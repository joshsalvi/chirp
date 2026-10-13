FROM nginx:alpine

# Custom entrypoint fixes a real, confirmed permission problem before
# nginx starts — see docker-entrypoint.sh's own comment for the full
# story and the real error this fixes.
COPY docker-entrypoint.sh /custom-entrypoint.sh
RUN chmod +x /custom-entrypoint.sh

ENTRYPOINT ["/custom-entrypoint.sh"]
