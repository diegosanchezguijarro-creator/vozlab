"""Scribe server — local speech-to-text + LLM cleanup, exposes an HTTP API.

Nothing leaves your network: Whisper + the cleanup LLM run on this machine.

Endpoints:
  GET  /            -> service info (name, version, model)
  GET  /health      -> {"ok": true, "version": ...}  (no auth, minimal)
  GET  /version     -> {"name": "vozlab", "version": "..."}
  GET  /status      -> full details: models, device, uptime   (auth)
  GET  /settings    -> server settings, token removed         (auth)
  PATCH /settings   -> change models/language at runtime      (auth)
  GET  /models      -> cleanup models available locally       (auth)
  POST /self-test   -> transcribe a built-in sample           (auth)
  GET  /logs        -> recent server log lines                (auth)
  POST /transcribe  -> {"text": ..., "raw_text": ..., "timings": {...}}
      Body:   raw audio bytes (WAV/MP3/OGG/FLAC — anything PyAV can decode)
      Header: Authorization: Bearer <token>
      Query:  ?cleanup=true|false   (default from config)
"""

import copy
import hashlib
import io
import json
import os
import secrets
import subprocess
import threading
import time
from collections import deque
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from cleanup import (DEFAULT_CLEANUP_PROMPT, STYLES, build_prompt, cleanup_ok,
                     normalize_style, sanitize_vocabulary, strip_decoration)

VERSION = "1.5.0"
NAME = "vozlab"
API_VERSION = 1          # bump when the HTTP contract changes incompatibly

CONFIG_PATH = os.environ.get("VOZLAB_CONFIG", "/data/config.json")

# Rate limiting: dictations are seconds apart, so this only stops abuse/mistakes.
RATE_LIMIT_PER_MINUTE = int(os.environ.get("VOZLAB_RATE_LIMIT", "120"))
LOG_RING_SIZE = 300

# The app can find this server on the LAN by broadcasting a UDP probe.
DISCOVERY_PORT = int(os.environ.get("VOZLAB_DISCOVERY_PORT", "8093"))
DISCOVERY_MAGIC = b"VOZLAB/1 discover"
# port the app should use — the published one, not the container's 8080
PUBLIC_PORT = os.environ.get("VOZLAB_PUBLIC_PORT", "8092")

# Environment overrides — handy for Docker/Compose deployments where editing
# config.json is awkward. Anything set here wins over the file.
ENV_OVERRIDES = {
    "VOZLAB_TOKEN": "token",
    "VOZLAB_WHISPER_MODEL": "whisper_model",
    "VOZLAB_LANGUAGE": "language",
    "VOZLAB_COMPUTE_TYPE": "compute_type",
    "VOZLAB_CLEANUP": "cleanup",
    "VOZLAB_CLEANUP_GUARD": "cleanup_guard",
    "VOZLAB_CLEANUP_MODEL": "cleanup_model",
    "VOZLAB_CLEANUP_BASE_URL": "cleanup_base_url",
    "VOZLAB_EXPOSE_DETAILS": "expose_details",
}
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB (~2h of 16kHz mono WAV)

DEFAULT_CONFIG = {
    "token": None,                      # admin token, generated on first boot
    "device_tokens": [],                # extra tokens: one per device, revocable
    "whisper_model": "small",           # 'small' = multilingual; 'small.en' = English-only
    "language": "auto",                 # or "en", "es", "de", ...  ("auto" needs a multilingual model)
    "compute_type": "int8_float16",
    "beam_size": 5,
    "vad_filter": True,                 # skip silence before transcribing
    "cleanup": True,
    "cleanup_model": "qwen2.5:7b-instruct",
    "cleanup_base_url": "http://host.docker.internal:11434",
    "cleanup_temperature": 0.0,
    "cleanup_max_tokens": 500,
    "cleanup_guard": True,              # reject cleanups that invent words, keep the raw text
    "cleanup_prompt": DEFAULT_CLEANUP_PROMPT,
    "vocabulary": [],                   # names/terms Whisper should expect
    "discovery": True,                  # answer LAN discovery probes
    "expose_details": False,            # /health stays minimal unless you opt in
    "docs": False,                      # OpenAPI docs (/docs) are off by default
}

