# Windows app

The Scribe app lives in your tray and turns your microphone into text in any
application: hold a key, speak, release.

## Install

1. Download `Scribe-Setup-x.y.z.exe` from the repository's **Releases** page.
2. Run it. It installs per-user (no administrator prompt) to
   `%LOCALAPPDATA%\Programs\Scribe`.
3. Optional: tick **Start Scribe automatically when I sign in**.

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
| Cancel a recording | Press `Esc` (nothing is sent to the server) |
| Copy the last dictation again | Click the pill, or tray → **Copy last dictation** |
| Pause for a meeting | Tray → **Pause for 30 min** (the icon turns into a pause symbol) |
| Open settings | Tray icon → **Settings…** |
| Change the key | Tray icon → **Change dictation key…** |
| Quit | Tray icon → **Quit** |

The floating pill shows **Listening…** while recording, **Transcribing…** while
the server works, then a brief **Done** confirmation — it never displays the
words you dictated.

## Settings

Settings are grouped in six tabs, and the **Server** tab configures the *remote*
server — no SSH, no container restart.

### Dictation
| Setting | Notes |
|---|---|
| Dictation key | any key, including media keys you never use |
| Dictation mode | hold-to-talk, or press-to-start/stop |
| Stop automatically when I stop speaking | hands-free: press once, talk, it stops itself |
| Dictation language | auto-detect, or force `en`, `es`, … |

### Audio
| Setting | Notes |
|---|---|
| Input device | pick a microphone; unplugged devices fall back to the system default |
| Input level | live meter, plus **Test microphone** (records 3 s and shows what the server heard) |
| Silence threshold / auto-stop delay | tune what counts as "you stopped talking" |
| Ignore recordings shorter than / Stop after | guards against accidental taps and runaway recordings |

### Formatting
| Setting | Notes |
|---|---|
| Format text with the local AI | off = raw Whisper output (fastest) |
| Never rewrite my words | if the formatter invents or drops words, your raw text is used instead |
| Writing style | `Default`, `Formal (email)`, `Casual (chat)`, `Concise`, `Bullet lists` — a tone hint for the formatter |
| Adjust the style per app | switch styles automatically based on the app you are typing into |
| Per-app rules | e.g. `slack.exe → Casual`, `outlook.exe → Formal`; **Use the app I'm in now** detects the current one |
| Names and terms | your name, company and product names. Comma-separated; they bias Whisper's recognition and the spell-checking, and are **Save**d to the server. They are never inserted into your text for you |

Styles only change *how* the text is written. The guard still rejects any rewrite
that adds or drops words, so a wrong profile can never corrupt a dictation.

### Server
| Setting | Notes |
|---|---|
| Find my server | broadcasts a UDP probe and lists Scribe servers on your network (no IP hunting) |
| Server URL / Token | where your server lives; use **Test connection**; the token is stored encrypted |
| Pinned certificate | with `https://` the app remembers the server certificate on first connect; **Re-pin** after re-installing the server, **Forget** to clear it |
| Speech model | `tiny` → `large-v3`; changing it reloads Whisper in the background |
| Formatting model | any model already pulled on your Ollama host |
| Apply to server / Load into memory / Run full test | change settings live, warm a model, and verify the whole chain with a built-in sample |
| Connected devices | issue a token for one machine or revoke a lost laptop; see who last used it |
| Recent server activity | the server's log, without any dictated text |

### Appearance
| Setting | Notes |
|---|---|
| Theme | dark, light, or follow Windows |
| Show floating status pill | hide it if you prefer silence |
| Pill position / style | corner, and `full` (live meter) or `minimal` (just the words) |
| Interface language | auto (follows Windows), English, Spanish |
| Sound feedback | off by default; short beeps when recording starts/stops |

### System
| Setting | Notes |
|---|---|
| Restore clipboard after pasting | your previous clipboard comes back |
| Start with Windows | autostart at login |
| Debug logging | verbose log **that also contains your words** — off by default |
| Show / Clear log | inspect or empty `%APPDATA%\Scribe\scribe.log` |
| Export / Import / Reset settings | share a configuration; the token is never exported |
| Check for updates | opt-in GitHub query — the only request that leaves your LAN |

Settings are stored in `%APPDATA%\Scribe\config.json` (the token encrypted with
DPAPI, not in clear text); the log sits next to it (tray → **Open settings
folder**).

## How the app behaves with other software

- Global hotkey works in Notepad, browsers, editors, chat apps, Office, etc.
- **Exclusive full-screen games** that read the keyboard directly will not
  deliver the hotkey; use a toggle-mode hotkey or *Dictate (toggle)* from the tray.
- The app pastes with `Ctrl+V`. In apps where `Ctrl+V` is remapped, text may not
  land — turn off *Restore clipboard after pasting* if the paste gets mangled.
- Windows can block global hooks for processes running as a different user.
  If the hotkey does nothing, try launching Scribe as administrator once.

## Updating

Install a newer `Scribe-Setup-x.y.z.exe` over the old version — settings and
logs are preserved (they live in `%APPDATA%\Scribe`, not in the install folder).

## Uninstalling

Windows *Settings → Apps → Scribe → Uninstall* (or the Start-menu uninstaller).
Your settings file is left behind; delete `%APPDATA%\Scribe` if you want it gone.
