#!/bin/sh
# Self-healing fix for a real, confirmed failure mode: a fresh bind
# mount to a host path that doesn't exist yet is commonly auto-created
# by Docker as root:root — which then blocks the non-root chirp user
# (UID 1000, set up below) from creating anything inside it, including
# this app's own expected subdirectories at startup (config.py's
# ensure_dirs()). Confirmed from a real deployment's actual logs:
# PermissionError: [Errno 13] Permission denied: '/app/data/recordings',
# crash-looping forever (Docker's restart policy just keeps hitting the
# same error) until fixed manually on the host. This container now
# fixes it itself instead of requiring that manual step.
#
# Runs as root (this script is the ENTRYPOINT, invoked before Dockerfile's
# USER directive would otherwise apply — see the Dockerfile's own comment
# on why USER chirp was removed in favor of this), then drops to the real
# unprivileged chirp user via setpriv (util-linux) before ever executing the actual app —
# the app itself never runs with root privileges, only this narrow
# ownership-fixing step does.
#
# Non-recursive on purpose: only the mount point itself needs correct
# ownership for subdirectory creation to succeed — recursively chowning
# potentially years of accumulated recordings on every single container
# start would be needlessly slow for something that only matters once,
# the very first time a fresh volume is mounted.
set -e

if [ "$(stat -c '%u' /app/data 2>/dev/null)" != "1000" ]; then
    echo "entrypoint: fixing ownership of /app/data (was owned by uid $(stat -c '%u' /app/data 2>/dev/null || echo '?'), fixing to chirp/1000)"
    chown chirp:chirp /app/data
fi

export HOME=/home/chirp USER=chirp LOGNAME=chirp
exec setpriv --reuid=chirp --regid=chirp --init-groups "$@"