_state = {}
_log_ring: deque[str] = deque(maxlen=LOG_RING_SIZE)
_rate_buckets: dict[str, deque[float]] = {}


def _discovery_payload() -> bytes:
    """What a probe gets back: no token, no settings, nothing sensitive."""
    cfg = _state.get("config") or {}
    cert = os.environ.get("VOZLAB_TLS_CERT") or cfg.get("tls_certfile")
    return json.dumps({
        "name": NAME,
        "version": VERSION,
        "api": API_VERSION,
        "port": int(PUBLIC_PORT),
        "tls": bool(cert),
        "whisper_model": cfg.get("whisper_model"),
        "device": _state.get("device"),
    }).encode("utf-8")


def _discovery_loop() -> None:
    """Answer UDP probes so the Windows app can find this server by itself."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("", DISCOVERY_PORT))
    except OSError as e:
        log_line(f"discovery responder off (udp {DISCOVERY_PORT}): {e}")
        return
    sock.settimeout(1.0)
    log_line(f"discovery responder listening on udp/{DISCOVERY_PORT}")
    try:
        while not _state.get("shutdown"):
            try:
                data, addr = sock.recvfrom(512)
            except socket.timeout:
                continue
            except OSError:
                break
            if not data.startswith(DISCOVERY_MAGIC):
                continue
            try:
                sock.sendto(_discovery_payload(), addr)
            except OSError:
                pass
    finally:
        sock.close()


def log_line(message: str) -> None:
    """Print and keep the last few hundred lines for GET /logs."""
    stamp = time.strftime("%Y-%m-%d %H:%M:%S")
    line = f"{stamp} {message}"
    _log_ring.append(line)
    print(f"[vozlab] {message}", flush=True)


def _apply_env(cfg: dict) -> dict:
    """Apply VOZLAB_* environment overrides on top of the config file."""
    for env_name, key in ENV_OVERRIDES.items():
        raw = os.environ.get(env_name)
        if raw is None or raw == "":
            continue
        if isinstance(DEFAULT_CONFIG.get(key), bool):
            cfg[key] = raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            cfg[key] = raw
    return cfg


def _cached_whisper_models() -> list[str]:
    """Whisper models already downloaded into the mounted cache."""
    models = []
    root = os.path.join(os.environ.get("HF_HOME", "/data/hf"), "hub")
    try:
        for name in os.listdir(root):
            if name.startswith("models--"):
                parts = name.split("--")
                if len(parts) >= 3:
                    models.append(parts[-1])
    except OSError:
        pass
    return sorted(set(models))


def _gpu_info() -> dict | None:
    """GPU name and memory, when an NVIDIA device is visible."""
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total,memory.used",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, check=True,
        ).stdout.strip().splitlines()
    except Exception:  # noqa: BLE001
        return None
    if not out:
        return None
    name, total, used = [p.strip() for p in out[0].split(",")[:3]]
    return {"name": name, "memory_total_mb": int(total), "memory_used_mb": int(used)}


def load_config():
    """Read config.json, creating it with a generated token on first boot."""
    # deep copy: lists (device_tokens) must never be shared between configs
    cfg = copy.deepcopy(DEFAULT_CONFIG)
    created = False
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    cfg = _apply_env(cfg)
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(24)
        created = True
    if created and not os.environ.get("VOZLAB_TOKEN"):
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
                f.write("\n")
            os.chmod(CONFIG_PATH, 0o600)
        except OSError as e:
            log_line(f"WARNING: could not write {CONFIG_PATH}: {e}")

    # 'auto' language detection needs a multilingual model
    if cfg["language"].lower() == "auto" and cfg["whisper_model"].endswith(".en"):
        log_line("language=auto needs a multilingual model; forcing language=en "
                 f"for {cfg['whisper_model']}")
        cfg["language"] = "en"
    _state["token_created"] = created
    return cfg


def banner(cfg):
    """Startup banner. The token is shown **only when it is first created**, so
    it never lands in `docker logs` / journald on every restart."""
    line = "=" * 66
    print(line, flush=True)
    print(f"  Scribe server v{VERSION} — 100% local dictation", flush=True)
    print(line, flush=True)
    print(f"  Whisper model : {cfg['whisper_model']}  (language: {cfg['language']})", flush=True)
    print(f"  Cleanup LLM   : {cfg['cleanup_model'] if cfg['cleanup'] else 'disabled'}", flush=True)
    print(flush=True)
    if _state.get("token_created"):
        print("  NEW TOKEN — paste this into the Scribe app (shown once):", flush=True)
        print(f"      {cfg['token']}", flush=True)
    else:
        print("  Token: already configured (see ./data/config.json if you need it again)", flush=True)
    print(flush=True)
    print("  Find this machine's LAN IP with:  hostname -I", flush=True)
    print("  Then in the app use:              http://<LAN-IP>:8092", flush=True)
    print(line, flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    _state["config"] = cfg
    _state["started_at"] = time.time()
    _state["requests"] = 0
    _state["reloading"] = False
    _state["cached_models"] = _cached_whisper_models()
    _state["gpu"] = _gpu_info()
    _state["shutdown"] = False
    banner(cfg)

    if cfg.get("discovery", True):
        threading.Thread(target=_discovery_loop, daemon=True).start()

    from faster_whisper import WhisperModel

    model_id = cfg["whisper_model"]
    last_err = None
    for device, compute in (("cuda", cfg["compute_type"]), ("cpu", "int8")):
        try:
            t0 = time.time()
            _state["model"] = WhisperModel(model_id, device=device, compute_type=compute)
            _state["device"] = device
            last_err = None
            log_line(f"loaded '{model_id}' on {device} ({compute}) in {time.time()-t0:.1f}s")
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            log_line(f"model load on {device} failed: {e}")
    if last_err is not None:
        raise RuntimeError(f"could not load whisper model: {last_err}")

    if cfg["cleanup"]:
        try:
            t0 = time.time()
            await cleanup_text(cfg, "ok")
            log_line(f"cleanup model warm in {time.time()-t0:.1f}s")
        except Exception as e:  # noqa: BLE001
            log_line(f"cleanup warmup failed (will retry per request): {e}")

    yield
    _state["shutdown"] = True
    _state.clear()


app = FastAPI(title=NAME, version=VERSION, lifespan=lifespan,
              docs_url=None, redoc_url=None, openapi_url=None)


def _token_hash(token: str, salt: str) -> str:
    """Fast, salted hash. Tokens are 32 random bytes, so a KDF isn't needed."""
    return hashlib.sha256((salt + token).encode("utf-8")).hexdigest()


