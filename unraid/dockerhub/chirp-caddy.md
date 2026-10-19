# Chirp Caddy

Optional companion to [`joshsalvi/chirp-headscale`](https://hub.docker.com/r/joshsalvi/chirp-headscale): [Caddy](https://caddyserver.com) with the Cloudflare DNS plugin, giving Headscale a public HTTPS address with automatic certificates.

## Setup

1. Copy `chirp-server-instances/caddy/Caddyfile` from the [source repo](https://github.com/joshsalvi/chirp) and change the hostname to yours.
2. Set `CF_API_TOKEN` to a Cloudflare token with Zone → DNS → Edit for that domain.
3. In Cloudflare, set the Headscale record to **DNS only** (grey cloud), and forward port 443 on your router to this container's HTTPS port.

Only needed for Chirp stations away from home. A single home site needs just [`joshsalvi/chirp`](https://hub.docker.com/r/joshsalvi/chirp).

Help: https://ourchirp.com/troubleshooting.html
