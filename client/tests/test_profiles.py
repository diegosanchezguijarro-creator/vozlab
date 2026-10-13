"""Per-app profiles, LAN discovery and certificate pinning."""

import json
import os
import socket
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from vozlab import discovery, profiles  # noqa: E402


# ------------------------------------------------------------------ profiles --


def test_shipped_profiles_map_everyday_apps():
    assert profiles.DEFAULT_PROFILES["outlook.exe"] == "formal"
    assert profiles.DEFAULT_PROFILES["slack.exe"] == "casual"
    assert set(profiles.DEFAULT_PROFILES.values()) <= set(profiles.STYLES)


def test_clean_app_strips_paths_and_case():
    assert profiles.clean_app(r"C:\Program Files\Slack\slack.exe") == "slack.exe"
    assert profiles.clean_app("/usr/bin/Code") == "code"
    assert profiles.clean_app(None) == ""


def test_resolve_style_by_exact_name():
    mapping = {"slack.exe": "casual", "outlook.exe": "formal"}
    assert profiles.resolve_style("slack.exe", mapping) == "casual"
    assert profiles.resolve_style("OUTLOOK.EXE", mapping) == "formal"


def test_resolve_style_ignores_the_exe_suffix():
    mapping = {"slack": "casual"}
    assert profiles.resolve_style("slack.exe", mapping) == "casual"
    mapping = {"slack.exe": "casual"}
    assert profiles.resolve_style("slack", mapping) == "casual"


def test_unknown_apps_use_the_fallback():
    mapping = {"slack.exe": "casual"}
    assert profiles.resolve_style("notepad.exe", mapping) == "default"
    assert profiles.resolve_style("", mapping) == "default"
    assert profiles.resolve_style("notepad.exe", mapping, fallback="concise") == "concise"


def test_friendly_style_names_are_accepted():
    assert profiles.resolve_style("x.exe", {"x.exe": "email"}) == "formal"
    assert profiles.resolve_style("x.exe", {"x.exe": "chat"}) == "casual"
    assert profiles.resolve_style("x.exe", {"x.exe": "short"}) == "concise"
    assert profiles.resolve_style("x.exe", {"x.exe": "nonsense"}) == "default"


def test_profiles_are_off_when_disabled(monkeypatch):
    monkeypatch.setattr(profiles.foreground, "foreground_app", lambda: "slack.exe")
    cfg = {"per_app_profiles": False, "style": "formal"}
    assert profiles.style_for_now(cfg) == "formal"          # the manual style wins


def test_style_for_now_uses_the_foreground_app(monkeypatch):
    monkeypatch.setattr(profiles.foreground, "foreground_app", lambda: "slack.exe")
    assert profiles.style_for_now({"per_app_profiles": True}) == "casual"
    monkeypatch.setattr(profiles.foreground, "foreground_app", lambda: "")
    assert profiles.style_for_now({"per_app_profiles": True}) == "default"


def test_describe_rules_is_sorted_and_normalized():
    rules = profiles.describe_rules({"B.exe": "chat", "a.exe": "nonsense"})
    assert rules == [("a.exe", "default"), ("b.exe", "casual")]


# ----------------------------------------------------------------- foreground --


def test_foreground_helpers_are_safe_off_windows():
    from vozlab import foreground
    if foreground.available():
        pytest.skip("this is Windows: the real calls are exercised by the app")
    assert foreground.foreground_app() == ""
    assert foreground.foreground_window() == 0
    assert foreground.window_pid(1234) == 0
    assert foreground.process_name(1) == ""


# ------------------------------------------------------------------ discovery --


def test_parse_reply_accepts_a_real_answer():
    raw = json.dumps({"name": "vozlab", "version": "1.4.0", "port": 8092,
                      "tls": True, "whisper_model": "small", "device": "cuda"}).encode()
    entry = discovery.parse_reply(raw, "192.168.0.23")
    assert entry["url"] == "https://192.168.0.23:8092"
    assert entry["tls"] is True
    assert entry["version"] == "1.4.0"


def test_parse_reply_ignores_foreign_and_broken_packets():
    assert discovery.parse_reply(b"not json", "10.0.0.1") is None
    assert discovery.parse_reply(json.dumps({"name": "other"}).encode(), "10.0.0.1") is None
    assert discovery.parse_reply(b"", "10.0.0.1") is None


