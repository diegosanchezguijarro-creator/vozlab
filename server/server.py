"""VozLab server — local speech-to-text + LLM cleanup, exposes an HTTP API.

Nothing leaves your network: Whisper + the cleanup LLM run on this machine.

Endpoints:
  GET  /            -> service info (name, version, model)
  GET  /health      -> {"ok": true, ...}
  GET  /version     -> {"name": "vozlab", "version": "..."}
  POST /transcribe  -> {"text": ..., "raw_text": ..., "timings": {...}}
      Body:   raw audio bytes (WAV/MP3/OGG/FLAC — anything PyAV can decode)
      Header: Authorization: Bearer <token>
      Query:  ?cleanup=true|false   (default from config)
"""

import json
import os
import secrets
import socket
import tempfile
import time
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

VERSION = "1.0.0"
NAME = "vozlab"

CONFIG_PATH = os.environ.get("VOZLAB_CONFIG", "/data/config.json")
MAX_AUDIO_BYTES = 25 * 1024 * 1024  # 25 MB (~2h of 16kHz mono WAV)

DEFAULT_CONFIG = {
    "token": None,                      # generated on first boot
    "whisper_model": "small",           # 'small' = multilingual; 'small.en' = English-only
    "language": "auto",                 # or "en", "es", "de", ...  ("auto" needs a multilingual model)
    "compute_type": "int8_float16",
    "beam_size": 5,
    "cleanup": True,
    "cleanup_model": "llama3.1:8b",
    "cleanup_base_url": "http://host.docker.internal:11434",
    "cleanup_temperature": 0.0,
    "cleanup_max_tokens": 500,
    "cleanup_prompt": (
        "You are a dictation formatter. The user spoke the text below and your job is "
        "to produce the exact sentences they intended. Remove filler words (um, uh, "
        "erm, este, bueno, like, you know), stutters and repeated words. Fix "
        "punctuation, capitalization and spacing. "
        "IMPORTANT: always keep the ORIGINAL language of the text — never translate it. "
        "NEVER summarize, never add or remove information. "
        "Output ONLY the corrected text — no quotes, no commentary."
    ),
}

_state = {}


def load_config():
    """Read config.json, creating it with a generated token on first boot."""
    cfg = dict(DEFAULT_CONFIG)
    created = False
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH) as f:
            cfg.update(json.load(f))
    if not cfg.get("token"):
        cfg["token"] = secrets.token_urlsafe(24)
        created = True
    if created:
        try:
            os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
            with open(CONFIG_PATH, "w") as f:
                json.dump(cfg, f, indent=2)
                f.write("\n")
            os.chmod(CONFIG_PATH, 0o600)
        except OSError as e:
            print(f"[vozlab] WARNING: could not write {CONFIG_PATH}: {e}", flush=True)

    # 'auto' language detection needs a multilingual model
    if cfg["language"].lower() == "auto" and cfg["whisper_model"].endswith(".en"):
        print(f"[vozlab] language=auto needs a multilingual model; forcing language=en "
              f"for {cfg['whisper_model']}", flush=True)
        cfg["language"] = "en"
    return cfg


