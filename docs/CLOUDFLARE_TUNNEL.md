# Cloudflare Tunnel Setup (chirp-server)

`chirp-server` is configured to use Cloudflare Tunnel by default for
HTTPS — no router port forwarding, no ports opened on your firewall, and
your home IP is never directly exposed to the internet. Cloudflare's edge
terminates TLS for you; the tunnel is a purely *outbound* connection your
server initiates, so there's nothing to punch a hole in your firewall for.

This is genuinely required, not optional hardening: Web Push and native
APNs push (built and tested) simply do not work over plain HTTP — a hard
browser/OS restriction, not a preference.

> **`chirp-server-instances` uses a genuinely different approach for its
> own main app** — not this document's Tunnel setup. It points a DNS
> record directly at your home IP, kept current automatically by its own
> bundled `cloudflare-ddns` service, with Cloudflare's regular proxying
> (the "orange cloud" toggle in its DNS dashboard) terminating TLS —
> see that project's own `ARCHITECTURE.md` for the full setup. Its
> bundled Headscale specifically *does* use a dedicated reverse proxy
> (Caddy, not Cloudflare Tunnel — Headscale's own protocol can't be
> proxied by Cloudflare at all, Tunnel or regular DNS proxying alike;
> see `docs/REMOTE_DEVICES.md`), which is a third, separate pattern
> again. Three different HTTPS approaches across this repo, each
> chosen for a real, documented reason — not inconsistency for its
> own sake.

## Prerequisites

Your domain's DNS needs to be managed by Cloudflare. If it isn't already:
Cloudflare dashboard → Add a domain → follow their onboarding, which
walks you through changing your domain's nameservers to Cloudflare's.
This is free, and doesn't require moving your domain registration itself
— only where DNS is resolved.

## Setting up chirp-server's tunnel

1. **Cloudflare dashboard → Zero Trust → Networks → Tunnels → Create a
   tunnel.**
2. Choose **Cloudflared** as the connector type.
3. Name it something clear, e.g. `chirp-server`.
4. The next screen shows an install command for various platforms —
   ignore all of them. You just need the **token** shown in that
   command (a long string starting with `ey...`). Copy it.
5. Still in the tunnel wizard (or by editing the tunnel afterward):
   click **Public Hostname**, and add:
   - **Subdomain**: whatever you want (e.g. `chirp`)
   - **Domain**: your real domain
   - **Type**: `HTTP`
   - **URL**: `http://localhost:8765` — chirp-server's own container
     runs with `network_mode: host` (needed for its device
     auto-discovery feature to read the LAN's ARP table), which means
     it doesn't get its own private Docker network identity the way a
     regular bridge-networked service would — from the tunnel
     container's own point of view, `localhost` is genuinely the right
     way to reach it, since both containers share the host's network
     stack directly.
6. In your `.env` file (same directory as `chirp-server/docker-compose.yml`,
   create it if it doesn't exist), add:
   ```
   CHIRP_CLOUDFLARE_TUNNEL_TOKEN=<the token from step 4>
   ```
7. `docker compose up -d` — the tunnel starts automatically alongside
   chirp-server itself (no separate command needed; Cloudflare Tunnel
   is the default in `docker-compose.yml`, not an opt-in extra).
8. Within a minute or two, `https://chirp.yourdomain.com` (or whatever
   subdomain you chose) should be live, with a real,
   automatically-managed TLS certificate — you never touch a certificate
   file yourself anywhere in this process.

## Verifying it's actually working

```bash
docker logs chirp-server-cloudflared
```

A healthy tunnel logs something like `Registered tunnel connection` and
`Connection established` — no `context deadline exceeded` or repeated
reconnection attempts. If you see the container restarting in a loop,
the token is almost always the cause — double check it was copied
completely (they're long) and that the `.env` file is in the same
directory `docker-compose.yml` is run from.

## If you'd rather not use Cloudflare at all

`chirp-server-instances` includes a bundled Caddy service (automatic
Let's Encrypt HTTPS via the DNS-01 challenge, not traditional HTTP-01 +
router port forwarding — see that project's own `headscale/config.yaml`
and `docker-compose.yml` comments) as a working reference for that
general pattern, though it's set up there specifically for Headscale
rather than a general-purpose reverse proxy in front of a main webapp.
Adapting it for that purpose is a real option if you want router-port-
forwarding-based HTTPS instead of either Cloudflare approach above, but
isn't something either project ships pre-configured for out of the box.
