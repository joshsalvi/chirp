# Chirp iOS re-sign service: AltServer-Linux (NG fork: iOS 26.4+/27 signing
# and the September 2026 Apple sign-in fix) + netmuxd + a small watcher.
# Optional; started only with COMPOSE_PROFILES=ios-resign (see README.md).
# netmuxd needs glibc 2.38+, so trixie rather than bookworm.
FROM debian:trixie-slim

ARG ALTSERVER_URL=https://github.com/jaakkopalvaila/AltServer-Linux/releases/latest/download/AltServer-x86_64
ARG NETMUXD_URL=https://github.com/jkcoxson/netmuxd/releases/latest/download/netmuxd-x86_64-unknown-linux-gnu.tar.gz

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates curl python3 libimobiledevice-utils libavahi-compat-libdnssd1 tini \
    && rm -rf /var/lib/apt/lists/*

RUN set -e; \
    curl -fsSL -o /usr/local/bin/AltServer "$ALTSERVER_URL" \
        || { echo "AltServer download failed: set ALTSERVER_URL (see ios-resign/README.md)"; exit 1; }; \
    curl -fsSL "$NETMUXD_URL" -o /tmp/netmuxd.tgz \
        || { echo "netmuxd download failed: set NETMUXD_URL (see ios-resign/README.md)"; exit 1; }; \
    tar -xzf /tmp/netmuxd.tgz -C /usr/local/bin netmuxd; rm /tmp/netmuxd.tgz; \
    chmod +x /usr/local/bin/AltServer /usr/local/bin/netmuxd; \
    /usr/local/bin/netmuxd --help >/dev/null

COPY resign.py /app/resign.py
WORKDIR /data
EXPOSE 8099
ENTRYPOINT ["/usr/bin/tini", "--", "python3", "-u", "/app/resign.py"]
