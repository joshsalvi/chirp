# Chirp Headscale

Optional companion to [`joshsalvi/chirp`](https://hub.docker.com/r/joshsalvi/chirp): a self-hosted [Headscale](https://github.com/juanfont/headscale) (an open Tailscale control server), so Chirp stations outside your home network reach your Chirp server privately without opening ports to it.

On first start it creates its own reusable key and writes it to the shared folder (`/shared`), where the Chirp container picks it up.

## Setup

1. Copy `chirp-server-instances/headscale/config.yaml` from the [source repo](https://github.com/joshsalvi/chirp) into the config folder and set `server_url` to your public Headscale address, e.g. `https://headscale.example.com`.
2. Map the same shared folder into Chirp at `/shared` and set Chirp's `CHIRP_TAILSCALE_ENABLED=true` and `CHIRP_TAILSCALE_LOGIN_SERVER` to that address.
3. Give Headscale a public HTTPS address with [`joshsalvi/chirp-caddy`](https://hub.docker.com/r/joshsalvi/chirp-caddy). Headscale can't sit behind Cloudflare's proxy or tunnel.

> On Unraid, keep Headscale's data on a cache-only share: the mover breaks the unix socket it uses.

Help: https://ourchirp.com/troubleshooting.html
