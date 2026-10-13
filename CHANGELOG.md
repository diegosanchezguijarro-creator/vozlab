# Changelog

All notable changes to VozLab are documented here.
This project follows [Semantic Versioning](https://semver.org/).

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
