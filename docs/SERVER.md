# Server setup

VozLab's server does the heavy lifting: speech recognition (Whisper) and the
optional text cleanup (a local LLM). It runs in Docker on any machine on your
LAN — a gaming PC, a home server, a NAS, a mini-PC.

## Requirements

| | Minimum | Recommended |
|---|---|---|
| OS | Any Linux with Docker Engine 20.10+ | Ubuntu 22.04/24.04 |
| GPU | none (CPU mode, ~5-10× slower) | NVIDIA, ≥6 GB VRAM, driver ≥550 |
| RAM | 4 GB | 8 GB+ |
| Disk | 3 GB (models + images) | 6 GB |

macOS/Windows servers are possible (Docker Desktop) but not tested.

## Install

```bash
git clone https://github.com/<your-user>/vozlab.git
cd vozlab/server
bash install.sh
```

`install.sh` detects a working NVIDIA GPU (and falls back to CPU mode if not),
builds the image, starts the container and prints:

```
Server URL : http://192.168.0.23:8092
Token      : 3xKm9Qr2Lp8VtHzWnBc4YeSfUa1DgJ6o
```

First start downloads the Whisper model (~500 MB) into `server/data/hf/`.

### Manual install

```bash
cd server
docker compose up -d --build              # GPU
docker compose -f docker-compose.yml -f docker-compose.cpu.yaml up -d --build   # CPU only
docker logs -f vozlab                     # watch startup, shows the token
```

## Connecting the app

1. Find the server's LAN IP: `hostname -I` (e.g. `192.168.0.23`)
2. In the VozLab app: **Settings → Server URL** = `http://192.168.0.23:8092`
3. **Token** = the one printed in the logs / by `install.sh`
4. Press **Test connection** — you should see the model and device.

## Settings — `server/data/config.json`

| key | default | meaning |
|---|---|---|
| `token` | auto-generated | shared secret required by every request |
| `whisper_model` | `small` | `small` = multilingual, `small.en` = faster/English-only, `medium` = more accurate (needs ~5 GB VRAM) |
| `language` | `auto` | detected per recording; set `en`, `es`… to force one |
| `compute_type` | `int8_float16` | GPU quantization; use `int8` for CPU |
| `beam_size` | `5` | higher = slightly more accurate, slower |
| `cleanup` | `true` | LLM formatting pass (filler words, punctuation) |
| `cleanup_model` | `llama3.1:8b` | any Ollama model or an OpenAI-compatible endpoint |
| `cleanup_base_url` | `http://host.docker.internal:11434` | where the cleanup LLM lives |

Restart after editing: `docker compose restart`.

### The cleanup LLM (optional but recommended)

The cleanup pass is what makes dictation feel like writing instead of
transcribing. VozLab talks to any OpenAI-compatible `/api/chat` endpoint —
[Ollama](https://ollama.com) is the easiest:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull llama3.1:8b
```

Smaller/faster alternatives: `ollama pull llama3.2:3b` then set
`"cleanup_model": "llama3.2:3b"` (good for CPU-only servers).

Set `"cleanup": false` to skip the LLM entirely (fastest, raw transcripts).

## API

| endpoint | description |
|---|---|
| `GET /health` | status, model, device (no auth) |
| `GET /version` | `{"name":"vozlab","version":"1.0.0"}` |
| `POST /transcribe` | `Authorization: Bearer <token>`; raw audio body; `?cleanup=true|false`, `?language=es` |

Example:

```bash
curl -X POST http://localhost:8092/transcribe \
     -H "Authorization: Bearer $TOKEN" \
     --data-binary @recording.wav
```

```json
{"text": "Meeting moved to Monday.", "raw_text": "um the meeting is moved to monday",
 "cleanup_used": true, "language": "en",
 "timings": {"whisper_s": 0.4, "cleanup_s": 0.6, "total_s": 1.0}}
```

## Operations

```bash
docker logs -f vozlab          # logs (shows the token at startup)
docker compose restart         # apply config changes
docker compose down            # stop
docker compose up -d --build   # update after a git pull
```

Backup/restore: `server/data/` (config + model cache). Models re-download if lost.

## Security notes

- The API is HTTP with a bearer token — intended for a **trusted LAN**. Do not
  expose port 8092 to the internet. If you need remote access, use a VPN
  (WireGuard/Tailscale) rather than port-forwarding.
- The token is the only credential; rotate it by editing `config.json` and
  restarting (`docker compose restart`), then update your clients.
