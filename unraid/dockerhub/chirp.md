# Chirp

Bird and bat call detection for your yard. Raspberry Pi stations listen and identify birds with BirdNET; this server keeps the recordings, spectrograms, life list, alerts and the web app. It's also the server behind the Chirp iPhone app.

- **Web app:** recordings with spectrograms, a bird library, life list, statistics, notes, alerts and a daily journal
- **Detection:** BirdNET v3 (default) or 2.4 on the server, Nighthawk night flight calls, bat echolocation
- **AI (optional):** second opinions on calls, journals and summaries with your own Anthropic, OpenAI, Gemini or local Ollama key
- **Many sites:** one server can host several sites, each with its own users and database

## Quick start

```bash
docker run -d --name chirp --network host \
  -e CHIRP_SECRET_KEY="$(openssl rand -hex 32)" \
  -e CHIRP_GLOBAL_ADMIN_USERNAME=yourname \
  -e TZ=America/New_York \
  -v /path/to/chirp-data:/app/data \
  joshsalvi/chirp:latest
```

Open `http://SERVER-IP:8768`, register with the admin username, then pair a station from **Devices**.

| Setting | What it's for |
|---|---|
| `CHIRP_SECRET_KEY` | Signs sign-ins. Any long random string; keep it the same across updates |
| `CHIRP_GLOBAL_ADMIN_USERNAME` | This username becomes the server admin |
| `CHIRP_SERVER_URL` | Public address, used in emails and links (optional) |
| `CHIRP_EBIRD_API_KEY` | Field Guide data (optional, free at ebird.org/api/keygen) |
| `CHIRP_CARTO_KEY` | Map tiles without a watermark (optional, free at carto.com/basemaps/apikey) |
| `CHIRP_TAILSCALE_ENABLED` | `true` to let stations away from home reach the server (see chirp-headscale) |
| `TZ` | Server time zone |

Data lives in `/app/data`: databases, recordings, spectrograms and photos. Put it on a disk with room to grow.

## Stations away from home

Add [`joshsalvi/chirp-headscale`](https://hub.docker.com/r/joshsalvi/chirp-headscale) and [`joshsalvi/chirp-caddy`](https://hub.docker.com/r/joshsalvi/chirp-caddy). The Unraid templates and `docker-compose.yml` in the source repo set up all three together.

## Links

- Source and full setup guide: https://github.com/joshsalvi/chirp
- Help: https://ourchirp.com/troubleshooting.html
- Unraid: search **Chirp** in Community Applications

BirdNET models are CC BY-NC-SA 4.0 and Nighthawk is CC BY-NC 4.0: free for non-commercial use with attribution.
