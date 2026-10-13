# Edge TPU Compiler — build environment
#
# The compiler itself (edgetpu_compiler) is a Google-distributed x86_64-only
# Linux binary — there is no macOS build and no ARM64 build (confirmed
# current as of this writing: coral.ai/docs/edgetpu/compiler explicitly
# says "no longer available for ARM64 systems, beginning with version 2.1").
# Docker with --platform linux/amd64 is what makes this runnable from a Mac
# (Intel: native x86_64, no emulation; Apple Silicon: QEMU-emulated x86_64 —
# slower, but this is a few-second one-time compile, not a big deal).
#
# Uses the modern GPG-keyring method (apt-key is deprecated and warns/fails
# on current Debian) rather than the older `apt-key add` instructions still
# shown on some older tutorials.
FROM debian:bookworm-slim

RUN export DEBIAN_FRONTEND=noninteractive \
    && apt-get update \
    && apt-get install --no-install-recommends -y \
        apt-transport-https ca-certificates curl gnupg \
    && curl -fsSL https://packages.cloud.google.com/apt/doc/apt-key.gpg \
        | gpg --dearmor -o /usr/share/keyrings/coral-edgetpu.gpg \
    && echo "deb [signed-by=/usr/share/keyrings/coral-edgetpu.gpg] https://packages.cloud.google.com/apt coral-edgetpu-stable main" \
        > /etc/apt/sources.list.d/coral-edgetpu.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y edgetpu-compiler \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /work
ENTRYPOINT ["edgetpu_compiler"]
