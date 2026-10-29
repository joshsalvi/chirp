# syntax=docker/dockerfile:1
# =============================================================================
# Chirp Server — Multi-stage Dockerfile
# Stage 1: Build React frontend
# Stage 2: Python FastAPI server
# =============================================================================

# ── Stage 1: Frontend Build ───────────────────────────────────────────────────
# node:22, not 20 — @capacitor/cli (used for the separate iOS build, not the
# web app itself, but still a dependency in this package.json) requires
# Node >=22 as of its 8.x line. 20 still worked (npm only warns, doesn't
# fail, on an engine mismatch), but this removes the warning cleanly rather
# than leaving a real, if currently harmless, version mismatch in place.
FROM node:22-slim AS frontend-builder

WORKDIR /frontend
# Copy package files first for better layer caching.
# package-lock.json* — the * makes it optional so builds work with or without it.
COPY frontend/package.json frontend/package-lock.json* ./
# npm ci installs exactly the lock file (faster than install, and the same
# packages every time); the cache mount keeps downloads between builds.
RUN --mount=type=cache,target=/root/.npm \
    if [ -f package-lock.json ]; then npm ci --legacy-peer-deps --no-audit --no-fund; \
    else npm install --legacy-peer-deps --no-audit --no-fund; fi
COPY frontend/ .
# VERSION lives at chirp-server/VERSION — one level above frontend/, so it
# is NOT included by `COPY frontend/ .` above (that only copies the
# contents of the frontend/ directory itself). This stage's filesystem is
# completely separate from the backend stage's own `COPY VERSION
# ./VERSION` below; each Docker build stage only contains what's
# explicitly copied into it. Without this line, scripts/stamp-sw-version.mjs
# (which runs via the npm prebuild hook below) has no VERSION file to
# read at all inside this stage, regardless of how its relative path math
# is written — confirmed by the exact failure this fixes: the script
# correctly computed /VERSION as the path it expected, but nothing had
# ever copied a file there in this stage.
COPY VERSION ./VERSION
# ourchirp.com's website pages (about, guides, support, privacy) and its
# own Global Admin tabs (src/website) are left out of every other build;
# those servers link to ourchirp.com instead (app/website). Only
# ourchirp.com's build sets CHIRP_WEBSITE=1 (its .env, via docker-compose.yml).
ARG CHIRP_WEBSITE=0
RUN if [ "$CHIRP_WEBSITE" != "1" ]; then \
      cd public && rm -rf about.html about-img setup.html guide.html troubleshooting.html support.html testflight.html \
        privacy.html docs.css site.js && cd .. && \
      if [ -d src/website ]; then rm -rf src/website && mkdir src/website && \
        printf '// Not in this build: ourchirp.com only.\nexport const websiteTabsFirst = []\nexport const websiteTabsLast = []\n' \
          > src/website/WebsiteAdmin.jsx; fi; \
    fi
RUN npm run build

# ── Stage 2: Python Backend ───────────────────────────────────────────────────
FROM python:3.11-slim-bookworm AS backend

