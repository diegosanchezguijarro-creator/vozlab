# Scribe client

Windows tray app for [Scribe](../README.md): hold a key, speak, release — your
words are transcribed by your own server and pasted into the focused app.

- **Users:** see [../docs/CLIENT.md](../docs/CLIENT.md)
- **Developers:** `pip install -r requirements-dev.txt && python run_vozlab.py`
- **Tests:** `python -m pytest tests -q`
- **Build the .exe / installer:** [../docs/BUILD.md](../docs/BUILD.md)

```
vozlab/
  app.py          orchestrator: tray + hotkey + recorder + overlay + paste
  audio.py        mic capture, silence-based auto-stop
  hotkeys.py      global hook (scan-code matching) + key calibration
  api.py          server client (/health, /transcribe)
  config.py       %APPDATA%\VozLab\config.json
  i18n.py         English / Spanish UI strings
  log.py          file logging (safe in windowed builds)
  overlay.py      floating status pill
  settings_ui.py  settings window + first-run wizard
  tray.py         tray icon (Pillow-drawn icons)
```
