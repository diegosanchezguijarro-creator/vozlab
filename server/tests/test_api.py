"""Tests for the HTTP surface: auth, minimal exposure, settings, rate limits.

Run with `python -m pytest tests -q` (needs pytest, fastapi, httpx).
The Whisper model is never loaded here: the app is exercised without its
lifespan, and `transcribe_raw` is stubbed, so these stay fast and offline.
"""

import copy
import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Point the server at a throwaway config *before* importing it.
_TMP = tempfile.mkdtemp(prefix="scribe-test-")
os.environ["SCRIBE_CONFIG"] = os.path.join(_TMP, "config.json")
os.environ["SCRIBE_TOKEN"] = "test-token"

import server  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

TOKEN = "test-token"
AUTH = {"Authorization": f"Bearer {TOKEN}"}
# No context manager: entering it would run the lifespan and load Whisper.
client = TestClient(server.app)


@pytest.fixture(autouse=True)
def clean_state():
    server._state.clear()
    server._state.update({
        # deep copy: a shallow one would share the device_tokens list between tests
        "config": copy.deepcopy({**server.DEFAULT_CONFIG, "token": TOKEN}),
        "cached_models": ["faster-whisper-small"],
        "gpu": {"name": "Test GPU", "memory_total_mb": 8188, "memory_used_mb": 4666},
        "started_at": 0,
        "requests": 0,
        "reloading": False,
        "device": "cuda",
    })
    server._rate_buckets.clear()
    server._log_ring.clear()
    yield


# --------------------------------------------------------------------- health


def test_health_is_minimal_by_default():
    body = client.get("/health").json()
    assert body["ok"] is True
    assert set(body) == {"ok", "version", "api"}
    # nothing that helps an unauthenticated scanner
    assert "whisper_model" not in body and "device" not in body


def test_health_can_expose_details_when_asked():
    server._state["config"]["expose_details"] = True
    body = client.get("/health").json()
    assert body["whisper_model"] == server.DEFAULT_CONFIG["whisper_model"]
    assert body["device"] == "cuda"


def test_docs_are_disabled():
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404


def test_root_lists_only_authenticated_endpoints():
    body = client.get("/").json()
    assert body["name"] == "scribe"
    assert "token" not in json.dumps(body)


# ----------------------------------------------------------------------- auth


@pytest.mark.parametrize("path", ["/status", "/settings", "/models", "/logs"])
def test_authenticated_endpoints_reject_anonymous(path):
    assert client.get(path).status_code == 401


def test_auth_rejects_wrong_token():
    r = client.get("/status", headers={"Authorization": "Bearer nope"})
    assert r.status_code == 401


def test_status_returns_useful_details():
    body = client.get("/status", headers=AUTH).json()
    assert body["device"] == "cuda"
    assert body["whisper_models_cached"] == ["faster-whisper-small"]
    assert body["gpu"]["name"] == "Test GPU"
    assert body["requests"] == 0
    assert "token" not in body


# -------------------------------------------------------------------- settings


def test_get_settings_never_leaks_the_token():
    body = client.get("/settings", headers=AUTH).json()
    assert "token" not in body
    assert body["token_set"] is True
    assert body["cleanup_model"] == server.DEFAULT_CONFIG["cleanup_model"]


def test_patch_settings_applies_and_persists():
    r = client.patch("/settings", headers=AUTH, json={"language": "es"})
    assert r.status_code == 200
    assert r.json()["applied"] == {"language": "es"}

    with open(server.CONFIG_PATH) as f:
        assert json.load(f)["language"] == "es"
    # the file must not be world-readable
    assert oct(os.stat(server.CONFIG_PATH).st_mode)[-3:] == "600"


def test_patch_settings_ignores_unknown_keys():
    r = client.patch("/settings", headers=AUTH, json={"nope": 1, "language": "en"})
    assert r.status_code == 200
    assert r.json()["applied"] == {"language": "en"}


def test_patch_settings_rejects_empty_change():
    r = client.patch("/settings", headers=AUTH, json={"token": "hijack"})
    assert r.status_code == 400
    # the token must be untouched
    assert server._state["config"]["token"] == TOKEN


