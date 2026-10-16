# Publishing Chirp to Docker Hub and Unraid Community Applications

The full ourchirp.com stack is three images built from `chirp-server-instances/`:

| Image | Built from | Needed by |
|---|---|---|
| `joshsalvi/chirp` | `chirp-server-instances/` | everyone (server + web app, port 8768) |
| `joshsalvi/chirp-headscale` | `chirp-server-instances/headscale/` | only for stations away from home |
| `joshsalvi/chirp-caddy` | `chirp-server-instances/caddy/` | only with Headscale (public HTTPS) |

The iOS re-sign services (`anisette`, `ios-resign`, `resign-tunnel`) stay out: they are personal tooling.

> **Placeholder:** `joshsalvi` is assumed to be your Docker Hub username. If it differs, replace it in `unraid/templates/*.xml`, `unraid/ca_profile.xml` and the commands below.

## Before publishing

- **What goes public.** A public image contains the server's Python source, the built web app and the BirdNET/bat model files. The source is already public (github.com/joshsalvi/chirp). The BirdNET models are CC BY-NC-SA 4.0 and Nighthawk is CC BY-NC 4.0: free redistribution is allowed for non-commercial use with attribution, which the app's About page and templates carry. If Chirp is ever sold, revisit this.
- **No secrets in images.** `.dockerignore` (both forks) leaves out `.env*`, `*.p8`, `*.db`, `data/`, `node_modules`, builds and tests. Check after the first build:
  ```bash
  docker run --rm --entrypoint sh joshsalvi/chirp:latest -c \
    'find / -xdev \( -name "*.p8" -o -name ".env" -o -name "*.db" \) 2>/dev/null | grep -v /proc'
  ```
  The output should be empty.
- **Defaults that point at ourchirp.com.** `headscale/config.yaml` (`server_url`) and `caddy/Caddyfile` (`headscale.ourchirp.com`) are not baked into the images; Unraid users supply their own copies (the templates map them from appdata).

## 1. Docker Hub

### One time

1. Sign in at hub.docker.com → **Repositories → Create**: `chirp`, `chirp-headscale`, `chirp-caddy`, all **Public**. Add a short description and link to https://ourchirp.com.
2. **Account settings → Personal access tokens → Generate**: name `github-actions`, access **Read & Write**. Copy it.
3. In GitHub, repo `joshsalvi/chirp` (the public one) → **Settings → Secrets and variables → Actions → New repository secret**:
   - `DOCKERHUB_USERNAME` = your Docker Hub username
   - `DOCKERHUB_TOKEN` = the token from step 2

### Each release (automatic)

`.github/workflows/docker-publish.yml` builds all three images for `linux/amd64` and `linux/arm64` and pushes `:<version>` and `:latest` when a tag starting with `v` is pushed:

```bash
cd ~/Documents/Github.nosync/chirp-public       # after publish-public.sh
V=$(cat chirp-server-instances/VERSION)
git tag "v$V" && git push origin "v$V"
```

Or run it by hand: GitHub → **Actions → Publish Docker images → Run workflow**. The first run takes about 30–40 minutes (arm64 under emulation); later runs use the cache.

### Each release (by hand from the Mac, instead)

```bash
docker login -u joshsalvi                        # paste the access token
cd ~/Developer/Chirp/src/chirp-server-instances
V=$(cat VERSION)
docker buildx create --use --name chirp 2>/dev/null || docker buildx use chirp
docker buildx build --platform linux/amd64,linux/arm64 -t joshsalvi/chirp:$V -t joshsalvi/chirp:latest --push .
docker buildx build --platform linux/amd64,linux/arm64 -t joshsalvi/chirp-headscale:$V -t joshsalvi/chirp-headscale:latest --push headscale
docker buildx build --platform linux/amd64,linux/arm64 -t joshsalvi/chirp-caddy:$V -t joshsalvi/chirp-caddy:latest --push caddy
```

### Run the full stack from Docker Hub (any Docker host)

In `docker-compose.yml`, replace each `build:` block with the image:

```yaml
  chirp-server-instances:
    image: joshsalvi/chirp:latest
  headscale:
    image: joshsalvi/chirp-headscale:latest
  caddy:
    image: joshsalvi/chirp-caddy:latest
```

`docker-compose.simple.yml` (one container) works the same way with `image: joshsalvi/chirp:latest`.

## 2. Unraid Community Applications

CA lists single-container templates from a public GitHub repo. The ready-made repo contents are in `unraid/` here:

```
unraid/
  README.md
  LICENSE            MIT, for the template files only (CA requires an OSI license)
  .gitignore
  ca_profile.xml     repository profile (required)
  icon.png, icon.svg
  templates/chirp.xml
  templates/chirp-headscale.xml
  templates/chirp-caddy.xml
```

### Steps

1. **Publish the images first** (section 1). CA scans check that each `<Repository>` image exists.
2. **Create the templates repo.** On GitHub: new **public** repo `joshsalvi/unraid-templates`. Copy in the contents of `unraid/`:
   ```bash
   gh repo create joshsalvi/unraid-templates --public --clone
   cp -R ~/Developer/Chirp/src/unraid/. unraid-templates/
   cd unraid-templates && git add -A && git commit -m "Chirp templates" && git push -u origin main
   ```
   (Compare with the official starter, github.com/unraid/unraid-community-apps-starter, in case its required files changed.)
3. **Test on your own Unraid** before submitting: copy `templates/chirp.xml` to `/boot/config/plugins/dockerMan/templates-user/my-Chirp.xml`, then **Docker → Add Container → Template: Chirp**. Use a new data path (not the live `chirp-instances-data`) and a different port if the live stack is running (set **Port** to e.g. 8769). Check the web UI opens, you can register the admin user, and a station pairs.
4. **Support page.** The templates point `<Support>` at https://ourchirp.com/support.html. CA also likes an Unraid forum thread: post one in **Docker Containers** (forums.unraid.net) titled "[Support] Chirp", then set its URL as `<Support>` in the three templates and `<Forum>` in `ca_profile.xml`.
5. **Submit.** Go to https://ca.unraid.net/submit/new, enter `https://github.com/joshsalvi/unraid-templates`, run **Validate**, then **Scan**. Fix anything it flags, push, rescan, then **Submit**. Track it under https://ca.unraid.net/submissions.
6. **Updates.** Nothing to resubmit for new versions: templates use `:latest`, so pushing new images (section 1) is enough; users get the update from the Docker tab. Change the XML only when settings change; CA re-reads the repo on its own.

### Notes for Unraid users (in the template text too)

- **Single home site:** install only **Chirp**. Host network, port 8768, data in `/mnt/user/appdata/chirp`.
- **Stations away from home:** also **Chirp-Headscale** and **Chirp-Caddy**. Copy `headscale/config.yaml` and `caddy/Caddyfile` from the repo into appdata and edit the hostnames before the first start; set the Cloudflare record to DNS only; forward router 443 → 8443. Map the same `shared` folder into Chirp at `/shared` and set Chirp's **Tailscale** to `true` and **Tailscale login server** to the Headscale address.
- **Keep sockets off the array.** Headscale's socket path (and Chirp's data if it holds sockets) must be on a cache-only or cache-preferred share; the Unraid mover breaks unix sockets it moves (this is what refused Tailscale hourly on ourchirp.com before 0.5.13.c).
