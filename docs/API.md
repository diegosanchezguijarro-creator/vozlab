# HTTP API

Base URL: `http://<server-ip>:8092` · API version: `1` (see `/version`).

All endpoints except `/health` and `/version` require a bearer token. The admin
token is generated on first boot and printed once:

```
Authorization: Bearer <token>
```

`GET /tokens` issues extra per-device tokens (they work everywhere the admin
token does), so one machine can be revoked without touching the rest.

The interactive OpenAPI docs are **disabled** (`/docs`, `/redoc`,
`/openapi.json` all return `404`).

## `GET /health`

Cheap liveness probe. No authentication, and **deliberately minimal** — nothing
that helps an unauthenticated scanner (no models, no device, no settings):

```json
{ "ok": true, "version": "1.4.0", "api": 1 }
```

Set `"expose_details": true` in `server/data/config.json` (or
`VOZLAB_...`) to get the verbose pre-1.3 response back. The full picture lives at
`/status`, behind the token.

## `GET /version`

```json
{ "name": "vozlab", "version": "1.4.0", "api": 1 }
```

The client compares `version` with its own and warns when major.minor differ, so
users know to update the other half.

## `GET /status`

Everything the desktop app shows on its Server tab, in one call (authenticated):

```json
{
  "name": "vozlab", "version": "1.4.0", "api": 1,
  "whisper_model": "small", "language": "auto",
  "cleanup": true, "cleanup_model": "qwen2.5:7b-instruct",
  "device": "cuda", "uptime_s": 812, "requests": 24,
  "whisper_models_cached": ["faster-whisper-small", "faster-whisper-base"],
  "ollama_models": ["qwen2.5:7b-instruct", "llama3.1:8b"],
  "gpu": { "name": "NVIDIA GeForce RTX 4060", "memory_total_mb": 8188, "memory_used_mb": 4666 },
  "reloading": false,
  "tls": false,
  "auth": { "role": "device", "device": "diego-laptop" }
}
```

`auth.role` is `admin` (the main token) or `device` (a per-device token).

## `POST /transcribe`

The only real endpoint: audio in, text out.

| | |
|---|---|
| Body | raw audio bytes (WAV, MP3, OGG, FLAC — anything PyAV can decode) |
| Query | `cleanup=true\|false` (default: server setting) |
| Query | `language=en\|es\|auto…` (default: server setting) |
| Query | `style=default\|formal\|casual\|concise\|bullets` (unknown values fall back to `default`) |
| Header | `Authorization: Bearer <token>` |
| Header | `Content-Type: audio/wav` |
| Limit | 25 MB per request |

The audio is decoded in memory: nothing is written to the container's disk.

```bash
curl -X POST "http://192.168.0.23:8092/transcribe?cleanup=true" \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: audio/wav" \
     --data-binary @recording.wav
```

```json
{
  "text": "Meeting moved to Monday.",
  "raw_text": "um the meeting is moved to monday",
  "cleanup_used": true,
  "cleanup_rejected": null,
  "style": "default",
  "language": "en",
  "timings": { "whisper_s": 0.41, "cleanup_s": 0.26, "total_s": 0.69 }
}
```

`style` is echoed back (the value actually used), so the app can log which profile
was applied.

- `text` — what the client pastes. Equals `raw_text` when cleanup is off, failed,
  or was rejected by the guard.
- `cleanup_rejected` — `null`, or the reason the cleaned text was discarded
  (for example `invented 8 words (>2): ['yes', 'i', 'am']`). Useful in logs.
- `language` — the language Whisper detected or the one you forced.

### Errors

| Status | Meaning | What the client does |
|---|---|---|
| `400` | empty body | reports "nothing was recognized" |
| `401` | missing/incorrect token | tells the user to copy the token again |
| `413` | audio over 25 MB | reports the recording was too long |
| `422` | decoding/transcription failed | surfaces the message, keeps running |
| `429` | more than `VOZLAB_RATE_LIMIT` requests/minute (default 120) | asks the user to retry shortly |

