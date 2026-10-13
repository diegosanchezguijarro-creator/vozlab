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

    def health(self) -> dict:
        return self._get("/health")

    def version(self) -> dict:
        return self._get("/version")

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
