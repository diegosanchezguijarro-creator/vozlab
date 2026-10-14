# Changelog

All notable changes to VozLab are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [1.4.1] — 2026-10-14

### Fixed — the status pill on scaled displays
- The floating pill is now sized from **real font metrics** (`tkinter.font`)
  and the live DPI factor instead of a hard-coded `len(text) * 6.6` estimate.
  On a laptop with display scaling above 100% the label overflowed the box and
  the whole pill looked off-centre; it now fits and stays centred. Labels wider
  than the pill are trimmed with `…` instead of being clipped.
- The pill **no longer shows the transcribed words**. A successful dictation
  shows a neutral "Done" confirmation, so your dictated text never appears on
  screen (the full text is still pasted and kept on the clipboard).

## [1.4.0] — 2026-10-13

**The rest of the roadmap: HTTPS you can actually use, per-app styles, custom
vocabulary, LAN discovery, and an arm64 image.**

### Added — HTTPS with certificate pinning
- `install.sh --tls` generates a self-signed certificate (SANs cover the LAN IP,
  localhost and the hostname), writes `server/.env` so Compose passes
  `VOZLAB_TLS_CERT`/`VOZLAB_TLS_KEY`, and prints the fingerprint.
- The app **pins** that certificate on first connect (trust on first use) and
  refuses any other certificate afterwards — `fetch_fingerprint()`,
  `PinnedAdapter` (urllib3 `assert_fingerprint`, so pinning replaces the CA check
  and a self-signed certificate needs no warning to click through).
- A changed certificate is a hard error (`bad_cert`) with instructions, not a
  silent retry. *Settings → Server* shows the pinned fingerprint, **Re-pin** and
  **Forget**. Plain `http://` keeps working exactly as before.

### Added — per-app formatting profiles
- Five writing styles on the server (`default`, `formal`, `casual`, `concise`,
  `bullets`) sent per request as `?style=`, with the value echoed back.
- The client resolves the style from the **foreground app** (ctypes
  `GetForegroundWindow`/`QueryFullProcessImageNameW`, no dependencies) at the
  moment you stop talking, because that is where the text will land.
- Ships sensible rules for the usual apps (Outlook/Word → formal,
  Slack/Discord/Teams/WhatsApp → casual) and a UI to add, remove and detect your
  own (`"Use the app I'm in now"`).
- Styles are tone hints only: the cleanup guard still rejects any rewrite that
  invents or drops words, so a wrong profile cannot corrupt a dictation.

### Added — custom vocabulary
- A list of names and terms (your name, company, product names) that is
  **injected into the formatter prompt** and passed to Whisper as an
  `initial_prompt`.
- Measurable effect on the test corpus: the bundled sample used to transcribe
  "For some self-test"; with `VozLab` in the vocabulary it transcribes
  "VozLab self-test".
- Managed from *Settings → Formatting → Names and terms* (`PATCH /settings`,
  sanitized: de-duplicated, trimmed, capped at 200 terms).

### Added — LAN discovery
- The server answers `VOZLAB/1 discover` on UDP 8093 with its name, version, HTTP
  port, TLS flag, model and device — **never the token or any setting**.
- *Find my server* in the wizard and the Server tab broadcasts the probe and
  lists what answers (including over Docker's UDP port mapping). Disable with
  `VOZLAB_DISCOVERY_PORT=0` or `"discovery": false`.

### Added — multi-arch server image
- `linux/amd64` **and** `linux/arm64` are built and pushed per release. The
  Dockerfile now installs the CUDA wheels only on amd64 (`ARG TARGETARCH`), so
  Raspberry Pi 5 / NAS hosts get a working CPU build instead of a failed one.
- CI builds both architectures on every PR (no push) and asserts the arm64 image
  contains no CUDA wheels and imports cleanly.
- `server/check_arm64.sh`: one command for real aarch64 owners to verify
  transcription. Being explicit: arm64 builds, starts and loads the model, but we
  could not verify end-to-end inference — QEMU-emulated CTranslate2 never
  completes — so real-hardware numbers are welcome.
- `run_server.py` replaces the shell-free `uvicorn` CMD to add TLS flags from
  configuration.

### Changed
- `vad_filter` is configurable (default on). Turning it off skips an onnxruntime
  pass per request, which is worth it for very short clips.
- The client's paste shortcut is platform-aware (`⌘V` on macOS) and the
  diagnostics report lists capabilities per platform.
- Documentation: a platform support matrix (what is tested where), TLS and
  discovery sections in `REMOTE.md`/`SERVER.md`, the new keys in
  `CONFIGURATION.md`, `style`/`vocabulary`/`tls` in `API.md`.

### Fixed
- An empty `CTkFrame` kept CTk's default 200 px height, leaving a gap in the
  wizard and Server tab; the discovery and pin cards are now created lazily.
- Two more `except … as e` lambdas were about to ship with the same
  `NameError`-on-error-path bug that `ruff` caught in 1.3.0 — caught again by CI.

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
