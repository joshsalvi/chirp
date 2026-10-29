# Remote Access (Tailscale / Headscale)

Lets the server, any device, and your own laptop/phone reach each other
directly and securely from anywhere — not only on the same home network —
without exposing anything else to the internet. This is the same underlying
technology whether you use Tailscale's own cloud service or a self-hosted
Headscale instance; the client software and the day-to-day experience are
identical either way.

## Which setup applies to you

- **chirp-server-instances** can bundle its own self-hosted Headscale
  (a real, open-source, drop-in-compatible reimplementation of Tailscale's
  coordination server) — see [Bundled Headscale setup](#bundled-headscale-setup-chirp-server-instances-only)
  below. This is what the rest of this page assumes unless noted otherwise.
- **chirp-server** (single-tenant) has two separate paths, not one:
  the client toggle in Settings → Access & Security → Server Network, pointed at either
  Tailscale's own cloud service or a self-hosted Headscale you're
  already running elsewhere (including a chirp-server-instances
  deployment's own bundled one, on the same tailnet) — **or** its own
  standalone, opt-in Headscale + DERP relay, a completely separate
  Docker Compose file from the bundled one above — see "Standalone
  Headscale + DERP setup (chirp-server only)" further down this page.
  Pick whichever already exists or fits better; there's no wrong
  choice, only two different levels of setup effort.
- **chirp-device** connects the same way, via `tailscale:` in its own
  `config.yaml`.

## Standalone Headscale + DERP setup (chirp-server only)

`chirp-server/docker-compose.headscale.yml` is a completely separate,
optional compose file (not bundled into the main `docker-compose.yml`
the way chirp-server-instances' own Headscale is) — brought up
alongside chirp-server explicitly:

```bash
docker compose -f docker-compose.yml -f docker-compose.headscale.yml up -d
```

Two services, both optional and independent of chirp-server's
core function:

| Service | What it does |
|---|---|
| `chirp-headscale` | The coordination server itself, on port 8090 (distinct from chirp-server's own 8765) |
| `chirp-derper` | A self-hosted DERP relay — the fallback path used only when two peers can't establish a direct P2P connection (both behind strict/symmetric NAT). Running this yourself, rather than relying on Tailscale's own public DERP servers, keeps the entire mesh self-hosted end to end; even relayed traffic stays WireGuard-encrypted throughout, so the relay itself never sees anything it can read. |

**Real differences from chirp-server-instances' bundled setup, worth
knowing before choosing this path:**

- **No auto-bootstrap.** chirp-server-instances' Headscale generates
  its own user and auth key on first boot with zero manual steps; this
  one doesn't — the setup steps in `docker-compose.headscale.yml`'s
  own comments (creating a user, generating a preauth key via
  `docker exec`) have to be run by hand once, after first start.
- **No bundled TLS or domain exposure.** chirp-server-instances pairs
  its Headscale with `caddy` (DNS-01 TLS) and `cloudflare-ddns`
  automatically; this standalone setup does neither — port 8090 is
  exposed as plain HTTP with nothing in front of it. Getting a real
  domain and TLS certificate in front of it (a reverse proxy of your
  own, or folding it into chirp-server's own existing Cloudflare Tunnel
  as a second hostname) is left to the operator, not handled by
  anything shipped here.
- **Includes its own DERP relay**, which chirp-server-instances'
  bundled setup does not — that one relies on Tailscale's own public
  DERP servers as the direct-connection fallback instead.

If either of chirp-server-instances' gaps above (manual setup, no TLS)
matters to you, running a full chirp-server-instances deployment only
for its bundled Headscale — even with only one location's worth of
actual multi-tenant data — is a real, simpler alternative to closing
those gaps by hand on this standalone path.

## Bundled Headscale setup (chirp-server-instances only)

`docker-compose.yml` includes three services that work together:

| Service | What it does |
|---|---|
| `headscale` | The coordination server itself — auto-generates its own reusable auth key on first boot |
| `caddy` | Terminates TLS for the Headscale domain and reverse-proxies to it |
| `cloudflare-ddns` | Keeps the domain's DNS record pointed at your current public IP automatically |

### One-time setup

1. **Edit `headscale/config.yaml`** — set `server_url` to your own domain
   (e.g. `https://headscale.yourdomain.com`).
2. **Cloudflare DNS**: add an `A` record for that hostname pointing at your
   current public IP (`curl -4 ifconfig.me` from any machine on your home
   network), with proxy status **DNS only** (grey cloud) — **not**
   proxied, and **not** routed through Cloudflare Tunnel. Cloudflare's
   proxying (Tunnel or otherwise) cannot carry Tailscale's protocol at
   all — see [Cloudflare cannot be used in front of Headscale](#cloudflare-cannot-be-used-in-front-of-headscale-at-all) below.
3. **`.env`**: set `CF_API_TOKEN` to a Cloudflare API token scoped to
   `Zone:DNS:Edit` for that domain only (not your account's global API
   key) — generate one at `dash.cloudflare.com/profile/api-tokens`,
   "Edit zone DNS" template. Used by both `caddy` (to prove domain
   ownership for its certificate) and `cloudflare-ddns` (to keep the
   record current).
4. **Router port forward**: external **TCP 443** → this host's port
   **8443** (not 443, which the host's own web UI often uses, e.g.
   Unraid's). One rule, nothing else.
5. Deploy: `docker compose up -d --build`.

That's the whole one-time list. After this, nothing needs ongoing
attention — the certificate renews itself, and the DNS record updates
itself if your IP ever changes.

### Getting a device or chirp-server onto the same tailnet

The reusable key Headscale generated for itself works for any number of
clients — that's what "reusable" means, it's not a conflict:

```bash
docker compose exec headscale cat /shared/authkey
```

Use that as the `auth_key` (chirp-device's `config.yaml`) or paste it into
Settings → Access & Security → Server Network / Global Admin → Network (chirp-server /
chirp-server-instances), with `login_server` set to the same
`https://headscale.yourdomain.com`.

## How the server reaches a device

Each device card on the Devices page has **Server Connects Via**. The setting covers SSH, device logs, Listen, and mic levels:

| Setting | Address used |
|---|---|
| Auto (default) | Tailscale IP when the server is on the tailnet and the device has reported one; otherwise the LAN IP. The SSH terminal falls back to the other address if the first can't connect. |
| LAN IP | The device's LAN IP only |
| Tailscale | The device's Tailscale IP only |

The card shows the address in use. If the server's tailscaled is in userspace mode (no `tailscale0` interface), connections go through its local SOCKS5 (127.0.0.1:1055) and HTTP (127.0.0.1:1056) proxies automatically. Auto counts the server as on the tailnet when its tailscaled reports connected, a `tailscale0` interface exists, or that SOCKS5 proxy answers. If the server finds a tailscaled it can't talk to (its socket gone), it stops it and starts a fresh one instead of piling up new daemons.

## Enabling / disabling on macOS

Once already configured (a login_server + auth key has been used
once), day-to-day toggling doesn't need any of that repeated:

- **GUI**: click the Tailscale icon in the menu bar → the toggle switch
  at the top turns the connection on/off directly.
- **CLI**: `tailscale down` disconnects without forgetting anything;
  plain `tailscale up` (no flags needed) reconnects using the same
  cached identity and server.
- Quitting and reopening `Tailscale.app` should preserve the session; if
  it ever prompts for login again, rerun the original `tailscale up
  --login-server=... --authkey=...` command once to re-establish it.

## Enabling / disabling on iOS

- The big toggle on the Tailscale app's own main screen.
- Or, since Tailscale uses iOS's native VPN framework: **Settings → VPN**
  has the same on/off toggle at the system level, without opening the
  app at all.

### A known, longstanding bug worth knowing about

iOS's "Alternate Coordination Server URL" field (used to point the app at
a self-hosted Headscale instead of Tailscale's own cloud) has multiple
open, unresolved issues in Tailscale's own GitHub — it can silently revert
to the default server, or fail to persist after a keychain reset. This is
upstream, not fixable from any config on the server side. If it happens:

- Try Headscale's own self-service configuration profile instead of the
  manual field: visit `https://your-headscale-domain/apple` in Safari on
  the device, install the profile it offers, then open the app fresh.
- If that's still unreliable, connecting from macOS/Linux/Windows first
  confirms the server-side setup itself is correct, and iOS can be
  revisited separately without it blocking anything else.

## Troubleshooting — issues hit and fixed during setup

These were all confirmed against live logs, not guessed — kept here since
they're exactly the kind of thing that's expensive to re-diagnose from
scratch a second time.

### "Enabled, not yet connected" and never progresses

Check `docker compose logs chirp-server-instances | grep -i tailscale`
first, always — every fix below was found this way, not by guessing.

### `PermissionError: [Errno 13] Permission denied: '/var/run/tailscale'`

The container drops from root to an unprivileged user (via `gosu`, in
`docker-entrypoint.sh`) before the Tailscale manager code runs, so it
can't create directories under `/var/run` or `/var/lib`. Fixed in the
app itself — the daemon's state and socket now live under `/app/data`,
which that same unprivileged user already owns. Nothing to configure;
noted here in case a similar path-permission error shows up elsewhere.

### `tstun.New("tailscale0"): operation not permitted` / `tun module not loaded nor found on disk`

The host's kernel doesn't have the TUN module available at all (true on
some Unraid kernels) — not a Docker capability issue, a fact about the
kernel itself. The app automatically falls back to userspace networking
(no special kernel permissions needed) the moment it detects this exact
failure — no action needed, this is expected behavior on such a host, not
an error to chase.

### Cloudflare cannot be used in front of Headscale at all

Headscale's own documentation states this directly: "Running headscale
behind a cloudflare proxy or cloudflare tunnel is not supported and will
not work as Cloudflare does not support WebSocket POSTs as required by
the Tailscale protocol." Tailscale's handshake upgrades an HTTP **POST**
request via an `Upgrade` header — Cloudflare Tunnel has a confirmed,
still-open bug where it strips that header specifically on POST requests.
This is true of Cloudflare's regular (non-Tunnel) proxying too, not only
Tunnel — the DNS record for the Headscale domain must be **DNS only**
(grey cloud), never proxied, no matter which Cloudflare product is
involved. The fix is a dedicated reverse proxy (Caddy, bundled — see
above) that Cloudflare's edge is never in the path of.

### `tailscale up timed out after 60s`, with the daemon's own log full of `bootstrapDNS(...) error: ... network is unreachable`

Tailscale's client tries a hardcoded list of its own DERP relay servers
as a DNS bootstrap fallback, and tries their **IPv6** addresses first.
"network is unreachable" (an immediate rejection, not a timeout) means
the host has no real IPv6 route — common even when IPv6 is nominally
enabled at the OS level but the network doesn't route it. The
client burns through many doomed IPv6 attempts before ever reaching a
working IPv4 one, often exhausting the whole 60-second window in the
process. Fix, on the Docker host, not in any Chirp config:

```bash
sysctl -w net.ipv6.conf.all.disable_ipv6=1
```

Make this persist across reboots in the host's network settings (on
Unraid: Settings → Network Settings, if it offers IPv4 only) or a boot
script — a live
`sysctl` alone reverts on restart.
