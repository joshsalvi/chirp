#!/bin/sh
# Self-healing fix for a real, confirmed failure mode, found from an
# actual deployment's real nginx error log:
#   "/usr/share/nginx/html/index.html" is forbidden (13: Permission denied)
# Root cause: the host-side launcher/ directory had 700/600 permissions
# (owner-only) from however it got extracted on the user's machine — a
# different problem from chirp-server's own root-owned-volume issue
# (docker-entrypoint.sh in chirp-server/), but the same underlying
# lesson: files that cross the host/container boundary can't be trusted
# to already have the permissions the container's own user needs.
#
# The fix can't be "chmod the mount in place" the way chirp-server's own
# entrypoint fixes its data directory — this mount is deliberately
# :ro (read-only), and chmod-ing a read-only bind mount fails outright
# ("Read-only file system"), even as root. Instead: copy from the
# read-only mount (/usr/share/nginx/html-src) into a real, writable,
# container-internal directory (/usr/share/nginx/html), fix permissions
# on THAT copy, and serve from there — the host's own files stay exactly
# as mounted, genuinely untouched and still read-only, while nginx gets
# a correctly-permissioned copy to actually serve.
#
# Runs on every container start, not just the first — cheap (two small
# files), and means a person re-extracting a fresh zip with the same
# restrictive permissions next month gets the same automatic fix, not a
# one-time patch that stops working on the next redeploy.
set -e

mkdir -p /usr/share/nginx/html
cp -f /usr/share/nginx/html-src/*.html /usr/share/nginx/html-src/*.json /usr/share/nginx/html/ 2>/dev/null || true
chmod -R 755 /usr/share/nginx/html

# Hand off to the real nginx:alpine image's own entrypoint (confirmed
# from the real log: it does genuine setup — IPv6 listen config, worker
# process tuning, envsubst on templates) rather than calling nginx
# directly here, which would silently skip all of that.
exec /docker-entrypoint.sh nginx -g "daemon off;"
