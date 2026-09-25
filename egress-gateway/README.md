# egress-gateway (E3a)

Sidecar d'egress du worker. Deny-par-défaut : le worker ne peut atteindre
que ce que cette passerelle autorise explicitement. Voir
`docs/E3_EGRESS_DESIGN.md` (suivi privé) pour la conception complète.

## Ce que ça fait

- Le worker n'a **aucune route Internet directe** : il est sur `worker_net`
  (`internal: true`, donc aucune NAT Docker vers l'extérieur). Le service
  jetable `worker-netinit` (partage le netns du worker, `NET_ADMIN` le temps
  d'une seule commande, puis s'arrête) réécrit sa route par défaut vers l'IP
  statique d'egress-gateway — le worker lui-même ne reçoit jamais cette
  capability.
- **HTTP** (port 80) : filtrage par en-tête `Host`, en clair.
- **HTTPS** (port 443) : filtrage par **SNI** (lu dans le ClientHello TLS,
  `ssl_preread`), **sans déchiffrer** — aucune clé privée, aucune CA
  injectée dans le worker. La connexion autorisée est relayée en TCP brut,
  octet pour octet, vers la vraie origine.
- **DNS** : le worker pointe directement sur cette passerelle comme
  résolveur (`dns:` dans docker-compose.yml) — le résolveur interne de
  Docker (127.0.0.11) refuse de transiter les requêtes externes sur un
  réseau `internal: true`, donc ce n'est de toute façon pas une option pour
  le worker. nftables redirige en plus tout `:53` sortant du worker vers
  `dnsmasq` local, qui est le seul résolveur que le worker peut atteindre.
- **Tout le reste** (autre port/protocole) : bloqué par nftables
  (chaîne `forward`, `policy drop` + règle terminale loggée via ulogd).

## Fournir la politique (allowlist)

Fichier `policy/allowlist-test.conf`, un nom d'hôte par ligne, `#` pour
commentaire. Monté en lecture seule dans le conteneur
(`/etc/egress/policy/...`) — **le worker n'y a ni accès réseau ni accès
disque**, il ne peut jamais la modifier.

Pour appliquer un changement de politique :
```
docker compose restart egress-gateway
```
(l'entrypoint régénère les maps nginx au démarrage à partir du fichier monté)

Pour E3a, la liste est **statique et de test** (`example.com`). Le
durcissement par engagement (allowlist A = cibles in-scope résolues,
allowlist B = sources OSINT curées, injectées par la Gateway au lancement
d'un run) est prévu par le design mais **hors périmètre d'E3a** — voir
`docs/E3_EGRESS_DESIGN.md` §6.

## Lire les logs de refus

```
docker compose logs -f egress-gateway
```
Trois flux fusionnés sur stdout :
- `deny.log` (nftables/ulogd) : tout paquet non-DNS/HTTP/HTTPS refusé au
  niveau L3/L4, avec IP/port source et destination.
- `http-deny.log` (nginx) : requêtes HTTP dont le `Host` n'est pas autorisé
  (403).
- `tls-egress.log` (nginx stream) : chaque connexion HTTPS interceptée, avec
  le SNI demandé et l'upstream choisi (`127.0.0.1:1` = refusé, non
  atteignable = refus immédiat côté client).

## Vérifier la barrière (E3a, à vide)

```
make up
docker compose exec worker python3 -c "
import socket, ssl
ctx = ssl.create_default_context()
s = ctx.wrap_socket(socket.create_connection(('example.com', 443), timeout=6), server_hostname='example.com')
print('OK', s.version())"                              # doit réussir

docker compose exec worker python3 -c "
import socket, ssl
ctx = ssl.create_default_context()
ctx.wrap_socket(socket.create_connection(('example.org', 443), timeout=6), server_hostname='example.org')"
                                                          # doit échouer (SSLEOFError)
docker compose logs egress-gateway | grep example.org    # refus loggé avec le SNI

docker compose exec worker python3 -c "
import socket
socket.create_connection(('1.1.1.1', 22), timeout=5)"    # doit échouer : aucune route directe

docker compose exec worker python3 -c "
import socket
socket.create_connection(('postgres', 5432), timeout=3)" # doit échouer (régression E1)
docker compose exec worker env | grep -i postgres        # doit être vide
```

## Fail-closed : fenêtre de démarrage et échec de worker-netinit

**Garantie : le worker ne récupère jamais de route permissive.** Deux cas
vérifiés (voir la session de dev pour les commandes exactes) :

1. **Avant que `worker-netinit` ait tourné** — Docker n'installe **aucune
   route par défaut** sur un réseau `internal: true` (ni la sienne, ni celle
   d'un tiers) : `cat /proc/net/route` dans le worker ne montre que la route
   de sous-réseau local, pas de ligne `0.0.0.0`. Une tentative de connexion
   externe échoue immédiatement avec `OSError: Network is unreachable` —
   rejetée par le noyau, aucun paquet n'est émis. Il n'y a donc pas de
   fenêtre permissive : c'est fail-closed par défaut, pas par notre
   configuration.
2. **Si `worker-netinit` échoue** (testé avec une passerelle invalide/hors
   sous-réseau) — `ip route replace` est atomique : un échec ne laisse
   **aucune** entrée de route, la table reste inchangée (donc toujours
   aucune route par défaut). Le worker reste bloqué à l'identique du cas 1.
   `worker-netinit` a `restart: "no"` : un échec est **terminal et visible**
   (`docker compose ps` montre `Exited (>0)`, pas de nouvelle tentative
   automatique) — le worker reste sans egress tant que l'opérateur n'a pas
   corrigé et relancé `docker compose up -d worker-netinit`. C'est un choix
   délibéré : en cas de doute sur l'état de la route, le worker doit rester
   injoignable plutôt que de retomber sur un comportement par défaut
   (silencieusement fail-open serait le risque inverse).

## Limites connues (honnêtes, pour E3a)

- **DNS non filtré par nom** : le résolveur contrôlé (`dnsmasq`) résout
  actuellement n'importe quel domaine ; le contrôle réel se fait en aval,
  sur la connexion (Host/SNI + nftables), pas sur la résolution elle-même.
  Filtrer aussi les noms résolus (bloquer une résolution DNS vers un domaine
  hors allowlist, pas seulement la connexion qui suit) est une itération
  future, pas un besoin d'E3a puisqu'aucun outil réel n'est branché ici.
- **SNI chiffré (ECH)** : si une origine utilise Encrypted Client Hello, le
  SNI n'est plus lisible en clair et le filtrage par nom échoue pour cette
  connexion. Repli prévu : nftables (IP) ou refus — pas traité dans E3a.
- **Redis comme relais potentiel** : Redis est rattaché à `worker_net` pour
  que le worker le joigne directement (hors passerelle, cf. topologie). Ce
  n'est PAS une route de sortie réseau : Redis ne proxifie ni ne relaie de
  trafic arbitraire, et il n'est lui-même joignable par le worker que pour
  le protocole Redis (queue arq). Un abus applicatif de Redis comme canal de
  données (ex. faire transiter des octets arbitraires dans des clés/valeurs
  pour qu'un autre composant les relaie ensuite) est une question de
  confiance applicative sur le contrat de job (couverte par le Scope
  Enforcer et la chaîne d'audit, hors périmètre réseau d'E3a), pas une
  brèche dans la barrière d'egress elle-même.
