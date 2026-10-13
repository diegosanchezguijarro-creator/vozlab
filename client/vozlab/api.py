"""HTTP client for the VozLab server."""

import requests

from . import VERSION


class ApiError(Exception):
    """Friendly, user-presentable API error."""

    def __init__(self, kind: str, detail: str = ""):
        self.kind = kind        # "unreachable" | "bad_token" | "empty" | "server" | "other"
        self.detail = detail
        super().__init__(f"{kind}: {detail}")


class VozLabAPI:
    def __init__(self, base_url: str, token: str, timeout: int = 120):
        self.base_url = (base_url or "").rstrip("/")
        self.token = token or ""
        self.timeout = timeout

    def _headers(self, content_type: str = "application/json") -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": content_type,
            "User-Agent": f"VozLab/{VERSION}",
        }

    def _get(self, path: str, timeout: int = 5) -> dict:
        if not self.base_url:
            raise ApiError("unreachable", "no server configured")
        try:
            r = requests.get(f"{self.base_url}{path}", headers=self._headers(), timeout=timeout)
        except requests.RequestException as e:
            raise ApiError("unreachable", str(e)) from e
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
            r = requests.request(method, f"{self.base_url}{path}", headers=self._headers(),
                                 json=payload, timeout=timeout)
        except requests.RequestException as e:
            raise ApiError("unreachable", str(e)) from e
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

    def transcribe(self, wav_bytes: bytes, cleanup: bool = True, language: str = "auto") -> dict:
        if not self.base_url:
            raise ApiError("unreachable", "no server configured")
        params = {"cleanup": str(bool(cleanup)).lower()}
        if language and language != "auto":
            params["language"] = language
        try:
            r = requests.post(
                f"{self.base_url}/transcribe",
                params=params,
                headers=self._headers("audio/wav"),
                data=wav_bytes,
                timeout=self.timeout,
            )
        except requests.RequestException as e:
            raise ApiError("unreachable", str(e)) from e

        if r.status_code == 401:
            raise ApiError("bad_token", r.text[:200])
        if r.status_code == 413:
            raise ApiError("other", "recording too large")
        if r.status_code != 200:
            raise ApiError("server", f"{r.status_code}: {r.text[:200]}")
        return r.json()
