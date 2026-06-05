"""The kernel plane interface — the only code allowed to touch nftables.

For this first vertical slice we drive the in-kernel nftables/netfilter engine
(already part of the kernel we cloned) via the `nft` userspace tool. Later this
becomes a direct netlink talker, and eventually our own VeloGuard LSM. The
interface here stays the same; the backend gets closer to the metal.

Default mode is DRY-RUN: it prints exactly what it *would* run. Touching the
real firewall requires apply=True and (usually) root. Safe by default.
"""

from __future__ import annotations

import shutil
import subprocess

TABLE = "inet veloguard"
SET = "blocklist"
QUARANTINE_DIR = "/run/veloguard/quarantine"  # /run is tmpfs == RAM


class NftExecutor:
    def __init__(self, apply: bool = False):
        self.apply = apply
        self._planned: list[list[str]] = []

    def _run(self, args: list[str]) -> str:
        cmd = ["nft", *args]
        if not self.apply:
            self._planned.append(cmd)
            return f"[dry-run] {' '.join(cmd)}"
        if shutil.which("nft") is None:
            raise RuntimeError("nft not found — install nftables")
        proc = subprocess.run(cmd, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"nft failed: {proc.stderr.strip()}")
        return proc.stdout.strip() or f"ok: {' '.join(cmd)}"

    def setup(self) -> list[str]:
        """Idempotent-ish creation of the veloguard table, set, and drop rule."""
        steps = [
            ["add", "table", *TABLE.split()],
            ["add", "set", *TABLE.split(), SET,
             "{", "type", "ipv4_addr", ";", "flags", "interval", ";", "}"],
            ["add", "chain", *TABLE.split(), "input",
             "{", "type", "filter", "hook", "input",
             "priority", "-100", ";", "policy", "accept", ";", "}"],
            ["add", "rule", *TABLE.split(), "input",
             "ip", "saddr", "@" + SET, "drop"],
        ]
        return [self._run(s) for s in steps]

    def block_ip(self, ip: str) -> str:
        return self._run(["add", "element", *TABLE.split(), SET, "{", ip, "}"])

    def unblock_ip(self, ip: str) -> str:
        return self._run(["delete", "element", *TABLE.split(), SET, "{", ip, "}"])

    def list_blocked(self) -> str:
        return self._run(["list", "set", *TABLE.split(), SET])

    # --- generic command runner (non-nft): same dry-run discipline ----------
    def _sh(self, argv: list[str]) -> str:
        if not self.apply:
            self._planned.append(argv)
            return f"[dry-run] {' '.join(argv)}"
        if shutil.which(argv[0]) is None:
            raise RuntimeError(f"{argv[0]} not found")
        proc = subprocess.run(argv, capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"{argv[0]} failed: {proc.stderr.strip()}")
        return proc.stdout.strip() or f"ok: {' '.join(argv)}"

    # --- VPN: WireGuard profiles, or Tor as the fallback transport ----------
    def vpn_up(self, target: str | None) -> str:
        target = target or "veloguard"
        if target == "tor":
            return self._sh(["systemctl", "start", "tor"])
        return self._sh(["wg-quick", "up", target])

    def vpn_down(self, target: str | None) -> str:
        target = target or "veloguard"
        if target == "tor":
            return self._sh(["systemctl", "stop", "tor"])
        return self._sh(["wg-quick", "down", target])

    # --- Quarantine: freeze an unknown process, stash its exe in RAM (tmpfs) -
    def quarantine(self, target: str) -> str:
        stop = ["kill", "-STOP", target] if target.isdigit() else ["pkill", "-STOP", target]
        out = [self._sh(stop)]
        # /run is tmpfs (RAM) on systemd systems — the "RAM partition".
        qdir = f"{QUARANTINE_DIR}/{target}"
        out.append(self._sh(["mkdir", "-p", qdir]))
        if target.isdigit():
            out.append(self._sh(["cp", "--no-dereference", f"/proc/{target}/exe",
                                 f"{qdir}/exe"]))
        return "\n".join(out)

    def release_quarantine(self, target: str) -> str:
        cont = ["kill", "-CONT", target] if target.isdigit() else ["pkill", "-CONT", target]
        return "\n".join([self._sh(cont),
                          self._sh(["rm", "-rf", f"{QUARANTINE_DIR}/{target}"])])

    def kill_quarantine(self, target: str) -> str:
        kill = ["kill", "-KILL", target] if target.isdigit() else ["pkill", "-KILL", target]
        # SIGKILL the frozen process, then wipe its RAM stash.
        return "\n".join([self._sh(kill),
                          self._sh(["rm", "-rf", f"{QUARANTINE_DIR}/{target}"])])

    # --- Virtualization layer: run an uncertain app isolated (RAM, no net) ---
    def sandbox_run(self, target: str, tier: str = "light",
                    allow_net: bool = False) -> str:
        import shlex
        from . import vlayer
        chosen, degraded = vlayer.resolve_tier(tier)
        argv = vlayer.build_argv(shlex.split(target), chosen, allow_net=allow_net)
        out = self._sh(argv)
        note = f"  (tier: {chosen}{' — degraded from ' + tier if degraded else ''}"
        note += ", network OFF)" if not allow_net else ", network ON)"
        return out + "\n" + note
