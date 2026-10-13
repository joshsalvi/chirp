#!/bin/sh
# Bootstraps a real Tailscale-compatible auth key with zero manual steps:
# starts headscale itself, then (idempotently — safe on every restart,
# never creates a second user or a second key) makes sure a "chirp"
# user and a long-lived reusable preauth key exist, and writes that key
# to a shared file chirp-server-instances reads at its own startup.
# This is the whole point of bundling headscale in the first place —
# without it, you'd still be pasting a fresh key into .env by hand.
set -e

KEY_FILE=/shared/authkey
USER=chirp

echo "[headscale-init] starting headscale..."
headscale serve &
HEADSCALE_PID=$!

echo "[headscale-init] waiting for headscale to be ready..."
for i in $(seq 1 30); do
  if ! kill -0 "$HEADSCALE_PID" 2>/dev/null; then
    echo "[headscale-init] ERROR: headscale exited during startup (check the output above for the real error) — aborting"
    exit 1
  fi
  if headscale users list >/dev/null 2>&1; then
    echo "[headscale-init] headscale is ready (took ~${i}s)"
    break
  fi
  if [ "$i" = "30" ]; then
    echo "[headscale-init] ERROR: headscale never became ready after 30s — check its own log output above for why"
    exit 1
  fi
  sleep 1
done

USER_CREATE_OUTPUT=$(headscale users create "${USER}" 2>&1) || true
if echo "$USER_CREATE_OUTPUT" | grep -qi "already exists"; then
  echo "[headscale-init] user '${USER}' already exists, skipping"
elif echo "$USER_CREATE_OUTPUT" | grep -qi "error\|failed"; then
  echo "[headscale-init] ERROR creating user '${USER}': $USER_CREATE_OUTPUT"
  exit 1
else
  echo "[headscale-init] created user '${USER}'"
fi

# A key already exists (from a previous boot) if the shared file has
# one — reused unconditionally, without asking headscale to confirm
# it's still valid via text-matching its own list output first (that
# exact kind of check, done the same way for the user check above, is
# what caused the restart loop this fixes: headscale's own table
# output doesn't reliably contain a raw grep-able match the way this
# assumed). If a key ever genuinely gets revoked out-of-band, that
# surfaces as a clear auth failure in chirp-server-instances' own
# Tailscale logs instead — a much more honest failure mode than a
# script silently minting a new key it can't actually confirm is
# needed.
if [ -s "$KEY_FILE" ]; then
  echo "[headscale-init] existing key in ${KEY_FILE}, reusing it"
else
  echo "[headscale-init] generating a new reusable, non-expiring-in-practice preauth key..."
  # --expiration 87600h ≈ 10 years — headscale preauth keys don't
  # support "never" directly, so this is the practical equivalent.
  # --reusable means restarting chirp-server-instances, or adding
  # chirp-server/chirp-device against this same headscale later, never
  # needs a fresh one either.
  NEW_KEY=$(headscale preauthkeys create --user "${USER}" --reusable --expiration 87600h)
  mkdir -p "$(dirname "$KEY_FILE")"
  echo "$NEW_KEY" > "$KEY_FILE"
  echo "[headscale-init] wrote new key to ${KEY_FILE}"
fi

# Same zero-manual-steps reasoning as the preauth key above, for a
# different purpose: this key is a shared secret between headscale
# and chirp-server-instances for Global Admin's "who's connected"
# Network tab panel — NOT a real headscale gRPC API key used for its
# documented purpose (confirmed directly, the hard way: headscale's
# gRPC listener only speaks raw gRPC, not REST/JSON — see
# api-wrapper.py's own docstring for the full story and why this
# reads the node list through headscale's own CLI instead, with this
# key just gating that small HTTP wrapper's one endpoint).
API_KEY_FILE=/shared/apikey
if [ -s "$API_KEY_FILE" ]; then
  echo "[headscale-init] existing API key in ${API_KEY_FILE}, reusing it"
else
  echo "[headscale-init] generating a new long-lived API key for node-list queries..."
  NEW_API_KEY=$(headscale apikeys create --expiration 87600h)
  mkdir -p "$(dirname "$API_KEY_FILE")"
  echo "$NEW_API_KEY" > "$API_KEY_FILE"
  echo "[headscale-init] wrote new API key to ${API_KEY_FILE}"
fi

echo "[headscale-init] starting the node-list HTTP wrapper on 0.0.0.0:50444..."
HEADSCALE_PID="$HEADSCALE_PID" python3 /etc/headscale/api-wrapper.py &
WRAPPER_PID=$!

# Same readiness-check reasoning as headscale's own startup above —
# confirm the wrapper is actually listening before declaring setup
# complete, rather than silently continuing if it died on startup
# (which a background process's own failure won't otherwise surface
# anywhere obvious — `set -e` doesn't catch a backgrounded command's
# later failure, only a foreground one).
for i in $(seq 1 10); do
  if ! kill -0 "$WRAPPER_PID" 2>/dev/null; then
    echo "[headscale-init] WARNING: the node-list HTTP wrapper exited during its own startup — Global Admin's Network tab node list won't work until this is fixed, but headscale itself is unaffected"
    break
  fi
  # A 401 (no Authorization header sent here) still means the wrapper
  # is up and correctly responding — only a connection-level failure
  # (refused/reset, meaning nothing is listening) should count as
  # "not ready yet".
  if python3 -c "
import urllib.request, urllib.error
try:
    urllib.request.urlopen('http://127.0.0.1:50444/nodes', timeout=1)
except urllib.error.HTTPError:
    pass  # any HTTP response at all means something is listening and answering
" 2>/dev/null; then
    echo "[headscale-init] node-list HTTP wrapper is up (took ~${i}s)"
    break
  fi
  if [ "$i" = "10" ]; then
    echo "[headscale-init] WARNING: node-list HTTP wrapper never responded after 10s — Global Admin's Network tab node list may not work"
  fi
  sleep 1
done

echo "[headscale-init] setup complete — headscale running in foreground"
wait $HEADSCALE_PID