def test_patch_settings_clamps_beam_size():
    client.patch("/settings", headers=AUTH, json={"beam_size": 99})
    assert server._state["config"]["beam_size"] == 10


def test_patch_settings_cannot_set_the_token():
    client.patch("/settings", headers=AUTH, json={"token": "evil"})
    assert server._state["config"]["token"] == TOKEN


# ------------------------------------------------------------------ transcribe


@pytest.fixture
def stub_whisper(monkeypatch):
    """Replace the model call and record exactly what it received."""
    seen = {}

    def fake_raw(cfg, audio, language=None):
        seen["audio"] = audio
        seen["language"] = language
        return "hello world", "en"

    monkeypatch.setattr(server, "transcribe_raw", fake_raw)
    return seen


def test_transcribe_auth_required():
    assert client.post("/transcribe", content=b"x").status_code == 401


def test_transcribe_rejects_empty_body(stub_whisper):
    r = client.post("/transcribe", headers=AUTH, content=b"")
    assert r.status_code == 400


def test_transcribe_rejects_oversized_body(stub_whisper, monkeypatch):
    monkeypatch.setattr(server, "MAX_AUDIO_BYTES", 10)
    r = client.post("/transcribe", headers=AUTH, content=b"x" * 50)
    assert r.status_code == 413


def test_transcribe_passes_bytes_not_a_file(stub_whisper):
    """Audio must stay in memory — no temp files on disk."""
    r = client.post("/transcribe?cleanup=false", headers=AUTH, content=b"RIFFfake")
    assert r.status_code == 200
    assert isinstance(stub_whisper["audio"], (bytes, bytearray))
    assert r.json()["text"] == "hello world"
    assert r.json()["cleanup_used"] is False


def test_transcribe_survives_a_broken_audio_stream(monkeypatch):
    def boom(cfg, audio, language=None):
        raise ValueError("bad wav")

    monkeypatch.setattr(server, "transcribe_raw", boom)
    r = client.post("/transcribe?cleanup=false", headers=AUTH, content=b"junk")
    assert r.status_code == 422
    assert "bad wav" in r.json()["detail"]


def test_transcribe_keeps_raw_text_when_cleanup_lies(stub_whisper, monkeypatch):
    """A hallucinating cleanup model must never replace the real transcript."""
    async def bad_cleanup(cfg, raw_text, style=None):
        return "completely different words"

    monkeypatch.setattr(server, "cleanup_text", bad_cleanup)
    r = client.post("/transcribe", headers=AUTH, content=b"RIFFfake")
    body = r.json()
    assert body["cleanup_used"] is True
    assert body["cleanup_rejected"]
    assert body["text"] == "hello world"


def test_transcribe_rate_limit(stub_whisper, monkeypatch):
    monkeypatch.setattr(server, "RATE_LIMIT_PER_MINUTE", 3)
    codes = [client.post("/transcribe?cleanup=false", headers=AUTH,
                         content=b"RIFF").status_code for _ in range(5)]
    assert codes[:3] == [200, 200, 200]
    assert codes[3] == 429 and codes[4] == 429


def test_rate_limit_can_be_disabled(stub_whisper, monkeypatch):
    monkeypatch.setattr(server, "RATE_LIMIT_PER_MINUTE", 0)
    for _ in range(8):
        assert client.post("/transcribe?cleanup=false", headers=AUTH,
                           content=b"RIFF").status_code == 200


# ------------------------------------------------------------------ misc infra


def test_logs_are_available_but_never_contain_transcripts(stub_whisper):
    client.post("/transcribe?cleanup=false", headers=AUTH, content=b"RIFFsecret")
    lines = client.get("/logs?lines=50", headers=AUTH).json()["lines"]
    assert isinstance(lines, list)
    assert not any("RIFFsecret" in line for line in lines)