def authenticate(authorization: str, request: Request | None = None) -> tuple[str, dict | None]:
    """Check a bearer token. Returns (role, device_entry).

    The admin token (config.json / VOZLAB_TOKEN) always works. Extra
    per-device tokens can be issued and revoked individually, so a lost
    laptop doesn't mean rotating the key for every other machine.
    """
    token = authorization[7:] if authorization.startswith("Bearer ") else ""
    cfg = _state["config"]

    if token and secrets.compare_digest(token, cfg.get("token", "")):
        return "admin", None

    for entry in cfg.get("device_tokens", []):
        expected = entry.get("hash", "")
        if token and expected and secrets.compare_digest(
                _token_hash(token, entry.get("salt", "")), expected):
            # in-memory only: we must not write config.json on every request
            entry["last_used"] = int(time.time())
            if request is not None and request.client is not None:
                entry["last_ip"] = request.client.host
            return "device", entry

    raise HTTPException(status_code=401, detail="bad or missing token")


def require_auth(authorization: str = Header(default="")) -> None:
    authenticate(authorization)


def rate_limit(request: Request, authorization: str = Header(default="")):
    """Simple per-client sliding window. Dictation is bursty but low volume."""
    if RATE_LIMIT_PER_MINUTE <= 0:
        return
    client = request.client.host if request.client else "?"
    key = f"{client}:{authorization[-8:]}"
    now = time.time()
    bucket = _rate_buckets.setdefault(key, deque())
    while bucket and now - bucket[0] > 60:
        bucket.popleft()
    if len(bucket) >= RATE_LIMIT_PER_MINUTE:
        raise HTTPException(status_code=429, detail="too many requests, slow down")
    bucket.append(now)
    # keep the bookkeeping small
    if len(_rate_buckets) > 500:
        for stale in [k for k, v in _rate_buckets.items() if not v][:200]:
            _rate_buckets.pop(stale, None)


