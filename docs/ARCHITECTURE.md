# Architecture

VozLab is two programs that talk over your LAN: a Windows tray app and a Docker
server. Nothing is centralised, nothing phones home.

```
┌──────────────────────────────┐        ┌───────────────────────────────────────────┐
│ client/  (Windows, Python)   │        │ server/  (Docker, FastAPI)                │
│                              │        │                                           │
│ tray.py        tray icon     │        │ server.py   HTTP API + model lifecycle    │
│ hotkeys.py     global hook   │        │ cleanup.py  LLM prompt + safety guard     │
│ audio.py       mic capture   │  HTTP  │ Dockerfile  Python 3.12 + CUDA libs       │
│ api.py         HTTP client   │ ──────►│                                           │
│ ui/            windows, pill │ token  │ faster-whisper → CTranslate2 (GPU/CPU)    │
│ app.py         orchestration │        │ Ollama (sibling or host) → cleanup LLM    │
└──────────────────────────────┘        └───────────────────────────────────────────┘
```

## Request lifecycle

1. **Hotkey** — `hotkeys.py` installs one `keyboard.hook` and pushes events onto a
   queue. A worker thread does the real work, because Windows silently removes
   low-level hooks whose callback takes longer than ~300 ms.
2. **Recording** — `audio.py` opens a 16 kHz mono float32 stream via PortAudio,
   tracks RMS (drives the pill's level meter) and optionally auto-stops after
   `silence_ms` of quiet following speech.
3. **Upload** — `api.py` packs the frames into 16-bit PCM WAV in memory and posts
   them to `/transcribe` with `Authorization: Bearer <token>`. Recordings shorter
   than `min_seconds` are dropped before the request.
4. **Server** — FastAPI writes the bytes to a temporary file (faster-whisper needs
   a path), runs Silero VAD to trim silence, transcribes, then deletes it.
5. **Cleanup** — the transcript goes to the local LLM with a formatter prompt.
   `cleanup.py:cleanup_ok()` then checks the result and **rejects any rewrite that
   invents words**, falling back to the raw transcript.
6. **Insert** — the client copies the text to the clipboard, sends Ctrl+V, and
   restores the previous clipboard a second later.

## Design decisions worth knowing

**GPU is opt-in in Compose.** Docker Compose merges `deploy.resources…
reservations.devices` and cannot remove entries in an overlay, so a GPU request in
the base file would break every CPU-only machine. Instead the base stacks request
nothing and `docker-compose.gpu.yml` adds the GPU.

**The cleanup guard exists because models misbehave.** An instruct model will
happily *answer* a dictated question ("are you responding to me?" → "Yes, I am
responding to you."). The prompt forbids it, and the guard is the safety net.

**Everything the app needs is in `%APPDATA%\VozLab`.** The install directory holds
only code, so updates never touch settings.

**Hotkeys are matched by hardware scan code** (e.g. right Ctrl = 285) with
localised-name fallbacks, because the `keyboard` library reports key names in the
OS language ("ctrl derecha" on Spanish Windows).

**The client is a package, not a script.** `run_vozlab.py` is a thin dev entry
point; PyInstaller builds the same code into the tray app. The headless UI
renderer (`client/tools/ui_preview.py`) runs every window with demo data, which is
how the screenshots and the demo GIF are generated.

## Repository layout

```
server/
  server.py            HTTP API, config, model lifecycle
  cleanup.py           formatter prompt + safety guard (unit-tested)
  Dockerfile           python:3.12-slim + ffmpeg + CTranslate2/CUDA libs
  docker-compose.yml   server only (builds locally)
  docker-compose.gpu.yml
  docker-compose.full.yml       + Ollama + model preload (published image)
  docker-compose.full.gpu.yml
  install.sh           one-command setup
  tests/               prompt + guard tests
  tools/               benchmark_cleanup.py
client/
  vozlab/
    app.py             orchestrator (tray, hotkeys, recorder, paste)
    audio.py           capture, level metering, auto-stop
    hotkeys.py         hook + queue + calibration
    api.py             server client
    config.py          settings storage + migrations
    updater.py         release checks (opt-in)
    i18n.py            English + Spanish strings
    log.py             file logging (safe in windowed builds)
    tray.py            tray icon (Pillow-drawn)
    ui/                theme, widgets, pill, settings, wizard, about
  tests/               logic tests (headless)
  tools/               make_icon.py, ui_preview.py, make_demo_gif.py,
                       install_from_source.ps1
  vozlab.spec          PyInstaller definition
installer/
  deploy.ps1           one-click installer (Smart App Control safe)
  update.ps1           in-place updater
  VozLab.bat           double-click wrapper
  vozlab.iss           Inno Setup script (classic .exe installer)
.github/workflows/     ci.yml (tests) · release.yml (artifacts + GHCR) · docs.yml
```

## Packaging

| Artifact | Built by | For whom |
|---|---|---|
| `VozLab-<v>-src.zip` + `deploy.ps1` | CI on tag | everyone (SAC-safe) |
| `VozLab-Setup-<v>.exe` | Inno Setup on CI | users with Smart App Control off |
| `VozLab-<v>-portable.zip` | PyInstaller on CI | no-install portable runs |
| `ghcr.io/…/vozlab-server:<tag>` | Docker buildx on CI | server operators |
| `SHA256SUMS` | CI | verifying downloads |

Each release also publishes checksums; `deploy.ps1` verifies them before
installing.
