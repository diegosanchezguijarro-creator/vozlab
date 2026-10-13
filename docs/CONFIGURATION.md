# Configuration reference

Two configuration files exist: one for the app (your laptop) and one for the
server (the machine with Docker). Neither needs editing by hand — the app's
settings window and `install.sh` cover almost everything.

## Client — `%APPDATA%\VozLab\config.json`

Everything here is editable from the tray icon → **Settings**. The file is shown
for completeness and for advanced tweaks; the app rewrites it on save.

| Key | Default | Meaning |
|---|---|---|
| `server_host` | — | server IP or hostname (`192.168.0.23`) |
| `server_port` | `8092` | server port |
| `token` | — | the token. **Encrypted on disk** as `token_enc` (Windows DPAPI); plain text only on Linux/macOS dev machines |
| `tls_pin` | `""` | SHA-256 of the server's certificate (only used with `https://`) |
| `hotkey` | — | hardware scan code (e.g. `285` = right Ctrl) or key name |
| `hotkey_mode` | `"hold"` | `hold` (push-to-talk) or `toggle` |
| `auto_stop` | `false` | end the recording automatically after you stop speaking |
| `silence_ms` | `1200` | how long a pause ends an auto-stop recording |
| `silence_rms` | `0.012` | audio level treated as silence |
| `min_seconds` | `0.4` | recordings shorter than this are ignored |
| `max_seconds` | `60` | hard limit per recording |
| `cleanup` | `true` | ask the server to run the AI formatting pass |
| `cleanup_guard` | `true` | never let the formatter rewrite what you said |
| `style` | `"default"` | writing style: `default`, `formal`, `casual`, `concise`, `bullets` |
| `per_app_profiles` | `true` | choose the style from the app you are typing into |
| `profiles` | shipped defaults | `{"slack.exe": "casual", …}`; `null` = the built-in map |
| `vocabulary` | `[]` | names/terms the server should expect (also biases Whisper) |
| `language` | `"auto"` | language hint (`auto`, `en`, `es`, …) |
| `input_device` | `null` | microphone name; `null` follows the system default |
| `beeps` | `false` | short beeps when recording starts/stops |
| `restore_clipboard` | `true` | put your previous clipboard back after pasting |
| `ui_language` | `"auto"` | interface language: `auto`, `en`, `es` |
| `theme` | `"dark"` | `dark`, `light` or `system` |
| `show_pill` | `true` | show the floating status pill |
| `pill_position` | `"bottom-center"` | `bottom-center`, `bottom-right`, `top-right` |
| `pill_style` | `"full"` | `full` (live meter) or `minimal` (just the words) |
| `device_name` | hostname | label this device shows up as in the server's device list |
| `launch_at_login` | `false` | start with Windows |
| `check_updates` | `false` | opt-in GitHub release check |
| `debug` | `false` | verbose log, including the text you dictate |
| `config_version` | — | internal; drives settings migrations |

### Where things live

```
%APPDATA%\VozLab\config.json     your settings
%APPDATA%\VozLab\vozlab.log      log (transcripts only with debug on)
%LOCALAPPDATA%\Programs\VozLab\  the app + its virtual environment
```

Deleting `config.json` re-runs the first-run wizard. Deleting the whole
`%LOCALAPPDATA%\Programs\VozLab` folder is a clean uninstall.

## Server — `server/data/config.json`

Created on first boot with a generated token. Edit it and restart
(`docker compose restart`) — or use environment variables.

| Key | Default | Meaning |
|---|---|---|
| `token` | generated | admin secret; every request must present it. Printed once, at creation |
| `device_tokens` | `[]` | per-device tokens (salted SHA-256 hashes only). Managed from the app |
| `whisper_model` | `small` | `tiny`/`base`/`small`/`medium`/`large-v3`, add `.en` for English-only |
| `language` | `auto` | auto-detect, or force `en`, `es`, … |
| `compute_type` | `int8_float16` | GPU quantisation (`int8` on CPU) |
| `beam_size` | `5` | higher = slightly more accurate, slower |
| `vad_filter` | `true` | trim silence before transcribing; `false` is faster for short clips |
| `vocabulary` | `[]` | names/terms to bias Whisper and the formatter |
| `discovery` | `true` | answer LAN discovery probes on UDP 8093 |
| `tls_certfile` / `tls_keyfile` | — | paths to a certificate/key; `install.sh --tls` writes them |
| `cleanup` | `true` | run the LLM formatting pass |
| `cleanup_guard` | `true` | reject AI rewrites that invent words |
| `cleanup_model` | `qwen2.5:7b-instruct` | any Ollama model |
| `cleanup_base_url` | `http://host.docker.internal:11434` | where the cleanup LLM lives |
| `cleanup_temperature` | `0.0` | keep at 0 for deterministic formatting |
| `cleanup_max_tokens` | `500` | cap on the formatted output length |
| `expose_details` | `false` | `true` makes the unauthenticated `/health` verbose again (pre-1.3 behaviour) |
| `docs` | `false` | OpenAPI `/docs` stays disabled |

### Environment variables (Docker-friendly)

Set these instead of (or to override) the file — anything set here wins:

```bash
VOZLAB_TOKEN=…                  # pin the token
VOZLAB_WHISPER_MODEL=medium
VOZLAB_LANGUAGE=es
VOZLAB_COMPUTE_TYPE=int8
VOZLAB_CLEANUP=true
VOZLAB_CLEANUP_GUARD=true
VOZLAB_CLEANUP_MODEL=qwen2.5:3b-instruct
VOZLAB_CLEANUP_BASE_URL=http://ollama:11434
VOZLAB_VAD_FILTER=true          # false = faster on very short clips
VOZLAB_EXPOSE_DETAILS=false      # true = verbose /health (unauthenticated)
VOZLAB_TLS_CERT=/data/tls/cert.pem   # enables HTTPS (see install.sh --tls)
VOZLAB_TLS_KEY=/data/tls/key.pem
VOZLAB_PUBLIC_PORT=8092          # port advertised to LAN discovery
VOZLAB_DISCOVERY_PORT=8093       # UDP probe port; 0 disables discovery
VOZLAB_RATE_LIMIT=120           # requests/minute per client; 0 disables
VOZLAB_CONFIG=/data/config.json # where to read/write the file
```

Example — pin tokens and models in Compose:

```yaml
services:
  vozlab:
    image: ghcr.io/diegosanchezguijarro-creator/vozlab-server:latest
    environment:
      - VOZLAB_TOKEN=choose-something-long
      - VOZLAB_WHISPER_MODEL=small.en
      - VOZLAB_CLEANUP_MODEL=qwen2.5:3b-instruct
```

### Keeping the model resident

The server preloads Whisper at startup and keeps the cleanup model in memory
(`keep_alive: -1`), so the first dictation after a restart is as fast as the
hundredth. Ollama's own `OLLAMA_KEEP_ALIVE` is not used by VozLab.

### CPU-only tuning

```json
{
  "whisper_model": "small.en",
  "compute_type": "int8",
  "cleanup_model": "qwen2.5:3b-instruct"
}
```

Or switch cleanup off entirely (`"cleanup": false`) for the fastest possible
path — you'll see filler words and looser punctuation.
