# Privacy & security

VozLab is designed so that **your voice never leaves your network**. This page
documents exactly what happens to your data, and what you can verify yourself.

## What is collected

**Nothing.** No analytics, no crash reporting, no usage counters, no account, no
device identifiers.

The app makes exactly two kinds of network request:

| Request | When | Destination |
|---|---|---|
| `GET /health` and `POST /transcribe` | normal use | **your** server, on your LAN |
| `GET /releases/latest` | only if you enable *Settings → System → Check for updates*, or press *Check now* | `api.github.com` (public version number) |

The second one is **off by default**. With it off, the only packets VozLab sends
are to the IP address you typed in the wizard.

`deploy.ps1` / `update.ps1` also contact GitHub, but only when you run them, to
download a release you asked for.

## What is stored

| Where | What | Why |
|---|---|---|
| `server/data/config.json` | token, model settings | server configuration (mode 600, git-ignored) |
| `server/data/hf/` | Whisper model weights | so startup doesn't re-download ~500 MB |
| `server/data/` + `ollama_data/` | LLM model weights (Docker volume) | same |
| `%APPDATA%\VozLab\config.json` | server URL, token, your preferences | so the app remembers everything |
| `%APPDATA%\VozLab\vozlab.log` | timestamps, state changes, errors | support/debugging |

**Audio is never written to disk.** It lives in memory on the client, and on the
server the only disk touch is a temporary file inside the container that
faster-whisper needs to read; it is deleted immediately after transcription. It is
not a recording — no preview, no history, no retention policy to configure.

**Transcripts** reach `vozlab.log` only when *Debug logging* is on (it is off by
default). Turn it off and clear the file from *Settings → System → Open settings
folder*. To audit what a shared PC saw, delete that folder; nothing else is kept.

## Authentication

- Every `/transcribe` request must send `Authorization: Bearer <token>`; anything
  else gets `401`. The token is generated with `secrets.token_urlsafe(24)` on
  first boot and printed in the container log.
- `/health` and `/version` are unauthenticated on purpose: they expose the model
  name, device and version number, nothing personal, and they make monitoring
  simple. Bind them to your LAN only.
- **Keep the server on a trusted LAN.** The API is plain HTTP: anyone who can
  sniff your network AND has the token could send audio to it. If you need remote
  access, use a VPN ([docs/REMOTE.md](REMOTE.md)) rather than port-forwarding.
- Rotating the token: edit `server/data/config.json`, restart the container, and
  update each client (Settings → Connection → token).

## Threat model (what VozLab does and does not protect against)

| Scenario | Covered? |
|---|---|
| Cloud provider reading your dictations | ✅ impossible — there is no cloud |
| A friend on your Wi-Fi seeing your audio | ⚠️ partially — audio is unencrypted on the LAN; use a VPN or trusted network |
| Someone with your laptop reading the token | ❌ not yet — the token is stored in plain text (`DPAPI` storage is on the roadmap) |
| Someone opening your server's port from the internet | ⚠️ they still need the token, but do not expose it; use a VPN |
| An LLM "helpfully" rewriting your text | ✅ the guard rejects rewrites that invent words, falling back to the raw transcript |
| Malicious model in Ollama | ⚠️ model weights run as data, but Ollama is a separate process you control; pin models you trust |
| Supply chain (pip/Docker) | ⚠️ dependencies are version-pinned and scanned in CI (`pip-audit`, secret scanning); SBOM is on the roadmap |

## Verifying the claims

1. **Watch the traffic**: run `sudo tcpdump -i any -n 'not port 22'` (or Wireshark)
   while dictating. You will see connections only to your server's IP:8092.
2. **Confirm no audio on disk**: `docker exec vozlab ls -la /tmp` after a few
   dictations — nothing accumulates.
3. **Check the log contents**: `%APPDATA%\VozLab\vozlab.log` with debug off
   contains state changes and errors, not your sentences.
4. **Read the code**: the whole client is ~1500 lines of Python in
   [`client/vozlab`](../client/vozlab), and the server is two files in
   [`server`](../server).

## Reporting a vulnerability

Please open a private security advisory (repository → *Security* → *Advisories*)
or email the maintainer rather than filing a public issue. We aim to respond
within a few days. See [SECURITY.md](../SECURITY.md).
