"""Find Scribe servers on the local network.

The server answers a UDP probe on port 8093 with its name, version and HTTP
port — no token, no settings. The app broadcasts the same probe and lists the
replies, so a new user never has to hunt for an IP address.

Discovery is deliberately dumb and dependency-free (no mDNS/zeroconf): one
broadcast, a short listen window, done. It only ever runs when you press
*Find my server*.
"""

import json
import socket
import time

PROBE_PORT = 8093
MAGIC = b"SCRIBE/1 discover"
# the probe and reply name used before the rename: a new app still finds a
# server that has not been updated yet, and accepts the old reply name
LEGACY_MAGIC = b"VOZLAB/1 discover"
KNOWN_NAMES = ("scribe", "vozlab")
TIMEOUT = 1.6


def probe_messages() -> list[bytes]:
    """Both probe packets: the current one and the pre-rename one."""
    return [MAGIC + b"\n", LEGACY_MAGIC + b"\n"]


def parse_reply(data: bytes, host: str) -> dict | None:
    """Turn a raw reply into a server description (or None if it is not ours)."""
    try:
        payload = json.loads(data.decode("utf-8", "replace"))
    except (ValueError, UnicodeDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get("name") not in KNOWN_NAMES:
        return None
    port = payload.get("port") or 8092
    try:
        port = int(port)
    except (TypeError, ValueError):
        port = 8092
    scheme = "https" if payload.get("tls") else "http"
    return {
        "host": host,
        "port": port,
        "url": f"{scheme}://{host}:{port}",
        "version": str(payload.get("version") or ""),
        "tls": bool(payload.get("tls")),
        "whisper_model": payload.get("whisper_model") or "",
        "device": payload.get("device") or "",
    }


def discover(timeout: float = TIMEOUT, port: int = PROBE_PORT) -> list[dict]:
    """Broadcast a probe and collect the answers, de-duplicated by host:port."""
    found: dict[str, dict] = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.settimeout(0.3)

        # a server on this very machine answers on loopback
        targets = ["255.255.255.255", "127.0.0.1"]
        # some stacks drop the all-ones broadcast but answer the subnet one
        try:
            for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
                ip = info[4][0]
                if not ip.startswith("127."):
                    targets.append(".".join(ip.split(".")[:3] + ["255"]))
        except (socket.gaierror, OSError):
            pass

        for target in dict.fromkeys(targets):
            for message in probe_messages():
                for _ in range(2):                  # a lost packet is common on Wi-Fi
                    try:
                        sock.sendto(message, (target, port))
                    except OSError:
                        pass

        deadline = time.time() + timeout
        while time.time() < deadline:
            try:
                data, addr = sock.recvfrom(2048)
            except socket.timeout:
                continue
            except OSError:
                break
            entry = parse_reply(data, addr[0])
            if entry:
                found[f"{entry['host']}:{entry['port']}"] = entry
    finally:
        sock.close()
    return sorted(found.values(), key=lambda e: (e["host"], e["port"]))
