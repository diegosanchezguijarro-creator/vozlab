# Privacy & security

Scribe is designed so that **your voice never leaves your network**. This page
documents exactly what happens to your data, and what you can verify yourself.

## What is collected

**Nothing.** No analytics, no crash reporting, no usage counters, no account, no
device identifiers.

The app makes exactly two kinds of network request:

| Request | When | Destination |
|---|---|---|
| `GET /health`, `GET /status`, `POST /transcribe` | normal use | **your** server, on your LAN |
| `GET /releases/latest` | only if you enable *Settings → System → Check for updates*, or press *Check now* | `api.github.com` (public version number) |

The second one is **off by default**. With it off, the only packets Scribe sends
are to the IP address you typed in the wizard.

`deploy.ps1` / `update.ps1` also contact GitHub, but only when you run them, to
download a release you asked for.

## What is stored

| Where | What | Why |
|---|---|---|
| `server/data/config.json` | admin token **hash-free** (mode 600), device-token hashes, model settings | server configuration (git-ignored) |
| `server/data/hf/` | Whisper model weights | so startup doesn't re-download ~500 MB |
| `server/data/` + `ollama_data/` | LLM model weights (Docker volume) | same |
| `%APPDATA%\VozLab\config.json` | server URL, **DPAPI-encrypted token**, your preferences | so the app remembers everything |
| `%APPDATA%\VozLab\vozlab.log` | timings, state changes, errors | support/debugging (never your words, unless debug is on) |

**Audio is never written to disk.** The client keeps it in memory and posts it
straight to the server; the server decodes the uploaded bytes **in memory** and
hands them to faster-whisper, so no temporary file is created anywhere. There is
no recording, no preview, no history, and no retention setting to get wrong.

Your **custom vocabulary** (names, product names) is stored in
`server/data/config.json` and `%APPDATA%\VozLab\config.json`: it is a list of
terms you chose, used to bias recognition. It is not sent anywhere else.

**Transcripts never reach `vozlab.log` by default.** The log records lengths,
languages and timings, not what you said. Only with *Debug logging* on (off by
default) do the words get written, so you can analyse a bad transcription — turn
it off and clear the file from *Settings → System → Clear log*.

`vozlab.log` also scrubs anything that looks like a credential: the server token,
`Authorization: Bearer …` headers and `"token": "…"` fields are masked before a
line is written.

## Authentication

- Every `/transcribe` request must send `Authorization: Bearer <token>`; anything
  else gets `401`. The admin token is generated with `secrets.token_urlsafe(24)`
  on first boot and **printed once**, at that moment only — later restarts say
  "already configured" so the token never accumulates in `docker logs`.
- Token comparison is constant-time (`secrets.compare_digest`).
- **Per-device tokens**: *Settings → Server → Connected devices* issues a token
  for one machine (`POST /tokens`). Only a salted SHA-256 hash is stored on the
  server, and the value is shown once. Revoke a lost laptop without touching the
  other machines.
- `/health` and `/version` are unauthenticated on purpose and deliberately
  minimal: `{"ok": true, "version": …, "api": …}`. The detailed view (models,
  device, GPU, uptime, request count) lives behind the token at `/status`. Set
  `"expose_details": true` in `server/data/config.json` if you *want* the old
  verbose `/health`. OpenAPI docs (`/docs`) are disabled.
- **LAN discovery replies contain no credential**: name, version, HTTP port, TLS
  flag, model and device. It answers only to a broadcast probe on UDP 8093 and
  can be switched off (`VOZLAB_DISCOVERY_PORT=0`).
- **HTTPS is available and pinned**: `install.sh --tls` creates a self-signed
  certificate; the app stores its SHA-256 fingerprint on first connect and
  refuses any other certificate afterwards. That protects the audio on the wire,
  which is the one thing a home LAN cannot promise.