def test_parse_reply_defaults_to_plain_http():
    raw = json.dumps({"name": "vozlab"}).encode()
    entry = discovery.parse_reply(raw, "10.0.0.5")
    assert entry["url"] == "http://10.0.0.5:8092"
    assert entry["tls"] is False


@pytest.fixture
def fake_server():
    """A real UDP socket that answers like the container does."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    stop = threading.Event()

    def serve():
        sock.settimeout(0.2)
        while not stop.is_set():
            try:
                data, addr = sock.recvfrom(512)
            except (socket.timeout, OSError):
                continue
            if data.startswith(discovery.MAGIC):
                sock.sendto(json.dumps({"name": "vozlab", "port": 8092,
                                        "tls": False, "version": "1.4.0"}).encode(), addr)

    thread = threading.Thread(target=serve, daemon=True)
    thread.start()
    yield port
    stop.set()
    thread.join(timeout=2)
    sock.close()


def test_discover_finds_a_local_server(fake_server):
    found = discovery.discover(timeout=1.5, port=fake_server)
    assert len(found) == 1
    assert found[0]["url"].startswith("http://127.0.0.1")
    assert found[0]["version"] == "1.4.0"


def test_discover_returns_nothing_when_nobody_answers():
    # pick a port with no listener; nothing should be discovered or raised
    assert discovery.discover(timeout=0.6, port=1) == []


# ------------------------------------------------------------- TLS pinning ----

OPENSSL = subprocess.run(["which", "openssl"], capture_output=True, text=True).stdout.strip()


@pytest.fixture(scope="module")
def tls_server(tmp_path_factory):
    """A local HTTPS server with a self-signed certificate."""
    if not OPENSSL:
        pytest.skip("openssl is not available")
    directory = tmp_path_factory.mktemp("tls")
    cert = directory / "cert.pem"
    key = directory / "key.pem"
    subprocess.run([OPENSSL, "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
                    "-keyout", str(key), "-out", str(cert), "-subj", "/CN=localhost",
                    "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                   check=True, capture_output=True)

    import http.server
    import ssl

    stop = threading.Event()

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"ok": true, "name": "vozlab", "version": "1.4.0"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(str(cert), str(key))
    httpd = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield {"port": port, "cert": cert, "key": key, "directory": directory, "stop": stop}
    httpd.shutdown()
    httpd.server_close()


def test_fetch_fingerprint_matches_the_certificate(tls_server):
    import hashlib

    from vozlab.api import fetch_fingerprint, format_fingerprint
    fingerprint = fetch_fingerprint("127.0.0.1", tls_server["port"])
    der = subprocess.run([OPENSSL, "x509", "-in", str(tls_server["cert"]), "-outform", "DER"],
                         check=True, capture_output=True).stdout
    assert fingerprint == hashlib.sha256(der).hexdigest()
    assert len(fingerprint) == 64
    assert format_fingerprint(fingerprint).count(":") == 31


def test_pinned_request_succeeds_with_the_right_certificate(tls_server):
    from vozlab.api import VozLabAPI, fetch_fingerprint
    fingerprint = fetch_fingerprint("127.0.0.1", tls_server["port"])
    api = VozLabAPI(f"https://127.0.0.1:{tls_server['port']}", "token", fingerprint=fingerprint)
    assert api.health()["ok"] is True


def test_pinned_request_rejects_a_different_certificate(tls_server):
    from vozlab.api import ApiError, VozLabAPI
    # a pin that is not this certificate's fingerprint must be refused
    api = VozLabAPI(f"https://127.0.0.1:{tls_server['port']}", "token",
                    fingerprint="ab" * 32)
    with pytest.raises(ApiError) as err:
        api.health()
    assert err.value.kind == "bad_cert"


def test_https_without_a_pin_is_not_silently_accepted(tls_server):
    """No pin = no protection, so the CA check must be the one that fails."""
    from vozlab.api import ApiError, VozLabAPI
    api = VozLabAPI(f"https://127.0.0.1:{tls_server['port']}", "token")
    with pytest.raises(ApiError):
        api.health()          # self-signed + no pin -> refused


def test_http_ignores_the_pin():
    from vozlab.api import VozLabAPI
    api = VozLabAPI("http://127.0.0.1:9", "token", fingerprint="ab" * 32)
    assert isinstance(api.session.adapters["http://"], object)   # still a normal session
