# Server setup

Scribe's server does the heavy lifting: speech recognition (Whisper) and the
optional text cleanup (a local LLM). It runs in Docker on any machine on your
LAN — a gaming PC, a home server, a NAS, a mini-PC.

## Requirements

| | Minimum | Recommended |
|---|---|---|
| OS | Any Linux with Docker Engine 20.10+ (amd64 or arm64) | Ubuntu 22.04/24.04 |
| GPU | none (CPU mode, ~5-10× slower) | NVIDIA, ≥6 GB VRAM, driver ≥550 |
| RAM | 4 GB | 8 GB+ |
| Disk | 3 GB (models + images) | 6 GB |

### Platform support

| Platform | Image | Status |
|---|---|---|
| Linux amd64 + NVIDIA GPU | `linux/amd64` | tested (RTX 4060: ~0.4 s per dictation) |
| Linux amd64, CPU only | `linux/amd64` | tested (fallback works, `small` ≈ 3-6 s) |
| Linux arm64 (Raspberry Pi 5, NAS) | `linux/arm64` | builds in CI and starts; **transcription not verified on real hardware yet** — run `bash server/check_arm64.sh` on your Pi and report the numbers |
| macOS (Apple Silicon) | `linux/arm64` under Docker Desktop | CPU-only, community-reported; the *client* has no macOS build |
| Windows server | `linux/amd64` under WSL2/Docker Desktop | CPU mode; GPU passthrough is best-effort |

The arm64 image deliberately ships **without** the CUDA wheels (they are
amd64-only), so on a Pi you get CPU inference. `tiny`, `base` or `small.en` are
the sensible models there.

## Install

### Easiest: published image + bundled AI

```bash
git clone https://github.com/diegosg-dev/scribe.git
cd scribe/server
bash install.sh --with-ai
```

This pulls the published server image **and** Ollama, then downloads the cleanup
model automatically (~4 GB, once). Nothing else to install.

### From this checkout (builds locally, uses an Ollama you already have)

```bash
git clone https://github.com/diegosg-dev/scribe.git
cd scribe/server
bash install.sh
```

`install.sh` detects a working NVIDIA GPU (adding the GPU overlay automatically)
and falls back to CPU mode otherwise. It builds the image, starts the container
and prints:

```
Server URL : http://192.168.0.23:8092
Token      : PASTE-THE-TOKEN-PRINTED-ABOVE
```

Add `--tls` to also create a self-signed certificate and serve HTTPS (the app
pins it on first connect — see [REMOTE.md](REMOTE.md)):

```bash
bash install.sh --with-ai --tls
#  Server URL : https://192.168.0.23:8092
#  Certificate : 26:AE:6E:DD:…:5A:E7
```

First start downloads the Whisper model (~500 MB) into `server/data/hf/`.

### Manual install

```bash
cd server

# from this checkout (builds the image locally)
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d --build   # with NVIDIA GPU
docker compose -f docker-compose.yml up -d --build                            # CPU only

# or use the published image + bundled Ollama (no build, needs no local Ollama)
docker compose -f docker-compose.full.yml -f docker-compose.full.gpu.yml up -d
docker compose -f docker-compose.full.yml up -d                               # CPU only

docker logs -f scribe                     # watch startup, shows the token
```

GPU support is **opt-in** (`docker-compose.gpu.yml`): the base stacks always run
on CPU, so a machine without an NVIDIA GPU (or without the container toolkit)
starts cleanly instead of failing on a device request.

## Connecting the app

1. Find the server's LAN IP: `hostname -I` (e.g. `192.168.0.23`)
2. In the Scribe app: **Settings → Server URL** = `http://192.168.0.23:8092`
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
| `cleanup_guard` | `true` | reject LLM rewrites that invent words and keep the raw transcript |
| `cleanup_model` | `llama3.1:8b` | any Ollama model or an OpenAI-compatible endpoint |
| `cleanup_base_url` | `http://host.docker.internal:11434` | where the cleanup LLM lives |

Restart after editing: `docker compose restart`.

### The cleanup LLM (optional but recommended)

The cleanup pass is what makes dictation feel like writing instead of
transcribing. Scribe talks to any OpenAI-compatible `/api/chat` endpoint —
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
| `GET /version` | `{"name":"scribe","version":"1.0.0"}` |
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
docker logs -f scribe          # logs (shows the token at startup)
docker compose restart         # apply config changes
docker compose down            # stop
docker compose up -d --build   # update after a git pull
```

Backup/restore: `server/data/` (config + model cache). Models re-download if lost.

## Discovery

The container publishes UDP **8093** and answers `SCRIBE/1 discover` probes with
its name, version, HTTP port and TLS flag (never the token), so the app's *Find my
server* button works. Set `SCRIBE_DISCOVERY_PORT=0` to switch it off.

## Security notes

- The API is HTTP with a bearer token — intended for a **trusted LAN**. Do not
  expose port 8092 to the internet. If you need remote access, use a VPN
  (WireGuard/Tailscale) rather than port-forwarding.
- The token is the only credential; rotate it by editing `config.json` and
  restarting (`docker compose restart`), then update your clients.