- Requests are rate-limited per client (`VOZLAB_RATE_LIMIT`, default 120/min).
- **Keep the server on a trusted LAN.** The API is plain HTTP: anyone who can
  sniff your network AND has a token could send audio to it. If you need remote
  access, use a VPN ([docs/REMOTE.md](REMOTE.md)) rather than port-forwarding.
- Rotating everything: delete the `token` in `server/data/config.json` and restart
  the container (a new one is generated), then update each client. To rotate a
  single device instead, revoke it in the app.

## Hardening you get by default

The server container runs as an unprivileged user (uid 1000) with a **read-only
root filesystem**, `no-new-privileges`, and **all Linux capabilities dropped**:

```yaml
user: "1000:1000"
read_only: true
tmpfs: [/tmp]
security_opt: [no-new-privileges:true]
cap_drop: [ALL]
```

The base image is pinned by digest (`python:3.12-slim@sha256:…`) and every Python
dependency is pinned to an exact version, so a rebuild cannot silently pull
something different. CI enforces this:

| Check | Tool |
|---|---|
| Bugs / dead code | `ruff` (this caught real `except … as e` scope bugs) |
| Static analysis | `bandit` (medium and above fail the build) |
| Secrets in history | `gitleaks` |
| Known CVEs in dependencies | `pip-audit` |
| Dockerfile ↔ requirements drift | a CI job that parses both |
| Leaks and thread growth over time | soak tests in `client/tests/test_soak.py` |

Every release also publishes an **SBOM** (`vozlab-server-<version>.spdx.json`)
alongside the binaries.

## Threat model (what Scribe does and does not protect against)

| Scenario | Covered? |
|---|---|
| Cloud provider reading your dictations | ✅ impossible — there is no cloud |
| A friend on your Wi-Fi seeing your audio | ⚠️ partially — audio is unencrypted on the LAN; use a VPN or trusted network |
| Someone with your laptop reading the token | ✅ the token is encrypted with Windows DPAPI, tied to your user account, and stored as `token_enc` (a copied config file is useless) |
| Someone opening your server's port from the internet | ⚠️ they still need a token, but do not expose it; use a VPN |
| A stolen laptop | ✅ revoke that device's token from any other client; the others keep working |
| The server being compromised through the app | ✅ the container is non-root, read-only and capability-free |
| An LLM "helpfully" rewriting your text | ✅ the guard rejects rewrites that invent words, falling back to the raw transcript |
| Malicious model in Ollama | ⚠️ model weights run as data, but Ollama is a separate process you control; pin models you trust |
| Supply chain (pip/Docker) | ✅ pinned by exact version, base image by digest; `pip-audit`, `bandit`, `gitleaks`, Dependabot and an SBOM per release |
| Someone sniffing your LAN | ✅ optional: `install.sh --tls` + certificate pinning encrypts the audio ([REMOTE.md](REMOTE.md)); plain HTTP is still the default for a trusted home network |
| A rogue device pretending to be your server | ✅ with a pinned certificate the app refuses it (the fingerprint stops matching) |

## Verifying the claims

1. **Watch the traffic**: run `sudo tcpdump -i any -n 'not port 22'` (or Wireshark)
   while dictating. You will see connections only to your server's IP:8092.
2. **Confirm no audio on disk**: `docker exec vozlab ls -la /tmp` after a few
   dictations — nothing accumulates.
3. **Check the log contents**: `%APPDATA%\VozLab\vozlab.log` with debug off
   contains timings and errors, not your sentences:
   `Select-String -Path "$env:APPDATA\VozLab\vozlab.log" -Pattern "dictation"`.
4. **Check the token is encrypted**: `%APPDATA%\VozLab\config.json` has no
   `token` field, only `token_enc`.
5. **Read the code**: the whole client is ~1500 lines of Python in
   [`client/vozlab`](../client/vozlab), and the server is a few files in
   [`server`](../server).

## Reporting a vulnerability

Please open a private security advisory (repository → *Security* → *Advisories*)
or email the maintainer rather than filing a public issue. We aim to respond
within a few days. See [SECURITY.md](../SECURITY.md).
