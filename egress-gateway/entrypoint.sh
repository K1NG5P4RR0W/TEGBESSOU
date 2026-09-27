#!/bin/bash
# Point d'entrée de la passerelle d'egress.
#
# 1. Génère les maps nginx (Host / SNI) depuis la politique montée.
# 2. Charge le ruleset nftables (deny-par-défaut + redirections locales).
# 3. Démarre dnsmasq (résolveur contrôlé), nginx (filtrage Host/SNI) et
#    ulogd (journalisation des refus), capabilities Linux minimales (voir
#    §3 plus bas), et fusionne leurs logs sur stdout pour `docker compose logs`.
set -euo pipefail

: "${WORKER_NET_SUBNET:?WORKER_NET_SUBNET requis}"
: "${EGRESS_POLICY_FILE:=/etc/egress/policy/allowlist-test.conf}"

mkdir -p /var/log/egress /etc/nginx/generated

# --- 1. Génération des maps nginx depuis la politique -----------------------
# Le worker n'a ni accès réseau ni accès disque à ce fichier : c'est la
# passerelle (et elle seule) qui lit la politique et matérialise les règles.
#
# EGRESS_POLICY_FILE peut lister PLUSIEURS fichiers séparés par ':' (chaque
# fichier reste une allowlist statique, versionnée, revue séparément) : c'est
# ainsi que l'allowlist B (OSINT, subfinder) et l'allowlist A (cible in-scope,
# httpx) sont chargées ENSEMBLE dans ce sas unique — union des hôtes, mais
# toujours deny-par-défaut pour tout le reste (voir docs/E3_EGRESS_DESIGN.md
# §6 et egress-gateway/README.md pour la limite : une seule politique pour
# tout le stack, pas encore une par engagement — génération dynamique = B5).
: > /etc/nginx/generated/allowed_hosts.map
: > /etc/nginx/generated/allowed_tls_upstreams.map
IFS=':' read -ra _policy_files <<< "$EGRESS_POLICY_FILE"
for _policy_file in "${_policy_files[@]}"; do
    while IFS= read -r host; do
        host="${host%%#*}"
        host="$(echo -n "$host" | tr -d '[:space:]')"
        [ -z "$host" ] && continue
        echo "${host} 1;" >> /etc/nginx/generated/allowed_hosts.map
        echo "${host} ${host}:443;" >> /etc/nginx/generated/allowed_tls_upstreams.map
    done < "$_policy_file"
done

echo "[egress-gateway] politique chargée depuis ${EGRESS_POLICY_FILE} :"
sed 's/^/[egress-gateway]   allow /' /etc/nginx/generated/allowed_hosts.map

# --- 2. Ruleset nftables -----------------------------------------------------
sed "s#\$WORKER_NET_SUBNET#${WORKER_NET_SUBNET}#g" /etc/egress/nftables.conf > /tmp/nftables.rendered.conf
nft -f /tmp/nftables.rendered.conf
echo "[egress-gateway] nftables chargé (deny-par-défaut sur forward)."

# --- 3. Démarrage des services (non-root) -----------------------------------
nginx -t -c /etc/egress/nginx.conf

# nginx/dnsmasq/ulogd tournent tous les trois avec les MÊMES capabilities
# Linux que le conteneur (cap_drop: ALL + cap_add: NET_ADMIN, NET_RAW —
# voir docker-compose.yml) : ulogd a besoin de NET_ADMIN pour lire le socket
# NFLOG, ce qui empêche de les faire tourner sous un UID non privilégié sans
# capabilities ambiantes. La frontière de sécurité est la capability Linux,
# pas l'UID : aucune autre capability que NET_ADMIN/NET_RAW n'est présente.
dnsmasq -C /etc/egress/dnsmasq.conf &
DNSMASQ_PID=$!

nginx -c /etc/egress/nginx.conf -g "daemon off;" &
NGINX_PID=$!

ulogd -c /etc/egress/ulogd.conf &
ULOGD_PID=$!

# Fusionne les logs pertinents sur stdout (docker compose logs egress-gateway).
tail -F /var/log/egress/deny.log /var/log/egress/http-deny.log /var/log/egress/tls-egress.log 2>/dev/null &
TAIL_PID=$!

trap 'kill -TERM $DNSMASQ_PID $NGINX_PID $ULOGD_PID $TAIL_PID 2>/dev/null || true' TERM INT

wait -n $DNSMASQ_PID $NGINX_PID $ULOGD_PID
echo "[egress-gateway] un service critique s'est arrêté, extinction." >&2
kill -TERM $DNSMASQ_PID $NGINX_PID $ULOGD_PID $TAIL_PID 2>/dev/null || true
wait