def transcribe_raw(cfg, audio, language: str | None = None):
    """Run faster-whisper on audio bytes (in memory — nothing touches disk)."""
    kwargs = {
        "beam_size": cfg["beam_size"],
        # voice-activity detection trims silence (better on long clips) but it
        # costs an onnxruntime pass per request; off makes short dictations faster
        "vad_filter": bool(cfg.get("vad_filter", True)),
        # dictation clips are independent: without this, Whisper can repeat or
        # invent text when the audio is quiet or short (hallucinations)
        "condition_on_previous_text": False,
    }
    lang = language or cfg["language"]
    if lang and lang.lower() != "auto":
        kwargs["language"] = lang

    # seeding Whisper with the user's names/terms makes it far more likely to
    # spell them right (it is a prompt, not a hard rule)
    terms = sanitize_vocabulary(cfg.get("vocabulary"))
    if terms:
        kwargs["initial_prompt"] = ", ".join(terms)[:400]

    stream = io.BytesIO(audio) if isinstance(audio, (bytes, bytearray)) else audio
    segments, info = _state["model"].transcribe(stream, **kwargs)
    text = "".join(seg.text for seg in segments).strip()
    return text, info.language


async def cleanup_text(cfg, raw_text: str, style: str | None = None) -> str:
    payload = {
        "model": cfg["cleanup_model"],
        "messages": [
            {"role": "system",
             "content": build_prompt(cfg["cleanup_prompt"], style, cfg.get("vocabulary"))},
            {"role": "user", "content": raw_text},
        ],
        "temperature": cfg["cleanup_temperature"],
        "options": {"num_predict": cfg["cleanup_max_tokens"]},
        "keep_alive": -1,  # stay resident on GPU so dictation is always warm
        "stream": False,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        r = await client.post(f"{cfg['cleanup_base_url'].rstrip('/')}/api/chat", json=payload)
        r.raise_for_status()
        return strip_decoration(r.json()["message"]["content"])


def service_info():
    cfg = _state["config"]
    info = {
        "name": NAME,
        "version": VERSION,
        "api": API_VERSION,
        "whisper_model": cfg["whisper_model"],
        "language": cfg["language"],
        "cleanup": cfg["cleanup"],
        "cleanup_model": cfg["cleanup_model"] if cfg["cleanup"] else None,
        "device": _state.get("device"),
        "tls": bool(os.environ.get("VOZLAB_TLS_CERT") or cfg.get("tls_certfile")),
    }
    if _state.get("started_at"):
        info["uptime_s"] = int(time.time() - _state["started_at"])
    return info


def _public_config(cfg: dict) -> dict:
    """Settings safe to send to an authenticated client (no token)."""
    keys = ("whisper_model", "language", "compute_type", "beam_size", "vad_filter", "cleanup",
            "cleanup_guard", "cleanup_model", "cleanup_base_url",
            "cleanup_temperature", "cleanup_max_tokens", "expose_details",
            "vocabulary")
    data_extra = {"styles": sorted(STYLES)}
    data = {k: cfg[k] for k in keys if k in cfg}
    data.update(data_extra)
    data["token_set"] = bool(cfg.get("token"))
    data["config_path"] = CONFIG_PATH
    return data


def _save_config(cfg: dict) -> None:
    payload = dict(cfg)
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w") as f:
            json.dump(payload, f, indent=2)
            f.write("\n")
        os.chmod(CONFIG_PATH, 0o600)
    except OSError as e:
        log_line(f"could not write {CONFIG_PATH}: {e}")


@app.get("/")
async def root():
    return {"name": NAME, "version": VERSION, "api": API_VERSION,
            "hint": "authenticated endpoints: /status /settings /models /self-test /logs"}


@app.get("/health")
async def health():
    """Liveness probe. Minimal by default: no models, no device, no secrets."""
    body = {"ok": True, "version": VERSION, "api": API_VERSION}
    if _state["config"].get("expose_details"):
        body.update({k: v for k, v in service_info().items() if k not in ("name",)})
    return body


@app.get("/status")
async def status(request: Request, authorization: str = Header(default="")):
    """Everything the app needs to show a useful status line."""
    role, entry = authenticate(authorization, request)
    info = service_info()
    info["auth"] = {"role": role, "device": entry.get("name") if entry else None}
    info["whisper_models_cached"] = _state.get("cached_models", [])
    info["ollama_models"] = await list_ollama_models(_state["config"])
    info["gpu"] = _state.get("gpu")
    info["reloading"] = _state.get("reloading", False)
    info["requests"] = _state.get("requests", 0)
    return info


@app.get("/tokens")
async def list_tokens(authorization: str = Header(default="")):
    """Devices that may dictate. Hashes are never returned."""
    authenticate(authorization)
    now = int(time.time())
    return {
        "tokens": [
            {
                "id": entry.get("id"),
                "name": entry.get("name"),
                "created": entry.get("created"),
                "last_used": entry.get("last_used"),
                "last_ip": entry.get("last_ip"),
                "age_days": round((now - entry["created"]) / 86400, 1) if entry.get("created") else None,
                "used": bool(entry.get("last_used")),
            }
            for entry in _state["config"].get("device_tokens", [])
        ]
    }


@app.post("/tokens")
async def create_token(request: Request, authorization: str = Header(default="")):
    """Issue a token for one device. The value is returned **once**."""
    authenticate(authorization)
    body = await request.json()
    name = str((body or {}).get("name") or "").strip()[:60]
    if not name:
        raise HTTPException(status_code=400, detail="a name is required (e.g. 'laptop')")

    cfg = _state["config"]
    token = secrets.token_urlsafe(32)
    salt = secrets.token_hex(16)
    entry = {
        "id": secrets.token_hex(4),
        "name": name,
        "salt": salt,
        "hash": _token_hash(token, salt),
        "created": int(time.time()),
        "last_used": None,
        "last_ip": None,
    }
    cfg.setdefault("device_tokens", []).append(entry)
    _save_config(cfg)
    log_line(f"issued a device token for '{name}' ({entry['id']})")
    return {"id": entry["id"], "name": name, "token": token}


@app.delete("/tokens/{token_id}")
async def revoke_token(token_id: str, authorization: str = Header(default="")):
    """Revoke one device (a lost laptop) without touching the others."""
    authenticate(authorization)
    cfg = _state["config"]
    tokens = cfg.get("device_tokens", [])
    kept = [e for e in tokens if e.get("id") != token_id]
    if len(kept) == len(tokens):
        raise HTTPException(status_code=404, detail="no such token")
    cfg["device_tokens"] = kept
    _save_config(cfg)
    log_line(f"revoked device token {token_id}")
    return {"ok": True, "revoked": token_id, "remaining": len(kept)}


@app.get("/version")
async def version():
    return {"name": NAME, "version": VERSION, "api": API_VERSION}


@app.get("/settings")
async def get_settings(authorization: str = Header(default="")):
    require_auth(authorization)
    return _public_config(_state["config"])


@app.patch("/settings")
async def patch_settings(request: Request, authorization: str = Header(default="")):
    """Change server settings at runtime (no SSH, no restart)."""
    require_auth(authorization)
    cfg = _state["config"]
    body = await request.json()
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="expected a JSON object")

    editable = {"whisper_model", "language", "cleanup", "cleanup_model",
                "cleanup_guard", "beam_size", "compute_type", "expose_details",
                "vocabulary", "vad_filter"}
    applied, ignored = {}, []
    for key, value in body.items():
        if key not in editable:
            ignored.append(key)
            continue
        if key == "vocabulary":
            value = sanitize_vocabulary(value)
        if key == "beam_size":
            value = max(1, min(10, int(value)))
        if key in ("cleanup", "cleanup_guard", "expose_details", "vad_filter"):
            value = bool(value)
        if key == "language":
            value = str(value).lower()
        cfg[key] = value
        applied[key] = value

    if not applied:
        raise HTTPException(status_code=400, detail=f"nothing to change (ignored: {ignored})")

    _save_config(cfg)
    log_line(f"settings updated: {applied}")

    # Whisper needs a real reload; the cleanup model is just a request parameter
    if any(k in applied for k in ("whisper_model", "compute_type")):
        # swap the model in the background; /status reports progress
        threading.Thread(target=reload_whisper, args=(dict(cfg),), daemon=True).start()
    return {"ok": True, "applied": applied, "reloading": _state.get("reloading", False)}