## Server settings (the "unified settings" API)

The app never needs SSH: it reads and writes the server's configuration over
HTTP.

### `GET /settings`

The settings that are safe to hand to a client — **never the token**:

```json
{
  "whisper_model": "small", "language": "auto", "compute_type": "int8_float16",
  "beam_size": 5, "vad_filter": true, "cleanup": true, "cleanup_guard": true,
  "cleanup_model": "qwen2.5:7b-instruct",
  "cleanup_base_url": "http://host.docker.internal:11434",
  "cleanup_temperature": 0.0, "cleanup_max_tokens": 500,
  "vocabulary": ["VozLab", "Diego"],
  "styles": ["bullets", "casual", "concise", "default", "formal"],
  "expose_details": false, "token_set": true, "config_path": "/data/config.json"
}
```

### `PATCH /settings`

Apply changes immediately and persist them to `config.json`:

```bash
curl -X PATCH http://192.168.0.23:8092/settings \
     -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
     -d '{"whisper_model":"base","language":"es","cleanup_model":"qwen2.5:7b-instruct"}'
# {"ok": true, "applied": {...}, "reloading": false}
```

Editable: `whisper_model`, `language`, `cleanup`, `cleanup_model`,
`cleanup_guard`, `beam_size` (clamped 1–10), `compute_type`, `expose_details`,
`vad_filter`, `vocabulary` (list or `"a, b"`; de-duplicated, max 200 terms).
Anything else (including `token`) is ignored, and a request that changes nothing
returns `400`. Changing the speech model reloads Whisper in the background; watch
`reloading` in `/status`.

### `GET /models`

What you can pick from: cleanup models already pulled into Ollama, plus the
Whisper models already in the server's cache.

### `POST /models/preload`

`{"cleanup_model": "qwen2.5:7b-instruct"}` — loads a model into VRAM so the first
dictation after an idle period isn't slow. Returns `{"ok": true, "seconds": 3.1}`.

### `POST /self-test`

End-to-end check with no microphone involved: the server transcribes a sample
bundled in the image and runs the formatting pass.

```json
{
  "ok": true, "text": "If you can read this, the server works.",
  "raw_text": "For some self test. If you can read this, the server works.",
  "language": "en", "cleanup_error": null,
  "timings": { "whisper_s": 0.49, "cleanup_s": 0.25, "total_s": 0.73 },
  "device": "cuda"
}
```

### `GET /logs?lines=100`

The last lines of the server log (capped at 300). Transcripts are never logged,
so this is safe to paste in a bug report.

## Device tokens

One token per machine, so you can revoke a lost laptop without disturbing the
others. Only a salted SHA-256 hash is stored on the server.

| Endpoint | Does |
|---|---|
| `GET /tokens` | list devices: `id`, `name`, `created`, `last_used`, `last_ip`, `age_days` |
| `POST /tokens` | `{"name": "laptop"}` → `{"id": "...", "token": "..."}` (shown **once**) |
| `DELETE /tokens/{id}` | revoke that device immediately |

The admin token (`config.json`, `/tokens`, `/settings`) cannot be revoked this
way — rotate it by editing the file and restarting.

## LAN discovery (UDP, not HTTP)

The app can find the server without being told an IP address. Send
`VOZLAB/1 discover\n` to UDP **8093** (broadcast, or the subnet broadcast
address) and every VozLab server on the network answers with a small JSON object:

```json
{ "name": "vozlab", "version": "1.4.0", "api": 1, "port": 8092,
  "tls": false, "whisper_model": "small", "device": "cuda" }
```

There is **no token and no settings** in the reply, so discovery cannot be used to
dictate. Disable it with `VOZLAB_DISCOVERY_PORT=0` (or `"discovery": false`).

## Example: fully scripted setup

```bash
docker compose -f docker-compose.full.yml -f docker-compose.full.gpu.yml up -d
TOKEN=$(python3 -c 'import json;print(json.load(open("server/data/config.json"))["token"])')
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8092/status
curl -s -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8092/self-test
```
