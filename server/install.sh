#!/usr/bin/env bash
# VozLab server installer — one command to a working local dictation server.
#
#   bash install.sh                     # build from this checkout (auto GPU/CPU)
#   bash install.sh --with-ai           # published image + Ollama + model (easiest)
#   bash install.sh --with-ai --cpu     # same, without an NVIDIA GPU
#   VOZLAB_VERSION=1.1.2 bash install.sh --with-ai
#
# Prints the URL and token to paste into the VozLab desktop app.
set -euo pipefail
cd "$(dirname "$0")"

WITH_AI=false
CPU=false
for arg in "$@"; do
  case "$arg" in
    --with-ai) WITH_AI=true ;;
    --cpu) CPU=true ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) echo "unknown option: $arg (try --help)" >&2; exit 1 ;;
  esac
done

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

# ------------------------------------------------------------- preflight ----
command -v docker >/dev/null 2>&1 || die "Docker is not installed. See https://docs.docker.com/engine/install/"
docker info >/dev/null 2>&1 || die "Cannot talk to the Docker daemon. Is it running? (try: sudo systemctl start docker)"
docker compose version >/dev/null 2>&1 || die "The 'docker compose' plugin is missing (install docker-compose-plugin)."

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  HAS_GPU=true
  GPU_NAME="$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1)"
else
  HAS_GPU=false
fi

# ------------------------------------------------------------ compose args --
COMPOSE=(docker compose)
if $WITH_AI; then
  COMPOSE+=(-f docker-compose.full.yml)
  if $HAS_GPU && ! $CPU; then
    COMPOSE+=(-f docker-compose.full.gpu.yml)
  fi
else
  COMPOSE+=(-f docker-compose.yml)
  if $HAS_GPU && ! $CPU; then
    COMPOSE+=(-f docker-compose.gpu.yml)
  fi
fi

if $HAS_GPU && ! $CPU; then
  say "NVIDIA GPU detected${GPU_NAME:+: $GPU_NAME} — using GPU mode (fast)"
else
  if $CPU; then
    warn "CPU mode forced with --cpu (slower, but works)."
  else
    warn "No working NVIDIA GPU/driver detected — falling back to CPU mode (slower)."
  fi
  warn "Tip: whisper_model 'small.en' and cleanup_model 'qwen2.5:3b-instruct' are much faster on CPU."
fi

# ------------------------------------------------------------------- start --
mkdir -p data
if $WITH_AI; then
  say "Starting VozLab + Ollama (first run downloads images and the model, ~5 GB)"
else
  say "Building and starting VozLab from this checkout"
fi
"${COMPOSE[@]}" up -d --build 2>/dev/null || "${COMPOSE[@]}" up -d

say "Waiting for the server to load the Whisper model..."
for _ in $(seq 1 80); do
  if curl -fsS http://localhost:8092/health >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

say "Server status"
curl -fsS http://localhost:8092/health && echo || warn "Still starting — check: docker logs -f vozlab"

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
TOKEN="$(python3 -c 'import json;print(json.load(open("data/config.json"))["token"])' 2>/dev/null \
        || grep -o '"token": *"[^"]*"' data/config.json 2>/dev/null | cut -d'"' -f4 \
        || true)"

cat <<EOF

$(printf '\033[1;32m')
  ┌──────────────────────────────────────────────────────────────┐
  │  VozLab server is running!                                   │
  └──────────────────────────────────────────────────────────────┘

  In the VozLab app, connect to:

      Server URL : http://${LAN_IP:-<this-machine-IP>}:8092
      Token      : ${TOKEN:-see: docker logs vozlab}

  Handy:
      docker logs -f vozlab      # live logs (token is printed at startup)
      docker compose $( $WITH_AI && echo '-f docker-compose.full.yml ' )restart
      docker compose $( $WITH_AI && echo '-f docker-compose.full.yml ' )down

  Client (Windows): https://github.com/diegosanchezguijarro-creator/vozlab#install
  Docs            : https://github.com/diegosanchezguijarro-creator/vozlab/tree/main/docs
EOF
