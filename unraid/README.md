# Chirp templates for Unraid

Community Applications templates for [Chirp](https://ourchirp.com).

| Template | Needed? |
|---|---|
| `templates/chirp.xml` | Yes: the Chirp server and web app (port 8768) |
| `templates/chirp-headscale.xml` | Only for stations away from home |
| `templates/chirp-caddy.xml` | Only with Chirp-Headscale: public HTTPS for it |

Images: `joshsalvi/chirp`, `joshsalvi/chirp-headscale`, `joshsalvi/chirp-caddy` on Docker Hub.
Full instructions: `docs/PUBLISHING_DOCKER_UNRAID.md` in the Chirp repository.
