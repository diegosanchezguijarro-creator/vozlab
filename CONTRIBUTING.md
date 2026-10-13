# Contributing to VozLab

Thanks for helping! Bug reports, docs fixes, translations and code are all
welcome.

## Quick orientation

| I want to… | Read |
|---|---|
| run the server locally | [docs/SERVER.md](docs/SERVER.md) |
| run the client from source | [docs/BUILD.md](docs/BUILD.md) |
| understand the code layout | [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) |
| add a translation | below, "Translations" |
| report a security issue | [SECURITY.md](SECURITY.md) |

## Development setup

**Client** (any OS for development; Windows for the real thing):

```bash
cd client
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests -q          # 30 logic tests, no audio hardware needed
python run_vozlab.py               # run the tray app
```

**Server**:

```bash
cd server
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build
docker logs -f vozlab
```

**Server tests** (no Docker needed):

```bash
cd server && python -m pytest tests -q
```

### Previewing the UI without Windows

Every window renders with demo data, headless:

```bash
sudo apt-get install -y xvfb imagemagick
Xvfb :99 -screen 0 1440x900x24 &
cd client
DISPLAY=:99 python tools/ui_preview.py --lang es         # look at it
DISPLAY=:99 python tools/ui_preview.py --shot            # write docs/images/*.png
DISPLAY=:99 python tools/make_demo_gif.py                # regenerate demo.gif
```

## What CI checks

Every pull request runs on Linux **and** Windows:

- byte-compilation of all modules,
- `pytest` for the client (30 tests) and the server (17 tests),
- compose-file validation (including "the base stacks never request a GPU"),
- on tags: PyInstaller build, Inno Setup installer, source zip, checksums, and the
  GHCR server image.

Run the same things locally before pushing: `python -m pytest tests -q` in both
`client/` and `server/`.

## Translations

The UI is English/Spanish today and the strings live in one file:
[`client/vozlab/i18n.py`](client/vozlab/i18n.py). To add a language:

1. copy the `"en"` dictionary to a new key (e.g. `"fr"`),
2. translate the values (keep `{placeholders}` intact),
3. add the code to the language pickers in `ui/settings_window.py`
   (`LANGUAGES` and the UI-language `CTkOptionMenu` values),
4. check parity: `python -c "from vozlab import i18n; print(set(i18n.STRINGS['en']) ^ set(i18n.STRINGS['fr']))"` should print an empty set.

`client/tools/ui_preview.py --lang fr` renders it for a screenshot.

## Style

- Keep the client dependency-light: `customtkinter`, `sounddevice`, `numpy`,
  `keyboard`, `requests`, `pyperclip`, `pystray`, `pillow`. Please ask before
  adding a new one.
- Comment the *why*, not the *what* — especially around Windows quirks (hook
  timeouts, scan codes, Smart App Control).
- No network calls outside your server. Anything that contacts the internet must
  be opt-in and documented in `docs/PRIVACY.md`.

## Pull requests

1. Fork, branch from `main` (`feat/…`, `fix/…`, `docs/…`).
2. Keep the diff focused; update docs and `CHANGELOG.md` when behaviour changes.
3. Make sure the test suites pass, and say in the description what you tested on
   real hardware (Windows version, GPU).
4. If you changed a default, note it in the PR so it can be mentioned in the
   release notes.

## Good first issues

- Add a Spanish/other-language README tweak.
- More model presets in `docs/MODELS.md`.
- Extra dictation cases in `server/tools/benchmark_cleanup.py`.
- Docs typos anywhere — small PRs are very welcome.
