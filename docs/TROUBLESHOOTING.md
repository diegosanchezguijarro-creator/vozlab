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

Copy the token exactly as printed by `install.sh`, or read it from `server/data/config.json` on the server.
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

## The text isn't what I said

- Dictations are logged with both versions — open the log from the tray
  (**Open settings folder → `vozlab.log`**) and compare `raw=...` (what Whisper
  heard) with the final text (what the AI formatting produced).
- If the *raw* text is wrong, it's an audio/accuracy problem: speak closer to the
  mic, and consider a bigger model (`whisper_model`: `small.en` for English-only
  is notably more accurate than the multilingual `small`; `medium` is better still).
- If the raw text is right but the final isn't, the cleanup model rewrote it —
  the server's guard normally catches this and keeps the raw text
  (`cleanup_rejected` in the log). Send me that log line if it persists.
- Turn off *Format text with the local AI* in Settings to check the raw output.

## Windows blocks the installer

Two different Windows features can do this:

**SmartScreen** — *"Windows protected your PC"*. Click **More info → Run anyway**.
Expected for unsigned software; harmless.

**Smart App Control** — *"This app can't run because it's not signed"* (Settings →
Privacy & security → Windows Security → App & browser control → Smart App Control).
There is **no bypass** — SAC only allows apps with a valid signature. Pick one:

1. **Run from source (recommended, keeps SAC enabled).** Windows allows the app
   because it is launched by your signed `pythonw.exe`:

   ```powershell
   # in the repo's client folder (requires Python 3.11+)
   powershell -ExecutionPolicy Bypass -File tools\install_from_source.ps1
   ```

   This creates a `.venv`, installs the dependencies, adds a **VozLab** Start-menu
   shortcut and launches the app. It behaves exactly like the installed build.

2. **Turn Smart App Control off** — Settings → Privacy & security → Windows
   Security → App & browser control → Smart App Control → **Off**.
   ⚠️ Microsoft warns it can only be re-enabled by resetting Windows. Only do this
   if you are comfortable with that.

3. **Sign the build** — required if you want to *share* the installer: every friend
   with SAC enabled would hit the same wall. See [BUILD.md](BUILD.md#code-signing).

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
