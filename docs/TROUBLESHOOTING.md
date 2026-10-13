# Troubleshooting

Check the log first: tray icon → **Open settings folder** → `vozlab.log`.
Enable **Debug logging** in Settings for per-keystroke detail.

## The hotkey does nothing

1. Make sure the app is running (tray icon present, blue mic).
2. Re-run calibration: tray → **Change dictation key…**, press your key.
3. Some apps (exclusive full-screen games, some remote-desktop sessions) swallow
   global hotkeys — try the tray menu → **Dictate (toggle)**.
4. If you run other automation tools, they may capture the key first; try another
   key (e.g. right Shift or F8).
5. Run VozLab once **as administrator** to confirm it's a permissions issue.

Debug tip (development installs): this prints every key the hook sees —

```powershell
python -c "import keyboard; keyboard.hook(lambda e: print(e.name, e.scan_code, e.event_type)); keyboard.wait()"
```

## "Cannot reach the server"

- Is the server running? On the server: `docker ps` and
  `curl http://localhost:8092/health`.
- Same network? The client and server must be on the same LAN (no guest Wi-Fi
  isolation, no VPN split-tunnelling unless configured for it).
- Correct IP? On the server: `hostname -I`. Then in the app:
  `http://<that-ip>:8092`.
- Firewall on the server blocking 8092? `sudo ufw allow 8092/tcp` (or your distro's equivalent).
- Docker not running on the server? `sudo systemctl start docker`.

## "The token was rejected" (401)

Copy the token exactly as printed by `install.sh` / `docker logs vozlab`.
Rotating the token server-side requires updating every client.

## Nothing is transcribed (empty result)

- Windows mic permission: *Settings → Privacy & security → Microphone* —
  allow desktop apps, and make sure the right input device is default.
- Speak for at least ~0.4 s; trailing silence is trimmed.
- Too quiet? Move closer or raise the input volume.
- Check the app log for `[dbg]` lines and the server log for errors.

## Transcription is slow

- Check the server log line: `loaded 'small' on cuda` (fast) vs `on cpu` (slow).
- CPU mode: expect 5–10× slower. Use `small.en` instead of `small`, or a smaller
  cleanup model (`llama3.2:3b`), or disable cleanup.
- The first request after a restart is slower (models load). VozLab preloads
  Whisper at startup and keeps the cleanup model resident.

## Text pastes into the wrong place / doesn't paste

- The text goes wherever focus is **when the paste happens**. Click into your
  document right after releasing the key.
- Apps that remap `Ctrl+V` may fail: disable *Restore clipboard after pasting*.
- The app restores your clipboard ~1 s after pasting; if you copy something in
  that window, it can be overwritten — disable the option or paste manually.

## The status pill is missing / in the wrong place

Settings → *Show floating status pill*. Position is controlled by
`pill_position` in `%APPDATA%\VozLab\config.json`
(`bottom-center`, `bottom-right`, `top-right`).

## Windows SmartScreen blocks the installer

Expected for unsigned software: **More info → Run anyway**. Code signing is on
the roadmap (`docs/BUILD.md`).

## `vozlab` container restarts in a loop (server)

- Check `docker logs vozlab`: usually a missing GPU (`nvidia-smi` not working) —
  use the CPU compose overlay, or fix the NVIDIA container toolkit.
- Out of VRAM: switch `whisper_model` to `small.en`, or set `cleanup: false`.
- Still stuck? `docker compose down && docker compose up -d --build`.

## Reset everything

Server: stop the container, edit `server/data/config.json`, start again
(models are cached in `server/data/hf/` and are only re-downloaded if deleted).

Client: delete `%APPDATA%\VozLab\config.json` — the setup wizard runs again on
next start.
