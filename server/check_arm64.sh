#!/usr/bin/env bash
# Verify an arm64 (Raspberry Pi 5 / NAS) VozLab server end to end.
#
# We build the arm64 image in CI, where the only thing we can do is run it under
# QEMU emulation — and emulated CTranslate2 inference does not complete, so this
# script exists for people with real aarch64 hardware.
#
#   bash check_arm64.sh              # uses the published image
#   VOZLAB_VERSION=1.4.0 bash check_arm64.sh
#
# It builds a container, waits for the model, posts the bundled sample to
# /transcribe, and prints what came back. Expect a couple of seconds per
# dictation with `small` on a Pi 5, longer with `medium`.
set -euo pipefail
cd "$(dirname "$0")"

IMAGE="ghcr.io/diegosanchezguijarro-creator/vozlab-server:${VOZLAB_VERSION:-latest}"
PORT="${VOZLAB_PORT:-8092}"

say()  { printf '\n\033[1;36m==> %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33mWARNING: %s\033[0m\n' "$*"; }
die()  { printf '\033[1;31mERROR: %s\033[0m\n' "$*" >&2; exit 1; }

case "$(uname -m)" in
  aarch64|arm64) ;;
  *) warn "This machine is $(uname -m), not arm64 — results will reflect emulation." ;;
esac

command -v docker >/dev/null 2>&1 || die "Docker is not installed"
mkdir -p data
chown -R 1000:1000 data 2>/dev/null || warn "could not chown ./data (try: sudo chown -R 1000:1000 data)"

say "Starting $IMAGE"
docker rm -f vozlab-arm-check >/dev/null 2>&1 || true
docker run --rm -d --name vozlab-arm-check \
  -p "${PORT}:8080" -p "8093:8093/udp" \
  -v "${PWD}/data:/data" \
  --user 1000:1000 --read-only --tmpfs /tmp:size=512m \
  --security-opt no-new-privileges:true --cap-drop ALL \
  -e VOZLAB_PUBLIC_PORT="${PORT}" \
  --add-host host.docker.internal:host-gateway \
  "$IMAGE" >/dev/null

cleanup() { docker rm -f vozlab-arm-check >/dev/null 2>&1 || true; }
trap cleanup EXIT

say "Waiting for the model (a Pi needs 30-90 s the first time)"
for _ in $(seq 1 100); do
  if curl -fsS "http://localhost:${PORT}/health" >/dev/null 2>&1; then break; fi
  sleep 3
done
curl -fsS "http://localhost:${PORT}/health" || die "the server never became healthy — check: docker logs vozlab-arm-check"
echo

TOKEN="$(python3 -c 'import json;print(json.load(open("data/config.json"))["token"])' 2>/dev/null \
        || grep -o '"token": *"[^"]*"' data/config.json | cut -d'"' -f4 || true)"
[ -n "$TOKEN" ] || die "no token in ./data/config.json"

say "Running the built-in end-to-end test (decode + Whisper + LLM cleanup)"
START=$(date +%s)
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  "http://localhost:${PORT}/self-test" || die "self-test failed — check: docker logs vozlab-arm-check"
echo
END=$(date +%s)

say "Text you dictate (same path, with a real microphone recording)"
curl -fsS -X POST -H "Authorization: Bearer $TOKEN" \
  --data-binary @sample.wav "http://localhost:${PORT}/transcribe?cleanup=true" || die "transcription failed"
echo

cat <<EOF

  Wall clock for the self-test: $((END - START))s (includes model warm-up)
  Device in use: $(curl -fsS -H "Authorization: Bearer $TOKEN" "http://localhost:${PORT}/status" | python3 -c 'import json,sys;print(json.load(sys.stdin)["device"])')

  If that printed "If you can read this, the server works." the arm64 image
  works on this machine. Please report the numbers in issue #1 if they look
  unusual — we have no aarch64 hardware in CI.
EOF