def reload_whisper(cfg: dict) -> None:
    """Swap the Whisper model in the background (old one is freed on success)."""
    from faster_whisper import WhisperModel

    _state["reloading"] = True
    try:
        for device, compute in (("cuda", cfg["compute_type"]), ("cpu", "int8")):
            try:
                t0 = time.time()
                model = WhisperModel(cfg["whisper_model"], device=device, compute_type=compute)
                _state["model"] = model
                _state["device"] = device
                log_line(f"reloaded '{cfg['whisper_model']}' on {device} ({compute}) "
                         f"in {time.time()-t0:.1f}s")
                return
            except Exception as e:  # noqa: BLE001
                log_line(f"reload on {device} failed: {e}")
        log_line("reload failed on every device; keeping the previous model")
    finally:
        _state["reloading"] = False


async def list_ollama_models(cfg: dict) -> list[str]:
    """Cleanup models already downloaded on the Ollama host."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{cfg['cleanup_base_url'].rstrip('/')}/api/tags")
            r.raise_for_status()
            return sorted(m["name"] for m in r.json().get("models", []))
    except Exception:  # noqa: BLE001
        return []


@app.get("/models")
async def models(authorization: str = Header(default="")):
    require_auth(authorization)
    cfg = _state["config"]
    return {
        "cleanup_models": await list_ollama_models(cfg),
        "current_cleanup_model": cfg["cleanup_model"],
        "whisper_models_cached": _state.get("cached_models", []),
        "current_whisper_model": cfg["whisper_model"],
    }


@app.post("/models/preload")
async def preload(request: Request, authorization: str = Header(default="")):
    """Warm a cleanup model into VRAM before you need it."""
    require_auth(authorization)
    body = await request.json()
    model = (body or {}).get("cleanup_model") or _state["config"]["cleanup_model"]
    cfg = _state["config"]
    t0 = time.time()
    try:
        async with httpx.AsyncClient(timeout=600.0) as client:
            r = await client.post(f"{cfg['cleanup_base_url'].rstrip('/')}/api/generate",
                                  json={"model": model, "prompt": "ok", "keep_alive": -1,
                                        "stream": False})
            r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"could not preload {model}: {e}")
    seconds = round(time.time() - t0, 1)
    log_line(f"preloaded cleanup model {model} in {seconds}s")
    return {"ok": True, "model": model, "seconds": seconds}


@app.post("/self-test")
async def self_test(authorization: str = Header(default="")):
    """End-to-end check: transcribe a bundled sample and run the cleanup pass."""
    require_auth(authorization)
    cfg = _state["config"]
    sample = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sample.wav")
    if not os.path.exists(sample):
        raise HTTPException(status_code=500, detail="sample.wav missing from the image")
    with open(sample, "rb") as f:
        audio = f.read()

    t0 = time.time()
    try:
        raw_text, language = await run_in_threadpool(transcribe_raw, cfg, audio, None)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=422, detail=f"transcription failed: {e}")
    whisper_s = time.time() - t0

    t1 = time.time()
    cleanup_error = None
    text = raw_text
    try:
        text = await cleanup_text(cfg, raw_text) if cfg["cleanup"] else raw_text
    except Exception as e:  # noqa: BLE001
        cleanup_error = str(e)
    cleanup_s = time.time() - t1

    log_line(f"self-test: {whisper_s:.2f}s whisper, {cleanup_s:.2f}s cleanup")
    return {
        "ok": not cleanup_error,
        "text": text,
        "raw_text": raw_text,
        "language": language,
        "cleanup_error": cleanup_error,
        "timings": {"whisper_s": round(whisper_s, 2), "cleanup_s": round(cleanup_s, 2),
                    "total_s": round(whisper_s + cleanup_s, 2)},
        "device": _state.get("device"),
    }


@app.get("/logs")
async def logs(authorization: str = Header(default=""), lines: int = Query(default=100)):
    """Recent server log lines (no transcripts: those are never logged)."""
    require_auth(authorization)
    lines = max(1, min(LOG_RING_SIZE, lines))
    return {"lines": list(_log_ring)[-lines:]}


@app.post("/transcribe")
async def transcribe(
    request: Request,
    authorization: str = Header(default=""),
    cleanup: bool = Query(default=None),
    language: str = Query(default=None),
    style: str = Query(default=None),
):
    authenticate(authorization, request)
    rate_limit(request, authorization)
    cfg = _state["config"]
    _state["requests"] = _state.get("requests", 0) + 1

    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio too large (25 MB max)")

    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="empty body: send raw audio bytes")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio too large (25 MB max)")

    t_total = time.time()
    t_whisper = time.time()
    try:
        raw_text, language = await run_in_threadpool(transcribe_raw, cfg, audio, language)
    except Exception as e:  # noqa: BLE001
        log_line(f"transcription failed: {e}")
        raise HTTPException(status_code=422, detail=f"could not decode/transcribe audio: {e}")
    t_whisper = time.time() - t_whisper

    use_cleanup = cfg["cleanup"] if cleanup is None else cleanup
    style = normalize_style(style)
    text, t_clean = raw_text, 0.0
    cleanup_rejected = None
    if use_cleanup and raw_text:
        t_clean = time.time()
        try:
            candidate = await cleanup_text(cfg, raw_text, style)
            if cfg.get("cleanup_guard", True):
                ok, reason = cleanup_ok(raw_text, candidate)
                if not ok:
                    cleanup_rejected = reason
                    log_line(f"cleanup rejected ({reason}); keeping raw transcript")
                    text = raw_text
                else:
                    text = candidate
            else:
                text = candidate
        except Exception as e:  # noqa: BLE001 — never fail dictation because the LLM errored
            log_line(f"cleanup failed, returning raw: {e}")
            text = raw_text
        t_clean = time.time() - t_clean

    return JSONResponse({
        "text": text,
        "raw_text": raw_text,
        "cleanup_used": use_cleanup and bool(raw_text),
        "cleanup_rejected": cleanup_rejected,
        "style": style,
        "language": language,
        "timings": {
            "whisper_s": round(t_whisper, 3),
            "cleanup_s": round(t_clean, 3),
            "total_s": round(time.time() - t_total, 3),
        },
    })
