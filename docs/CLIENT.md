# Windows app

The VozLab app lives in your tray and turns your microphone into text in any
application: hold a key, speak, release.

## Install

1. Download `VozLab-Setup-x.y.z.exe` from the repository's **Releases** page.
2. Run it. It installs per-user (no administrator prompt) to
   `%LOCALAPPDATA%\Programs\VozLab`.
3. Optional: tick **Start VozLab automatically when I sign in**.

> Windows SmartScreen will warn about an unknown publisher on first run
> (the app is not code-signed): **More info → Run anyway**.

## First-run wizard

1. **Server** — paste the URL and token your server printed
   (e.g. `http://192.168.0.23:8092`), then **Test connection**.
   A green "Connected! Model: small on cuda" means you're done here.
2. **Dictation key** — press the key you want to use (e.g. **right Ctrl**).
   The app stores the key's hardware code, so it keeps working if you change
   Windows display language or keyboard layout.
3. **Microphone** — record 3 seconds and see the transcription. If it's empty,
   check Windows *Settings → Privacy & security → Microphone*.

Click **Finish** — the app minimises to the tray and starts listening.

## Daily use

| Action | How |
|---|---|
| Dictate | Hold your key, speak, release (default mode) |
| Dictate (toggle mode) | Press the key to start, press again to stop |
| Cancel a recording | Press `Esc`… or just stay silent (auto-stop, if enabled) |
| Open settings | Tray icon → **Settings…** |
| Change the key | Tray icon → **Change dictation key…** |
| Quit | Tray icon → **Quit** |

The floating pill shows **Listening…** while recording, **Transcribing…** while
the server works, then a short preview of your text.

## Settings

| Setting | Notes |
|---|---|
| Server URL / Token | where your server lives; use **Test connection** |
| Dictation key | any key, including media keys you never use |
| Dictation mode | hold-to-talk, or press-to-start/stop |
| Stop automatically when I stop speaking | hands-free: press once, talk, it stops itself |
| Format text with the local AI | off = raw Whisper output (fastest) |
| Dictation language | auto-detect, or force `en`, `es`, … |
| Interface language | auto (follows Windows), English, Spanish |
| Sound feedback | off by default; short beeps when recording starts/stops |
| Restore clipboard after pasting | your previous clipboard comes back |
| Show floating status pill | hide it if you prefer silence |
| Start with Windows | autostart at login |
| Debug logging | verbose log in `%APPDATA%\VozLab\vozlab.log` |

Settings are stored in `%APPDATA%\VozLab\config.json`; the log sits next to it
(tray → **Open settings folder**).

## How the app behaves with other software

- Global hotkey works in Notepad, browsers, editors, chat apps, Office, etc.
- **Exclusive full-screen games** that read the keyboard directly will not
  deliver the hotkey; use a toggle-mode hotkey or *Dictate (toggle)* from the tray.
- The app pastes with `Ctrl+V`. In apps where `Ctrl+V` is remapped, text may not
  land — turn off *Restore clipboard after pasting* if the paste gets mangled.
- Windows can block global hooks for processes running as a different user.
  If the hotkey does nothing, try launching VozLab as administrator once.

## Updating

Install a newer `VozLab-Setup-x.y.z.exe` over the old version — settings and
logs are preserved (they live in `%APPDATA%\VozLab`, not in the install folder).

## Uninstalling

Windows *Settings → Apps → VozLab → Uninstall* (or the Start-menu uninstaller).
Your settings file is left behind; delete `%APPDATA%\VozLab` if you want it gone.
