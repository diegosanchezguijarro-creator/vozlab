"""HTTP client for the Scribe server.

Works over plain HTTP on a trusted LAN, or over HTTPS with **certificate
pinning**: the app remembers the server's certificate fingerprint the first time
you connect (trust on first use) and refuses anything else afterwards, so a
self-signed certificate is as safe as the connection itself — no CA, no
warnings to click through.
"""

import hashlib
import socket
import ssl

import requests
from requests.adapters import HTTPAdapter
from urllib3.poolmanager import PoolManager

from . import VERSION


def fetch_fingerprint(host: str, port: int, timeout: float = 6.0) -> str:
    """SHA-256 of the TLS certificate a server presents, as lowercase hex."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE        # we only want to *look* at the cert
    with socket.create_connection((host, int(port)), timeout=timeout) as raw:
        with context.wrap_socket(raw, server_hostname=host) as tls:
            der = tls.getpeercert(binary_form=True)
    if not der:
        raise OSError("the server did not present a certificate")
    return hashlib.sha256(der).hexdigest()


def normalize_fingerprint(fingerprint: str) -> str:
    return (fingerprint or "").strip().lower().replace(":", "")


def format_fingerprint(fingerprint: str) -> str:
    """AA:BB:CC:… so two humans can compare it out loud."""
    clean = normalize_fingerprint(fingerprint)
    return ":".join(clean[i:i + 2] for i in range(0, len(clean), 2)).upper()


class PinnedAdapter(HTTPAdapter):
    """Refuse any certificate whose SHA-256 fingerprint is not the pinned one.

    urllib3 compares the fingerprint while wrapping the socket, so this replaces
    CA verification entirely — which is what makes a self-signed certificate
    (the normal home-lab case) safe to use.
    """

    def __init__(self, fingerprint: str, **kwargs):
        self.fingerprint = normalize_fingerprint(fingerprint)
        super().__init__(**kwargs)

    def init_poolmanager(self, connections, maxsize, block=False, **pool_kwargs):
        pool_kwargs.update(assert_fingerprint=self.fingerprint, cert_reqs="CERT_NONE")
        self.poolmanager = PoolManager(num_pools=connections, maxsize=maxsize,
                                       block=block, **pool_kwargs)


class ApiError(Exception):
    """Friendly, user-presentable API error."""

    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind        # "unreachable" | "bad_token" | "bad_cert" | "server" | "other"
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


def _classify(exc: Exception) -> ApiError:
    """Turn a requests/urllib3 failure into something the UI can explain."""
    text = str(exc)
    lowered = text.lower()
    if "fingerprint" in lowered or "certificate" in lowered or "ssl" in lowered:
        return ApiError("bad_cert", text[:200])
    return ApiError("unreachable", text[:300])


class ScribeAPI:
    def __init__(self, base_url: str, token: str, timeout: int = 120,
                 fingerprint: str = ""):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout
        self.session = requests.Session()
        if self.base_url.startswith("https://") and fingerprint:
            # pin the certificate: every request goes through this adapter
            self.session.mount("https://", PinnedAdapter(fingerprint))
            self.session.verify = False

    def _headers(self, content_type: str = "application/json") -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": content_type,
            "User-Agent": f"Scribe/{VERSION}",
        }

    def _get(self, path: str, timeout: int = 5) -> dict:
        if not self.base_url:
            raise ApiError("unreachable", "no server configured")
        try:
            r = self.session.get(f"{self.base_url}{path}", headers=self._headers(),
                                 timeout=timeout)
        except requests.RequestException as e:
            raise _classify(e) from e
        if r.status_code == 401:
            raise ApiError("bad_token", r.text[:200])
        if r.status_code != 200:
            raise ApiError("server", f"{r.status_code}: {r.text[:200]}")
        return r.json()

    def _send(self, method: str, path: str, payload: dict | None = None,
              timeout: int = 30) -> dict:
        if not self.base_url:
            raise ApiError("unreachable", "no server configured")
        try:
            r = self.session.request(method, f"{self.base_url}{path}", headers=self._headers(),
                                     json=payload, timeout=timeout)
        except requests.RequestException as e:
            raise _classify(e) from e
        if r.status_code == 401:
            raise ApiError("bad_token", r.text[:200])
        if r.status_code == 404:
            raise ApiError("server", "not found on this server version")
        if r.status_code == 429:
            raise ApiError("other", "the server is rate limiting requests, try again shortly")
        if r.status_code >= 400:
            detail = r.text[:200]
            try:
                detail = r.json().get("detail", detail)
            except ValueError:
                pass
            raise ApiError("server", str(detail))
        return r.json() if r.content else {}

    def health(self) -> dict:
        return self._get("/health")

    def version(self) -> dict:
        return self._get("/version")

    # -- server introspection / remote configuration -------------------------
    def status(self) -> dict:
        """Everything the app needs for its status panel (authenticated)."""
        return self._get("/status", timeout=8)

    def get_settings(self) -> dict:
        return self._get("/settings")

    def patch_settings(self, changes: dict) -> dict:
        return self._send("PATCH", "/settings", changes)

    def models(self) -> dict:
        return self._get("/models", timeout=15)

    def preload_model(self, cleanup_model: str | None = None) -> dict:
        payload = {"cleanup_model": cleanup_model} if cleanup_model else {}
        return self._send("POST", "/models/preload", payload, timeout=900)

    def self_test(self) -> dict:
        return self._send("POST", "/self-test", None, timeout=300)

    def logs(self, lines: int = 100) -> list[str]:
        return self._get(f"/logs?lines={int(lines)}").get("lines", [])

    def list_tokens(self) -> list[dict]:
        return self._get("/tokens").get("tokens", [])

    def create_token(self, name: str) -> dict:
        return self._send("POST", "/tokens", {"name": name})

    def revoke_token(self, token_id: str) -> dict:
        return self._send("DELETE", f"/tokens/{token_id}")

    def transcribe(self, wav_bytes: bytes, cleanup: bool = True, language: str = "auto",
                   style: str = "") -> dict:
        if not self.base_url:
            raise ApiError("unreachable", "no server configured")
        params = {"cleanup": str(bool(cleanup)).lower()}
        if language and language != "auto":
            params["language"] = language
        if style:
            params["style"] = style
        try:
            r = self.session.post(
                f"{self.base_url}/transcribe",
                params=params,
                headers=self._headers("audio/wav"),
                data=wav_bytes,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise _classify(e) from e

        if r.status_code == 401:
            raise ApiError("bad_token", r.text[:200])
        if r.status_code == 413:
            raise ApiError("other", "recording too large")
        if r.status_code != 200:
            raise ApiError("server", f"{r.status_code}: {r.text[:200]}")
        return r.json()
