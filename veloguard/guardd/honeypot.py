"""Decoy honeypot — fake services that bait attackers and capture what they do.

This is a real honeypot (a decoy to attract/observe attackers), distinct from
the process *quarantine* in executor.py. It opens fake SSH/HTTP/Telnet/etc.
listeners, hands out plausible banners, records whatever the attacker sends, and
writes each session to a RAM (tmpfs) capture log. The guard can then auto-block
the source and the AI analyst can diagnose the attack.

Default ports are high (2222/8080/2323) so it runs without root. In production,
redirect the real ports to these with nftables, e.g.:
    nft add rule inet veloguard prerouting tcp dport 22 redirect to :2222
"""

from __future__ import annotations

import json
import socket
import socketserver
import threading
import time
from pathlib import Path

_RAM_DIR = Path("/run/veloguard/honeypot")   # /run is tmpfs == RAM (root)


def capture_dir() -> Path:
    """Prefer the RAM/tmpfs dir; fall back to the per-user state dir if /run
    isn't writable (running unprivileged)."""
    try:
        _RAM_DIR.mkdir(parents=True, exist_ok=True)
        return _RAM_DIR
    except OSError:
        from . import state
        d = state.state_dir() / "honeypot"
        d.mkdir(parents=True, exist_ok=True)
        return d

# Fake banners per *real* service, keyed by the decoy port we listen on.
DECOYS = {
    2222: ("ssh", b"SSH-2.0-OpenSSH_8.9p1 Ubuntu-3ubuntu0.4\r\n"),
    2323: ("telnet", b"\r\nUbuntu 22.04 LTS\r\nlogin: "),
    8080: ("http", None),
    2121: ("ftp", b"220 ProFTPD Server ready.\r\n"),
}


def _printable(data: bytes) -> str:
    return data.decode("utf-8", "backslashreplace")


class _Handler(socketserver.BaseRequestHandler):
    service = "unknown"
    banner: bytes | None = None
    on_capture = None  # set per-server

    def handle(self) -> None:
        sock = self.request
        sock.settimeout(2.5)
        if self.banner:
            try:
                sock.sendall(self.banner)
            except OSError:
                return
        chunks = []
        try:
            while len(b"".join(chunks)) < 8192:
                buf = sock.recv(2048)
                if not buf:
                    break
                chunks.append(buf)
        except (socket.timeout, OSError):
            pass
        data = b"".join(chunks)
        cap = {
            "ts": time.time(),
            "iso": time.strftime("%Y-%m-%dT%H:%M:%S"),
            "service": self.service,
            "dst_port": self.server.server_address[1],
            "src_ip": self.client_address[0],
            "src_port": self.client_address[1],
            "bytes": len(data),
            "data": _printable(data),
        }
        _persist(cap)
        if self.on_capture:
            try:
                self.on_capture(cap)
            except Exception:
                pass
        try:
            sock.close()
        except OSError:
            pass


def _persist(cap: dict) -> None:
    try:
        with (capture_dir() / "captures.jsonl").open("a") as f:
            f.write(json.dumps(cap) + "\n")
    except OSError:
        pass


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def run(ports: list[int], on_capture=None) -> None:
    """Start a decoy on each port and block until interrupted."""
    servers = []
    for port in ports:
        service, banner = DECOYS.get(port, ("generic", None))
        handler = type("H", (_Handler,),
                       {"service": service, "banner": banner, "on_capture": staticmethod(on_capture)
                        if on_capture else None})
        try:
            srv = _Server(("0.0.0.0", port), handler)
        except OSError as e:
            print(f"  ! could not bind port {port}: {e}")
            continue
        servers.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"  decoy up: {service} on :{port}")
    if not servers:
        print("  no decoys running.")
        return
    print(f"  captures → {capture_dir()}/captures.jsonl   (Ctrl-C to stop)")
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n  shutting down decoys.")
        for s in servers:
            s.shutdown()
