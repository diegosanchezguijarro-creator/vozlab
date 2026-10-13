# Building VozLab

## Automatically (GitHub Actions)

1. Bump `VERSION` in `client/vozlab/__init__.py` and add a `CHANGELOG.md` entry.
2. Commit, then tag and push:

```bash
git tag v1.0.1
git push origin v1.0.1
```

3. The **Release** workflow (`.github/workflows/release.yml`) builds on
   `windows-latest`:
   - runs the test suite,
   - builds the app with PyInstaller,
   - builds the installer with Inno Setup (installed via Chocolatey),
   - creates a portable `.zip`,
   - publishes a GitHub Release with both artifacts.

The workflow fails fast if the tag doesn't match `VERSION` in the code.

## Locally on Windows

```powershell
cd client
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
python run_vozlab.py            # run from source (dev mode)
pyinstaller vozlab.spec --noconfirm
# -> dist\VozLab\VozLab.exe
```

Then the installer (requires [Inno Setup 6](https://jrsoftware.org/isdl.php)):

```powershell
cd ..\installer
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" /DAppVersion=1.0.1 vozlab.iss
# -> installer\output\VozLab-Setup-1.0.1.exe
```

## Locally on Linux/macOS (for testing, not for shipping)

The app is Windows-targeted, but the code runs elsewhere for development:

```bash
cd client
sudo apt-get install -y libportaudio2      # PortAudio for sounddevice
python -m pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q
pyinstaller vozlab.spec --noconfirm        # produces a Linux binary
```

## Icon

`client/assets/icon.ico` is generated programmatically:
`tools/make_icon.py` (requires Pillow).

## Project layout

```
client/
  vozlab/
    __init__.py     version + app name
    app.py          orchestrator (tray + hotkeys + recorder + overlay)
    audio.py        microphone recording, silence-based auto-stop
    hotkeys.py      global hotkey hooking + key calibration
    api.py          HTTP client for the server
    config.py       settings storage (%APPDATA%\VozLab\config.json)
    i18n.py         English/Spanish strings
    log.py          file logging (works in windowed builds)
    overlay.py      floating status pill (tkinter)
    settings_ui.py  settings window + first-run wizard
    tray.py         pystray tray icon (icons drawn with Pillow)
  tests/            pytest suite (headless, no audio hardware needed)
  assets/           icon.ico / icon.png
  vozlab.spec       PyInstaller build definition
installer/vozlab.iss  Inno Setup script
server/               Dockerised transcription + cleanup service
```

## Release checklist

- [ ] `VERSION` bumped in `client/vozlab/__init__.py`
- [ ] `CHANGELOG.md` updated
- [ ] CI green on `main`
- [ ] Tag pushed (`vX.Y.Z`)
- [ ] Release artifacts downloaded and smoke-tested on a clean Windows machine
- [ ] README screenshot/GIF up to date
