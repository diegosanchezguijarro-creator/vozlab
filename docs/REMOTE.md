# Using VozLab away from home

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
then in VozLab: **Settings → Connection → Server URL** = `http://100.101.102.103:8092`.

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
   `docker logs -f vozlab`.

Even then, remember that anyone who obtains the token can send audio to your
server. A VPN avoids the whole question.

## Why the client can't "just" do HTTPS for you

Certificate pinning (trust-on-first-use) is on the roadmap: it will let the
Windows app talk to a self-signed HTTPS server without a browser-style
certificate warning. Until then, use a VPN or a real certificate via Caddy.
