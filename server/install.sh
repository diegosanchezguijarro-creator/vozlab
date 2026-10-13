#!/usr/bin/env bash
# VozLab server installer — gets a local dictation server running with one command.
#
#   bash install.sh
#
# Detects NVIDIA GPU (fast) vs CPU-only (slower), builds and starts the container,
# then prints the URL and token to paste into the VozLab Windows app.
set -euo pipefail
cd "$(dirname "$0")"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || die "Docker is not installed. See https://docs.docker.com/engine/install/"
docker info >/dev/null 2>&1 || die "Cannot talk to the Docker daemon. Is it running? (try: sudo systemctl start docker)"
docker compose version >/dev/null 2>&1 || die "The 'docker compose' plugin is missing. Install docker-compose-plugin."

COMPOSE=(docker compose -f docker-compose.yml)

if command -v nvidia-smi >/dev/null 2>&1 && nvidia-smi >/dev/null 2>&1; then
  say "NVIDIA GPU detected — using GPU mode (fast)"
else
  warn "No working NVIDIA GPU/driver detected — falling back to CPU mode (slower)."
  COMPOSE+=(-f docker-compose.cpu.yaml)
fi

say "Building and starting VozLab (first run downloads the Whisper model, ~500 MB)"
mkdir -p data
"${COMPOSE[@]}" up -d --build

say "Waiting for the server to load the model..."
for _ in $(seq 1 60); do
  if curl -fsS http://localhost:8092/health >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

say "Server status"
curl -fsS http://localhost:8092/health || warn "Server is still starting — check: docker logs -f vozlab"

LAN_IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
TOKEN="$(python3 -c 'import json;print(json.load(open("data/config.json"))["token"])' 2>/dev/null \
        || grep -o '"token": *"[^"]*"' data/config.json | cut -d'"' -f4)"

cat <<EOF

$(printf '\033[1;32m')
  ┌──────────────────────────────────────────────────────────────┐
  │  VozLab server is running!                                   │
  └──────────────────────────────────────────────────────────────┘

  In the VozLab Windows app, connect to:

      Server URL : http://${LAN_IP:-<this-machine-IP>}:8092
      Token      : ${TOKEN:-see: docker logs vozlab}

  Handy:
      docker logs -f vozlab          # live logs
      docker compose restart         # restart
      docker compose down            # stop

  Settings live in: server/data/config.json  (restart after editing)
EOF
