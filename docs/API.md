# HTTP API

Base URL: `http://<server-ip>:8092` · API version: `1` (see `/version`).

All endpoints except `/health` and `/version` require the bearer token that the
server generates on first boot:

```
Authorization: Bearer <token>
```

## `GET /health`

Cheap liveness probe. No authentication, no secrets — safe for a monitoring
tool.

```json
{
  "ok": true,
  "version": "1.2.0",
  "api": 1,
  "whisper_model": "small",
  "language": "auto",
  "cleanup": true,
  "cleanup_model": "qwen2.5:7b-instruct",
  "device": "cuda"
}
```

`device` is `cuda` when a GPU was found, otherwise `cpu`.

## `GET /version`

```json
{ "name": "vozlab", "version": "1.2.0", "api": 1 }
```

The client compares `version` with its own and warns when major.minor differ, so
users know to update the other half.

## `POST /transcribe`

The only real endpoint: audio in, text out.

| | |
|---|---|
| Body | raw audio bytes (WAV, MP3, OGG, FLAC — anything PyAV can decode) |
| Query | `cleanup=true\|false` (default: server setting) |
| Query | `language=en\|es\|auto…` (default: server setting) |
| Header | `Authorization: Bearer <token>` |
| Header | `Content-Type: audio/wav` |
| Limit | 25 MB per request |

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
  "language": "en",
  "timings": { "whisper_s": 0.41, "cleanup_s": 0.26, "total_s": 0.69 }
}
```

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

## Server settings

Right now the server reads `data/config.json` (or `VOZLAB_*` environment
variables) at startup — the planned `GET/PATCH /settings` API will let the app
change models and language without SSH.

## Example: fully scripted setup

```bash
docker compose -f docker-compose.full.yml -f docker-compose.full.gpu.yml up -d
TOKEN=$(docker logs vozlab 2>&1 | grep -A1 'TOKEN' | tail -1 | tr -d ' ')
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8092/health
```