# System dependencies for audio processing + Playwright Chromium
RUN apt-get update && apt-get install -y --no-install-recommends \
    libsndfile1 ffmpeg curl gcc g++ openssh-client sshpass \
    # Playwright/Chromium runtime deps
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 libdrm2 libxkbcommon0 \
    libxcomposite1 libxdamage1 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libx11-xcb1 libxcb-dri3-0 \
    && rm -rf /var/lib/apt/lists/*

# Tailscale client — installed unconditionally, inert until actually
# configured via CHIRP_TAILSCALE_* env vars (see tailscale_manager.py).
# Uses Tailscale's own official install script, which handles adding
# its signed apt repo for this exact Debian release correctly rather
# than this Dockerfile hand-rolling (and potentially getting wrong) key
# management for a package that changes signing keys over time.
RUN curl -fsSL https://tailscale.com/install.sh | sh \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Python dependencies
# Note: requirements.txt includes tensorflow-cpu (not tflite-runtime).
# tflite-runtime 2.14 has a PyCapsule/CreateWrapperFromFile incompatibility
# with birdnetlib's bundled BirdNET model files. tensorflow-cpu works correctly.
COPY requirements.txt .
# The pip cache lives in a build cache mount, not the image, so rebuilds
# after a requirements change only download what changed. Chromium itself
# is installed once, further down, where the app looks for it.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade pip && \
    pip install -r requirements.txt && \
    playwright install-deps chromium 2>/dev/null || true
# The "|| true" above also hides a failed pip install. A full Docker disk
# once left tensorflow without tensorflow/python and the image still
# built, so server BirdNET failed with "No module named 'tensorflow.python'".
RUN python -c "from tensorflow import lite; import birdnetlib.analyzer; print('tensorflow + birdnetlib OK')"
# Nighthawk (Experimental night flight calls): no deps, see requirements.txt.
# Its wheel says Python 3.10 only; on 3.11 it gives the same detections.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-deps --ignore-requires-python nighthawk==0.3.1 && \
    python -c "import nighthawk.detector, onnxruntime, pandas; print('nighthawk + onnxruntime OK')"
# Security-scan cleanup: newer setuptools (its bundled wheel and
# jaraco.context had CVEs), then drop the compilers, which were only
# needed to build wheels above. Runtime libraries the compilers pulled in
# (libgomp1, libstdc++6 ...) are kept so numpy/scipy/onnxruntime still load.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --upgrade "setuptools>=83" "wheel>=0.46.2" && \
    apt-mark manual libgomp1 libstdc++6 libgcc-s1 libquadmath0 libgfortran5 libatomic1 2>/dev/null; \
    apt-get purge -y gcc g++ gcc-12 g++-12 cpp cpp-12 libgcc-12-dev libstdc++-12-dev && \
    apt-get autoremove -y && rm -rf /var/lib/apt/lists/* && \
    python -c "import numpy, scipy, librosa, onnxruntime, sklearn; from tensorflow import lite; import birdnetlib.analyzer, jwt; print('runtime imports OK after compiler removal')"

# Make Chromium accessible to all users. The chirp user is made here, so
# files copied below can be given to it as they're copied (COPY --chown):
# a chown -R over /app at the end rewrote every file, Chromium included,
# into a new ~1 GB layer on each release.
ENV PLAYWRIGHT_BROWSERS_PATH=/app/.playwright-browsers
RUN useradd -m -u 1000 chirp && \
    playwright install chromium && chown -R chirp:chirp /app

# Rarely changing files first, so a code change rebuilds only the last layers.
COPY --chown=chirp:chirp chirp-logo.svg ./chirp-logo.svg
COPY --chown=chirp:chirp models/ ./models/
COPY --chown=chirp:chirp scripts/night-report.py ./scripts/night-report.py
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

# Version file
COPY --chown=chirp:chirp VERSION ./VERSION

# Changelog — served at GET /api/v1/changelog
COPY --chown=chirp:chirp CHANGELOG.md ./CHANGELOG.md

# App icon — served at GET /icon.svg (see app/main.py's serve_icon()).
# This was missing entirely before: serve_icon() looks for
# /app/chirp-logo.svg, found nothing, and silently served an empty stub
# SVG instead of erroring — which is exactly why the icon never showed up
# anywhere that references this URL (Unraid's docker-compose.yml label,
# template.yml, and the Compose Manager plugin's project icon_url all
# point at the same http://.../icon.svg endpoint).

# Copy application code
COPY --chown=chirp:chirp app/ ./app/

# Bat species classifier files (~100KB; the BirdNET base model for
# embeddings comes from birdnetlib's own bundled copy) — a real bug found and
# fixed here: this line was missing entirely, meaning the classifier's
# model-file path computation was correct (confirmed directly against a
# production log showing it looking in exactly the right place,
# /app/models/bats) but nothing ever put the actual files there. The
# classifier code itself was extensively tested against the real files —
# just never against an actual Docker build, which is what actually ships
# to production.

# Copy built frontend into static directory
COPY --chown=chirp:chirp --from=frontend-builder /frontend/dist ./app/static
# Late, so changing it doesn't rebuild the layers above (app/website).
ARG CHIRP_WEBSITE=0
ENV CHIRP_WEBSITE=$CHIRP_WEBSITE
RUN if [ "$CHIRP_WEBSITE" != "1" ] && [ -d app/website ]; then \
      find app/website -name '*.py' ! -name '__init__.py' -delete; fi

# Create data directories
RUN mkdir -p /app/data/recordings \
             /app/data/spectrograms \
             /app/data/media/birds \
             /app/data/clips && chown -R chirp:chirp /app/data

# Non-root user for security — actual privilege drop now happens in
# docker-entrypoint.sh via setpriv, AFTER it's had a chance (running as
# root, this container's actual starting user now) to fix ownership of
# whatever's mounted at /app/data. See that script's own comment for
# the real, confirmed bug this fixes (found on chirp-server-instances,
# a fresh deployment of this same Dockerfile — applied here too since
# it protects any future fresh chirp-server deployment the same way,
# and is a no-op if /app/data's ownership is already correct, which it
# already is on any existing, working deployment): a container that
# stayed non-root from here (the old approach) can't chown a root-owned
# fresh mount to fix itself; it can only fail forever.
# (The chirp user is created above, with Chromium.)

EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=15s --start-period=90s --retries=3 \
  CMD curl -f http://localhost:8765/api/v1/health || exit 1

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
CMD ["python", "-m", "app.main"]
