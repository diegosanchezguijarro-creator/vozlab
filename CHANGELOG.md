# Changelog

All notable changes to VozLab are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [1.3.0] — 2026-10-13

**Security, unified settings and a real settings overhaul.** Everything from C, D
and E of the roadmap that a self-hoster actually feels: the app configures the
server, secrets stop living in plain text, and the whole UI gets themes, tabs and
translations in JSON.

### Security
- **The token is encrypted at rest on Windows** (`secretstore.py`, DPAPI via
  ctypes — no extra dependency). `config.json` now stores `token_enc`; older
  plain-text configs are migrated on the next save. A copied config file is
  useless on another account.
- **Per-device tokens**: *Settings → Server → Connected devices* issues a token
  for one machine; only a salted SHA-256 hash is kept on the server and the value
  is shown once. Revoke a stolen laptop without touching the others.
- **Dictated text no longer reaches `vozlab.log`.** The log records timings,
  language and length; only *Debug logging* (off) records the words. Every line
  is additionally scrubbed of the token, `Bearer …` headers and `"token": "…"`.
- **No audio on disk, anywhere.** The server decodes the uploaded bytes in memory
  (`io.BytesIO` → faster-whisper), so there is no temporary file to leak.
- **Minimal unauthenticated surface**: `/health` returns only
  `{"ok", "version", "api"}`; models, device, GPU and counters moved behind the
  token at `/status`. OpenAPI docs are disabled. Requests are rate limited
  (`VOZLAB_RATE_LIMIT`, default 120/min) and token checks are constant-time.
- **The token is printed once**, when it is created — not on every restart, so it
  stops piling up in `docker logs`/journald.
- **Container hardening**: non-root (uid 1000), read-only root filesystem,
  `no-new-privileges`, all capabilities dropped, base image pinned by digest.
- **Fixed dependency CVEs** found by the new `pip-audit` job (`requests`,
  `starlette`/`fastapi`); removed an unused dependency.

### Added — unified settings (the app configures your server)
- `GET/PATCH /settings`, `GET /models`, `POST /models/preload`, `POST /self-test`,
  `GET /logs`, `GET/POST /tokens`, `DELETE /tokens/<id>`.
- The app's **Server tab** changes the speech model, language, formatting model
  and cleanup on the server live — no SSH, no restart. Whisper reloads in the
  background and `/status` reports progress.
- **Run full test** transcribes a sample bundled in the image end to end and
  reports the timings; **Load into memory** warms a formatting model.
- Server activity and device list, right in the app.

### Added — settings overhaul
- Six tabs: **Dictation · Audio · Formatting · Server · Appearance · System**.
- Audio: input-device picker (devices that vanished fall back to the default),
  live input meter, *Test microphone* that records 3 s and shows what the server
  heard, and sliders-in-numbers for silence and length limits.
- System: app-log viewer, **Clear log**, export/import settings (never the token),
  reset to defaults, diagnostics, updates.
- Import is defensive: unknown keys are dropped and the token always stays local.

### Added — look, feel and languages
- **Dark / light / follow-Windows themes** (two full palettes with a contrast
  test in the suite).
- Pill styles (**full** with the live meter, or **minimal**), an elapsed-seconds
  counter while you talk, and **click the pill to copy** the last dictation.
- Tray: **Copy last dictation**, **Pause for 30 min** (with a pause icon), and
  Esc now **cancels** a recording instead of sending it.
- i18n moved to `client/vozlab/locales/{en,es}.json`; a test enforces that every
  language has the same keys and the same `{placeholders}`. Adding a language is
  now a single JSON file.

### Added — enforcement in CI
- `Security` workflow: **ruff** (it caught real `except … as e` scope bugs),
  **bandit**, **gitleaks**, **pip-audit**, and a job that fails if the Dockerfile
  and `requirements.txt` drift apart.
- **Dependabot** for pip, Docker and GitHub Actions.
- Every release publishes an **SBOM** (`vozlab-server-<version>.spdx.json`).
- **Soak tests** (`client/tests/test_soak.py`) drive 200 recording cycles and 50
  hotkey restarts to catch thread/memory leaks. They found two real ones: a
  worker thread leaked per hotkey restart, and shared mutable state between
  configs.

### Fixed
- `except ... as e` lambdas in the error paths raised `NameError` instead of
  showing the message (Python deletes the name at the end of the block).
- `HotkeyManager.stop()` never joined its worker, so a restart left two workers.
- `dict(DEFAULT_CONFIG)` shared the `device_tokens` list between configs.
- A wrong token used to report "Connected" in the settings status line, because
  the fallback to the then-verbose `/health` succeeded.

### Docs
- `docs/API.md` documents the whole surface (with real payloads), `docs/PRIVACY.md`
  states exactly what is stored and how to verify it, `docs/REMOTE.md` covers VPN
  access. The committed MkDocs build output was removed from git.

## [1.2.0] — 2026-10-13

**A release aimed at strangers on the internet: installable without code signing,
documented end to end.**

### Added — distribution
- `installer/deploy.ps1`: one-click installer that works **with Smart App Control
  enabled**. Downloads the release source, verifies its SHA256 against
  `SHA256SUMS`, builds a private virtual environment and launches the app with the
  signed `pythonw.exe`. Plus `VozLab.bat` (double-click) and `update.ps1`
  (in-place updates that keep your settings).
- Release workflow now publishes `VozLab-<v>-src.zip` and `SHA256SUMS`, and builds
  + pushes `ghcr.io/<owner>/vozlab-server:<tag|latest>` so the server needs no
  local build.
- `docker-compose.full.yml`: all-in-one stack (server + Ollama + model preload).
- `install.sh --with-ai` / `--cpu` / `--help` with preflight checks.

