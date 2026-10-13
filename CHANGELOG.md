# Changelog

All notable changes to VozLab are documented here.
This project follows [Semantic Versioning](https://semver.org/).

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