def test_models_survive_an_unreachable_ollama():
    server._state["config"]["cleanup_base_url"] = "http://127.0.0.1:1"
    body = client.get("/models", headers=AUTH).json()
    assert body["cleanup_models"] == []
    assert body["current_whisper_model"] == server.DEFAULT_CONFIG["whisper_model"]


def test_self_test_reports_a_missing_sample(monkeypatch):
    monkeypatch.setattr(os.path, "dirname", lambda _p: "/nonexistent")
    r = client.post("/self-test", headers=AUTH)
    assert r.status_code == 500
    assert "sample" in r.json()["detail"]


def test_version_endpoint_is_public():
    body = client.get("/version").json()
    assert body["api"] == server.API_VERSION
    assert body["version"] == server.VERSION


# -------------------------------------------------------------- device tokens


def test_issue_and_use_a_device_token():
    issued = client.post("/tokens", headers=AUTH, json={"name": "laptop"}).json()
    assert issued["id"] and issued["token"]
    device = {"Authorization": f"Bearer {issued['token']}"}

    # the same token on any endpoint
    assert client.get("/status", headers=device).status_code == 200
    r = client.post("/transcribe", headers=device, content=b"RIFF")
    assert r.status_code != 401
    assert client.get("/settings", headers=device).status_code == 200


def test_device_token_hash_is_never_returned():
    client.post("/tokens", headers=AUTH, json={"name": "laptop"})
    listed = client.get("/tokens", headers=AUTH).json()["tokens"]
    assert len(listed) == 1
    assert listed[0]["name"] == "laptop"
    blob = json.dumps(listed)
    assert "hash" not in blob and "salt" not in blob and "token" not in blob


def test_revoked_device_token_stops_working():
    issued = client.post("/tokens", headers=AUTH, json={"name": "stolen"}).json()
    device = {"Authorization": f"Bearer {issued['token']}"}
    assert client.get("/status", headers=device).status_code == 200

    assert client.delete(f"/tokens/{issued['id']}", headers=AUTH).status_code == 200
    assert client.get("/status", headers=device).status_code == 401
    # and the admin token is untouched
    assert client.get("/status", headers=AUTH).status_code == 200


def test_revoking_an_unknown_token_is_a_404():
    assert client.delete("/tokens/deadbeef", headers=AUTH).status_code == 404


def test_device_tokens_are_stored_hashed_on_disk():
    issued = client.post("/tokens", headers=AUTH, json={"name": "laptop"}).json()
    raw = open(server.CONFIG_PATH).read()
    assert issued["token"] not in raw
    stored = json.loads(raw)["device_tokens"]
    assert stored[0]["hash"] and stored[0]["salt"]


def test_token_management_requires_auth():
    assert client.get("/tokens").status_code == 401
    assert client.post("/tokens", json={"name": "x"}).status_code == 401
    assert client.delete("/tokens/whatever").status_code == 401


def test_device_token_needs_a_name():
    assert client.post("/tokens", headers=AUTH, json={}).status_code == 400
    assert client.post("/tokens", headers=AUTH, json={"name": "   "}).status_code == 400


def test_status_reports_which_device_is_talking():
    issued = client.post("/tokens", headers=AUTH, json={"name": "laptop"}).json()
    device = {"Authorization": f"Bearer {issued['token']}"}
    assert client.get("/status", headers=device).json()["auth"] == {
        "role": "device", "device": "laptop"}
    assert client.get("/status", headers=AUTH).json()["auth"]["role"] == "admin"


def test_a_wrong_token_of_the_right_length_is_still_rejected():
    issued = client.post("/tokens", headers=AUTH, json={"name": "laptop"}).json()
    tampered = issued["token"][:-1] + ("A" if issued["token"][-1] != "A" else "B")
    assert client.get("/status", headers={"Authorization": f"Bearer {tampered}"}).status_code == 401


# ------------------------------------------------ styles, vocabulary, TLS, LAN


