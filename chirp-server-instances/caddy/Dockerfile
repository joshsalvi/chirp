# Custom Caddy build with the Cloudflare DNS plugin — needed for the
# DNS-01 certificate challenge (see Caddyfile's own comment for why
# that's the right approach here, not the usual HTTP-01). The plain
# caddy:2-alpine image doesn't include any DNS provider plugins;
# xcaddy is Caddy's own official tool for building in exactly this
# kind of addition.
FROM caddy:2-builder AS builder
RUN xcaddy build --with github.com/caddy-dns/cloudflare

FROM caddy:2-alpine
COPY --from=builder /usr/bin/caddy /usr/bin/caddy
# --resume: on first boot (no autosave in the persistent /config volume
# yet) this is a no-op and --config/--adapter below are used as normal
# — explicitly documented as not an error. On every boot after any
# admin-API-driven change (see app/services/caddy_config_manager.py),
# --resume takes priority and the change survives a full container
# restart, not just a live reload — the whole reason this is here.
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile", "--resume"]
