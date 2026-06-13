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
WG_DIR = "/etc/wireguard"                      # where wg-quick reads <profile>.conf


class NftExecutor:
    def __init__(self, apply: bool = False, *, seal: str | None = None,
                 action=None):
        self.apply = apply
        self._planned: list[list[str]] = []
        # AI/agent/MCP actions arrive SEALED (dispatch sets seal+action). The
        # local-root CLI calls construct us plainly (seal is None) and run as
        # before — that path is the operator, not the AI.
        self._seal = seal
        self._action = action

    def _check_seal(self) -> None:
        """On a sealed channel, refuse any real kernel op whose action doesn't
        carry the guard's per-boot HMAC — i.e. that didn't pass the policy gate.
        Defeats a prompt-injected/compromised AI forging a kernel command."""
        if self._seal is None:
            return
        from . import authchan
        if not authchan.verify(self._action, self._seal):
            raise RuntimeError("guard seal invalid — refusing kernel op "
                               "(only policy-approved actions may touch the kernel)")

    def _run(self, args: list[str]) -> str:
        cmd = ["nft", *args]
        if not self.apply:
            self._planned.append(cmd)
            return f"[dry-run] {' '.join(cmd)}"
        self._check_seal()
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
        self._check_seal()
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
        # A WireGuard profile with AllowedIPs=0.0.0.0/0 *replaces the default
        # route*. If the profile is missing or its endpoint is dead, every
        # interface (Wi-Fi AND wired) silently black-holes — the connection
        # looks up but no traffic flows. So never raise a tunnel we can't
        # verify, and roll back one that comes up with no connectivity: better
        # no VPN than no network. (Real-run only; dry-run just previews.)
        cfg = f"{WG_DIR}/{target}.conf"
        if self.apply and not self._config_has_endpoint(cfg):
            raise RuntimeError(
                f"{cfg} is missing or has no Endpoint — bringing this tunnel up "
                f"would black-hole all routing. Import one first: "
                f"veloguard-vpn import <wg.conf>")
        out = self._sh(["wg-quick", "up", target])
        if self.apply and not self._tunnel_has_connectivity():
            # Internal rollback of our own failed action — not a user-initiated
            # vpn_down, so it needs no consent (leaving the black hole would).
            self._sh(["wg-quick", "down", target])
            raise RuntimeError(
                f"tunnel '{target}' came up but has no connectivity "
                f"(dead/unreachable endpoint) — rolled back to direct routing")
        return out

    def vpn_down(self, target: str | None) -> str:
        target = target or "veloguard"
        if target == "tor":
            return self._sh(["systemctl", "stop", "tor"])
        return self._sh(["wg-quick", "down", target])

    # --- VPN safety: a tunnel that can't carry traffic is worse than none ----
    def _config_has_endpoint(self, path: str) -> bool:
        """A usable WireGuard profile must exist and name a non-empty Endpoint."""
        try:
            with open(path) as fh:
                for line in fh:
                    s = line.strip()
                    if (s.lower().startswith("endpoint") and "=" in s
                            and s.split("=", 1)[1].strip()):
                        return True
        except OSError:
            return False
        return False

    def _tunnel_has_connectivity(self, settle: float = 1.5,
                                 timeout: float = 2.0, rounds: int = 2) -> bool:
        """Can we actually reach the internet through the freshly-raised tunnel?
        Raw TCP to anycast resolvers on :443 — deliberately NO DNS, because a
        dead tunnel usually breaks resolution too and we'd just hang on it."""
        import socket
        import time
        time.sleep(settle)  # WireGuard's first handshake is async — let it settle.
        for attempt in range(rounds):
            for host in ("1.1.1.1", "9.9.9.9"):
                try:
                    socket.create_connection((host, 443), timeout=timeout).close()
                    return True
                except OSError:
                    continue
            if attempt + 1 < rounds:
                time.sleep(1.0)
        return False

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