def test_transcribe_forwards_the_style(stub_whisper, monkeypatch):
    seen = {}

    async def spy(cfg, raw_text, style=None):
        seen["style"] = style
        return raw_text

    monkeypatch.setattr(server, "cleanup_text", spy)
    r = client.post("/transcribe?style=formal", headers=AUTH, content=b"RIFF")
    assert r.status_code == 200
    assert seen["style"] == "formal"
    assert r.json()["style"] == "formal"


def test_unknown_style_degrades_to_default(stub_whisper, monkeypatch):
    seen = {}

    async def spy(cfg, raw_text, style=None):
        seen["style"] = style
        return raw_text

    monkeypatch.setattr(server, "cleanup_text", spy)
    client.post("/transcribe?style=shakespearean", headers=AUTH, content=b"RIFF")
    assert seen["style"] == "default"
    assert client.post("/transcribe", headers=AUTH, content=b"RIFF").json()["style"] == "default"


def test_vocabulary_is_sent_to_whisper_as_an_initial_prompt(monkeypatch):
    captured = {}

    class FakeInfo:
        language = "en"

    class FakeModel:
        def transcribe(self, stream, **kwargs):
            captured.update(kwargs)
            return [], FakeInfo()

    monkeypatch.setitem(server._state, "model", FakeModel())
    cfg = {**server.DEFAULT_CONFIG, "vocabulary": ["Scribe", "Diego"]}
    server.transcribe_raw(cfg, b"RIFF")
    assert "Scribe" in captured["initial_prompt"]
    assert "Diego" in captured["initial_prompt"]


def test_no_vocabulary_means_no_initial_prompt(monkeypatch):
    captured = {}

    class FakeInfo:
        language = "en"

    class FakeModel:
        def transcribe(self, stream, **kwargs):
            captured.update(kwargs)
            return [], FakeInfo()

    monkeypatch.setitem(server._state, "model", FakeModel())
    server.transcribe_raw({**server.DEFAULT_CONFIG, "vocabulary": []}, b"RIFF")
    assert "initial_prompt" not in captured


def test_settings_expose_and_update_vocabulary():
    assert client.get("/settings", headers=AUTH).json()["vocabulary"] == []
    assert "styles" in client.get("/settings", headers=AUTH).json()

    r = client.patch("/settings", headers=AUTH, json={"vocabulary": ["Scribe", "scribe", "Diego"]})
    assert r.status_code == 200
    assert r.json()["applied"]["vocabulary"] == ["Scribe", "Diego"]
    assert client.get("/settings", headers=AUTH).json()["vocabulary"] == ["Scribe", "Diego"]


def test_discovery_reply_leaks_nothing():
    import json as _json
    server._state["device"] = "cuda"
    payload = _json.loads(server._discovery_payload())
    assert payload["name"] == "scribe"
    assert payload["port"] == int(server.PUBLIC_PORT)
    assert set(payload) <= {"name", "version", "api", "port", "tls", "whisper_model", "device"}
    blob = _json.dumps(payload)
    assert server._state["config"]["token"] not in blob
    assert "token" not in payload


def test_status_reports_tls_state(monkeypatch):
    monkeypatch.delenv("SCRIBE_TLS_CERT", raising=False)
    assert client.get("/status", headers=AUTH).json()["tls"] is False
    monkeypatch.setenv("SCRIBE_TLS_CERT", "/data/tls/cert.pem")
    assert client.get("/status", headers=AUTH).json()["tls"] is True


def test_run_server_ssl_kwargs():
    import importlib
    import run_server

    importlib.reload(run_server)
    assert run_server.ssl_kwargs() == {}          # no cert configured

    os.environ["SCRIBE_TLS_CERT"] = "/data/tls/cert.pem"
    try:
        assert run_server.ssl_kwargs() == {
            "ssl_certfile": "/data/tls/cert.pem", "ssl_keyfile": "/data/tls/cert.pem"}
        os.environ["SCRIBE_TLS_KEY"] = "/data/tls/key.pem"
        assert run_server.ssl_kwargs()["ssl_keyfile"] == "/data/tls/key.pem"
    finally:
        os.environ.pop("SCRIBE_TLS_CERT", None)
        os.environ.pop("SCRIBE_TLS_KEY", None)