def banner(cfg):
    line = "=" * 66
    print(line, flush=True)
    print(f"  VozLab server v{VERSION} — 100% local dictation", flush=True)
    print(line, flush=True)
    print(f"  Whisper model : {cfg['whisper_model']}  (language: {cfg['language']})", flush=True)
    print(f"  Cleanup LLM   : {cfg['cleanup_model'] if cfg['cleanup'] else 'disabled'}", flush=True)
    print(flush=True)
    print("  TOKEN (paste this into the VozLab app):", flush=True)
    print(f"      {cfg['token']}", flush=True)
    print(flush=True)
    print("  Find this machine's LAN IP with:  hostname -I", flush=True)
    print("  Then in the app use:              http://<LAN-IP>:8092", flush=True)
    print(line, flush=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    cfg = load_config()
    _state["config"] = cfg
    banner(cfg)

    from faster_whisper import WhisperModel

    model_id = cfg["whisper_model"]
    last_err = None
    for device, compute in (("cuda", cfg["compute_type"]), ("cpu", "int8")):
        try:
            t0 = time.time()
            _state["model"] = WhisperModel(model_id, device=device, compute_type=compute)
            _state["device"] = device
            last_err = None
            print(f"[vozlab] loaded '{model_id}' on {device} ({compute}) in {time.time()-t0:.1f}s",
                  flush=True)
            break
        except Exception as e:  # noqa: BLE001
            last_err = e
            print(f"[vozlab] model load on {device} failed: {e}", flush=True)
    if last_err is not None:
        raise RuntimeError(f"could not load whisper model: {last_err}")

    if cfg["cleanup"]:
        try:
            t0 = time.time()
            await cleanup_text(cfg, "ok")
            print(f"[vozlab] cleanup model warm in {time.time()-t0:.1f}s", flush=True)
        except Exception as e:  # noqa: BLE001
            print(f"[vozlab] cleanup warmup failed (will retry per request): {e}", flush=True)

    yield
    _state.clear()


app = FastAPI(title=NAME, version=VERSION, lifespan=lifespan)


def require_auth(authorization: str = Header(default="")):
    if authorization != f"Bearer {_state['config']['token']}":
        raise HTTPException(status_code=401, detail="bad or missing token")


def transcribe_raw(cfg, audio_path, language: str | None = None):
    """Run faster-whisper on a file path. Returns (raw_text, language)."""
    kwargs = {"beam_size": cfg["beam_size"], "vad_filter": True}
    lang = language or cfg["language"]
    if lang and lang.lower() != "auto":
        kwargs["language"] = lang

    segments, info = _state["model"].transcribe(audio_path, **kwargs)
    text = "".join(seg.text for seg in segments).strip()
    return text, info.language


async def cleanup_text(cfg, raw_text: str) -> str:
    payload = {
        "model": cfg["cleanup_model"],
        "messages": [
            {"role": "system", "content": cfg["cleanup_prompt"]},
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
        return r.json()["message"]["content"].strip()


def service_info():
    cfg = _state["config"]
    return {
        "name": NAME,
        "version": VERSION,
        "whisper_model": cfg["whisper_model"],
        "language": cfg["language"],
        "cleanup": cfg["cleanup"],
        "cleanup_model": cfg["cleanup_model"] if cfg["cleanup"] else None,
        "device": _state.get("device"),
    }


@app.get("/")
async def root():
    return service_info()


@app.get("/health")
async def health():
    return {"ok": True, **{k: v for k, v in service_info().items() if k != "name"}}


@app.get("/version")
async def version():
    return {"name": NAME, "version": VERSION}


@app.post("/transcribe")
async def transcribe(
    request: Request,
    authorization: str = Header(default=""),
    cleanup: bool = Query(default=None),
    language: str = Query(default=None),
):
    require_auth(authorization)
    cfg = _state["config"]

    declared = request.headers.get("content-length")
    if declared and int(declared) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio too large (25 MB max)")

    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="empty body: send raw audio bytes")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="audio too large (25 MB max)")

    t_total = time.time()
    with tempfile.NamedTemporaryFile(suffix=".wav") as tmp:
        tmp.write(audio)
        tmp.flush()
        t_whisper = time.time()
        try:
            raw_text, language = await run_in_threadpool(transcribe_raw, cfg, tmp.name, language)
        except Exception as e:  # noqa: BLE001
            print(f"[vozlab] transcription failed: {e}", flush=True)
            raise HTTPException(status_code=422, detail=f"could not decode/transcribe audio: {e}")
        t_whisper = time.time() - t_whisper

    use_cleanup = cfg["cleanup"] if cleanup is None else cleanup
    text, t_clean = raw_text, 0.0
    if use_cleanup and raw_text:
        t_clean = time.time()
        try:
            text = await cleanup_text(cfg, raw_text)
        except Exception as e:  # noqa: BLE001 — never fail dictation because the LLM errored
            print(f"[vozlab] cleanup failed, returning raw: {e}", flush=True)
            text = raw_text
        t_clean = time.time() - t_clean

    return JSONResponse({
        "text": text,
        "raw_text": raw_text,
        "cleanup_used": use_cleanup and bool(raw_text),
        "language": language,
        "timings": {
            "whisper_s": round(t_whisper, 3),
            "cleanup_s": round(t_clean, 3),
            "total_s": round(time.time() - t_total, 3),
        },
    })
