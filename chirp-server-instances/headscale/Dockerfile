# The official headscale/headscale image is minimal (no shell at all —
# confirmed the hard way: "stat /bin/sh: no such file or directory"
# when trying to run entrypoint.sh directly against it). This builds a
# small wrapper around it instead of guessing at a fix: extract the
# real headscale binary out of the official image, put it on a real
# Alpine base that has /bin/sh, and run the bootstrap script there.
#
# The binary's exact path inside the official image isn't something
# this Dockerfile assumes — it's found at build time via `find` across
# the whole extracted filesystem, so this doesn't silently break again
# if a future headscale release reorganizes its own image layout.
FROM headscale/headscale:0.23.0 AS headscale-src

FROM alpine:3.20
RUN apk add --no-cache ca-certificates bash python3

COPY --from=headscale-src / /headscale-src/
RUN HS_BIN=$(find /headscale-src -maxdepth 6 -type f -iname "headscale" | head -1) && \
    test -n "$HS_BIN" && \
    cp "$HS_BIN" /usr/bin/headscale && \
    chmod +x /usr/bin/headscale && \
    rm -rf /headscale-src && \
    /usr/bin/headscale version

COPY entrypoint.sh /etc/headscale/entrypoint.sh
RUN chmod +x /etc/headscale/entrypoint.sh
COPY api-wrapper.py /etc/headscale/api-wrapper.py

ENTRYPOINT ["/bin/sh", "/etc/headscale/entrypoint.sh"]