### Added — client
- `updater.py` and in-app update flow: *Check now*, *Update now* (runs the
  updater), and an opt-in automatic check. **Off by default — zero telemetry.**
- `diagnostics.py` + *Settings → System → Export diagnostics*: a support report
  with the token and every dictated word removed, plus *Report a problem* and
  *Documentation* buttons.
- Server/client version-mismatch warning with upgrade instructions.

### Added — documentation
- Complete README rewrite (two-track quick start, screenshots, latency tables,
  privacy, FAQ, roadmap) and a Spanish mirror (`README.es.md`).
- New guides: `ARCHITECTURE`, `API`, `CONFIGURATION`, `MODELS`, `PRIVACY`,
  `REMOTE`, `FAQ`, plus `CONTRIBUTING`, `SECURITY`, `CODE_OF_CONDUCT`, issue and
  PR templates.
- Docs site (MkDocs Material) with a GitHub Pages workflow.
- Animated demo GIF generated from the real UI, and regenerated screenshots.

### Changed
- GPU support is **opt-in** in Compose (`.gpu.yml` overlays) because Compose
  cannot remove device reservations in an override — CPU-only machines now start
  cleanly on the base files.
- Default cleanup model is **`qwen2.5:7b-instruct`** (Apache-2.0) instead of
  `llama3.1:8b` (Meta licence): same 8/8 quality score and 0.25 s latency in the
  benchmark, better Spanish punctuation, friendlier licence for redistribution.
- The cleanup guard is now accent-insensitive, so restoring accents in Spanish
  ("que tal" → "¿qué tal?") is no longer mistaken for inventing words.
- `/version` and `/health` expose `api: 1`; `VOZLAB_*` environment variables can
  override any server setting.

### Fixed
- Spanish text is no longer rejected by the cleanup guard when the model adds
  accents.
- `deploy.ps1`-installed apps are updated in place instead of being duplicated.

## [1.1.1] — 2026-10-13

### Changed
- **Sound feedback is now off by default.** No more beeps out of the box; turn it
  on any time in *Settings → System → Sound feedback*. Existing configs are
  migrated once (a `config_version` field) so installed copies go quiet too,
  unless you had explicitly enabled it.
- Settings: the switch now has a short description.

## [1.1.0] — 2026-10-13

### Added
- **Complete UI redesign** (CustomTkinter): dark, modern interface throughout
  - animated status pill with a **live microphone level meter** and pulsing
    "transcribing" indicator, real rounded corners and fade in/out
  - settings window rebuilt as grouped cards (Connection, Dictation, Local AI
    formatting, Appearance, System) with a live connection indicator, toggle
    switches, segmented controls and a key-cap style hotkey display
  - first-run wizard with progress dots, step titles and an in-line microphone
    test that shows the live level while recording
  - styled About window
- UI preview tool (`client/tools/ui_preview.py`) to render every window with
  demo data — works headless (Xvfb) for screenshots and development on Linux
- Screenshots in `docs/images/` (English + Spanish)

### Changed
- Requires `customtkinter`; PyInstaller spec collects its theme assets
- Spanish and English strings for all new UI text

## [1.0.2] — 2026-10-13

### Fixed
- **The AI formatting pass could "answer" dictated questions.** Saying
  *"are you responding to me?"* produced *"Yes, I am responding to you."* because
  the cleanup model treated the transcript as a conversation. The cleanup prompt
  now forbids replying (with question examples), and a new server-side guard
  rejects any rewrite that invents words, falling back to the raw transcript.
- Whisper: `condition_on_previous_text=False` for dictation clips (reduces
  invented text on short/quiet audio).

### Added
- Server: `cleanup_guard` setting, `cleanup_rejected` field in `/transcribe`
  responses, and a test suite for the cleanup prompt + guard (15 tests).
- Client: dictations are logged with both the raw and the formatted text
  (`%APPDATA%\VozLab\vozlab.log`), and rejections are reported in the log.

## [1.0.1] — 2026-10-13

### Fixed
- **Dictation always failed with "recording too short"**: the recorder cleared its
  audio buffer before the app asked how long the recording was, so every clip
  measured 0 s and was discarded. The finished recording's duration is now
  remembered on stop. (Regression tests added.)
- CI: bumped `actions/checkout` and `actions/setup-python` to versions that no
  longer run on the deprecated Node 20 runtime.

## [1.0.0] — 2026-10-13

First public release.

### Client (Windows)
- System tray application with state-aware icon (idle / listening / transcribing / offline)
- Floating status pill showing live state and a preview of the transcribed text
- First-run wizard: server connection test, dictation-key calibration, microphone test
- Push-to-talk and toggle modes; optional auto-stop on silence
- Hotkey matching by hardware scan code (works on any keyboard layout/language) with
  localized-name fallbacks
- Clipboard-safe pasting (restores your previous clipboard)
- Settings window (EN/ES) with start-with-Windows support
- File logging to `%APPDATA%\VozLab\vozlab.log`

### Server
- FastAPI service with `/transcribe`, `/health`, `/version`
- faster-whisper (CTranslate2) with CUDA auto-detection and CPU fallback
- Multilingual: `small` model + automatic language detection, per-request language override
- Optional LLM cleanup pass via Ollama (`llama3.1:8b` by default), language-preserving prompt
- Zero-config first boot: token generated automatically and printed in the logs
- 25 MB request cap, bearer-token auth, GPU/CPU compose files, one-command `install.sh`

### Tooling
- PyInstaller spec, Inno Setup installer (per-user, no admin prompt)
- GitHub Actions: tests on Linux + Windows, tag-driven release build
