# Server Deployment

The server runs as a single Docker container — no external database,
message queue, or other infrastructure to stand up separately.

## Quick start

```bash
cp .env.example .env
# Edit .env — required: CHIRP_SECRET_KEY, CHIRP_DEVICE_API_KEY
docker-compose up -d --build
# WebGUI:   http://YOUR_IP:8765
# API docs: http://YOUR_IP:8765/api/docs
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `CHIRP_SECRET_KEY` | Yes | JWT signing secret — generate with `openssl rand -hex 32` |
| `CHIRP_DEVICE_API_KEY` | Yes | Default API key edge devices authenticate with |
| `CHIRP_EBIRD_API_KEY` | No | eBird API v2 key — enables the Field Guide feature |
| `CHIRP_AUTH_ENABLED` | No | Set `true` to require login for dashboard access |
| `CHIRP_ADMIN_PASSWORD` | No | Initial admin password (default: `chirp-admin` if unset) |
| `CHIRP_API_DOCS` | No | `1` serves `/api/docs` and `/openapi.json`; on by default, off on ourchirp.com |
| `CHIRP_MONITOR_URLS` | No | ourchirp.com only: more addresses for the reachability checks, comma-separated `name=url` |

## Volume paths

Everything persistent lives under a single mounted volume:

| Container path | Contents |
|---|---|
| `/app/data` | Everything below — mount this whole path to persistent storage |
| `/app/data/chirp.db` | SQLite database |
| `/app/data/recordings/` | WAV audio files |
| `/app/data/spectrograms/` | Generated spectrogram PNGs |
| `/app/data/media/birds/` | Downloaded species photos and reference audio |

## Schema migrations

New database columns are added automatically on every container startup
(via a migration check built into the app, not a separate migration tool like Alembic)
— existing data is preserved, and adding a new field to the codebase is
enough for it to appear in the live schema on next restart.

## Security

- Every response carries `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy` and `Permissions-Policy`; HSTS is added over HTTPS (directly or behind Cloudflare / Caddy).
- Sign-in locks for 5 minutes after 5 wrong passwords for one name from one address, and an address is blocked for 15 minutes after 30 wrong passwords across names. Sign-ups: 10 attempts an hour per address.
- Behind a proxy the caller's address comes from `CF-Connecting-IP` or `X-Forwarded-For`. Don't expose port 8765 to the internet directly, or those headers can be forged.
- Requests for scanner paths (`/.env`, `/wp-login.php` …) get a 404 and are logged as security events.
- `robots.txt` asks search engines to stay out.

## Checks before a release

```bash
pip install -r requirements-dev.txt
./scripts/check.sh          # ruff (bugs only), tests in parallel, frontend build + size budget
```

## Frontend development

```bash
cd frontend
npm install
npm run dev      # dev server with hot reload, http://localhost:5173
npm run build    # production build → dist/, copied into the Docker image at build time
```
