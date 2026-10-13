# Security policy

## Supported versions

The latest release is supported. Please update
(`update.ps1` on the client, `docker compose pull` on the server) before
reporting, since fixes ship there first.

## Reporting a vulnerability

**Please do not open a public issue for security problems.**

- Preferred: repository → **Security** → **Advisories** → *Report a vulnerability*
  (private, encrypted, keeps the discussion closed until fixed).
- Or email the maintainer listed on the repository profile.

Include: what you did, what happened, what you expected, and the version numbers
(`vozlab.log` has the client version; `docker logs vozlab` prints the server
version at startup). A proof-of-concept helps enormously.

You can expect an acknowledgement within a few days, an assessment with a rough
timeline, and credit in the release notes if you'd like it.

## Known design limits (not vulnerabilities)

These are documented, deliberate trade-offs — see [docs/PRIVACY.md](docs/PRIVACY.md):

- The API uses **plain HTTP with a bearer token** and is intended for a trusted
  LAN. Exposing port 8092 to the internet is not supported; use a VPN
  ([docs/REMOTE.md](docs/REMOTE.md)).
- The token is stored **unencrypted** in `%APPDATA%\VozLab\config.json`; anyone
  who can read your files can read the token. DPAPI storage is on the roadmap.
- `/health` is unauthenticated and reveals the model name, device and version.
- Audio is unencrypted on the LAN while in transit.

## Hardening checklist for operators

- Keep the server on a private network (or a VPN).
- Rotate the token when a device is lost: edit `server/data/config.json`,
  `docker compose restart`, update the remaining clients.
- Run the container as-is; don't add `--privileged` or mount the Docker socket.
- Update the images regularly: `docker compose pull && docker compose up -d`.
