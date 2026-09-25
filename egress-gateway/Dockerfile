# Passerelle d'egress (E3a) — sidecar sandboxé, aucun accès DB/secrets.
# Base nginx officielle (module stream + ssl_preread compilés en standard)
# + nftables/dnsmasq/ulogd pour le filtrage L3/L4, DNS et la journalisation.
FROM nginx:1.27-alpine

RUN apk add --no-cache nftables dnsmasq ulogd ulogd-json bash \
    && rm -f /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/egress/nginx.conf
COPY nftables.conf /etc/egress/nftables.conf
COPY dnsmasq.conf /etc/egress/dnsmasq.conf
COPY ulogd.conf /etc/egress/ulogd.conf
COPY entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /usr/local/bin/entrypoint.sh

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
