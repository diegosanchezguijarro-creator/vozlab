# Using Scribe away from home

The server speaks plain HTTP and is meant for a trusted LAN. To dictate from a
café, a hotel or your phone hotspot, put the connection inside a VPN instead of
exposing port 8092 to the internet.

## Option 1 — Tailscale (easiest, free for personal use)

Tailscale gives every device a private IP (`100.x.y.z`) reachable from anywhere,
with no port forwarding and no firewall changes.

```bash
# on the server
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # log in with the same account as the laptop
tailscale ip -4            # e.g. 100.101.102.103
```

Install the Tailscale client on the Windows laptop, log in with the same account,
then in Scribe: **Settings → Connection → Server URL** = `http://100.101.102.103:8092`.

That's it — the dictation path now works over the tailnet, including from a phone
hotspot.

## Option 2 — WireGuard (self-hosted)

If you prefer to run the VPN yourself:

```bash
sudo apt install wireguard
# generate keys, add a [Peer] for the laptop, then
sudo wg-quick up wg0
```

Point the client at the server's WireGuard address (usually `10.0.0.1`).

## Option 3 — Public exposure (not recommended)

Only if you understand the trade-offs. Minimum requirements:

1. **TLS**: put the API behind a reverse proxy with a certificate —
   [Caddy](https://caddyserver.com) does this in two lines:
   ```
   voice.example.com {
       reverse_proxy 127.0.0.1:8092
   }
   ```
   Then set the client's Server URL to `https://voice.example.com`.
2. **A strong token** (rotate it: edit `server/data/config.json`, restart, update
   clients).
3. **Firewall**: allow only 443, and only the proxy should reach 8092.
4. **Monitoring**: watch the logs for unexpected volume —
   `docker logs -f scribe`.

Even then, remember that anyone who obtains the token can send audio to your
server. A VPN avoids the whole question.

## HTTPS with a pinned certificate

New in 1.4.0: the server can speak HTTPS with a self-signed certificate, and the
Windows app **pins** it. There is no CA, no browser warning and no certificate to
renew — the app remembers the certificate the first time it connects and refuses
anything else afterwards.

```bash
# on the server
cd ~/scribe/server
bash install.sh --with-ai --tls          # or: bash install.sh --tls
```

That generates `data/tls/cert.pem` (+ key), writes `server/.env` so Compose
passes `SCRIBE_TLS_CERT`/`SCRIBE_TLS_KEY` to the container, and prints the
certificate fingerprint:

```
  Server URL : https://192.168.0.23:8092
  Token      : …
  Certificate : 26:AE:6E:DD:…:5A:E7
```

In the app: **Settings → Server → Server URL** = `https://192.168.0.23:8092`,
then press **Test connection**. The first time, the app reads the certificate and
shows it as pinned; compare the fingerprint with the one `install.sh` printed if
you want certainty about *which* server you just trusted.

What pinning does and does not do:

| | |
|---|---|
| Protects against | passive sniffing on the network, a rogue device answering on the server's IP, a hijacked DNS/ARP reply |
| Does not protect against | someone holding the laptop (the pin is in `config.json`), or a compromised server |
| If the certificate changes | the app **stops connecting** and says so. Re-generate or re-pin: *Settings → Server → Re-pin certificate* |

Everything else on this page (Tailscale, WireGuard) still works, and a VPN
remains the right answer for dictating from outside your home network.

## LAN discovery

The server answers a UDP probe on port 8093 (name, version, HTTP port, TLS flag —
**no token, no settings**). *Settings → Server → Find my server* broadcasts that
probe and lists what answers, so you never have to look up an IP address:

```
Find my server →  http://192.168.0.23:8092  ·  v1.4.0  ·  cuda
```

Nobody can use it to dictate: the reply contains no credential. Turn it off with
`SCRIBE_DISCOVERY_PORT=0` or `"discovery": false` in `server/data/config.json`.
