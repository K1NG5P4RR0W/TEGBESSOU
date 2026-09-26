# egress-gateway (E3a + allowlist B réelle E3b)

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

Un fichier par politique, un nom d'hôte par ligne, `#` pour commentaire.
Monté en lecture seule dans le conteneur (`/etc/egress/policy/...`) — **le
worker n'y a ni accès réseau ni accès disque**, il ne peut jamais la modifier.

Pour appliquer un changement de politique :
```
docker compose restart egress-gateway
```
(l'entrypoint régénère les maps nginx au démarrage à partir du fichier monté)

- `policy/allowlist-test.conf` : allowlist de TEST (E3a), `example.com` — sert
  aux vérifications manuelles de la barrière ci-dessous, à vide de tout outil
  réel.
- `policy/allowlist-osint.conf` : **allowlist B (E3b)**, sources passives fixes
  de subfinder, sans clé API — voir ce fichier pour la correspondance exacte
  source → endpoint (vérifiée contre le code source de subfinder v2.16.0, pas
  supposée) et les sources volontairement exclues.
- `policy/allowlist-target-test.conf` : **allowlist A de TEST (E3 final)**,
  `example.com` — la cible in-scope pour httpx (trafic ACTIF). Voir
  « Mécanisme de l'allowlist A » ci-dessous.

`EGRESS_POLICY_FILE` (dans `docker-compose.yml`) charge les deux fichiers
**ensemble**, séparés par `:` — c'est `entrypoint.sh` qui fusionne les hôtes
des deux dans les mêmes maps nginx. Toujours un seul sas, une seule politique
pour tout le stack ; tout hôte absent des deux fichiers reste refusé
(deny-par-défaut inchangé).

## Mécanisme de l'allowlist A (cibles in-scope, E3 final)

Contrairement à l'allowlist B (sources OSINT, curée une fois pour toutes),
l'allowlist A devrait en théorie suivre le scope de CHAQUE engagement,
résolu dynamiquement à l'activation (voir `docs/E3_EGRESS_DESIGN.md` §6).
Cette PR ne construit **pas** ce mécanisme dynamique : `allowlist-target-test.conf`
est un fichier **statique**, au même patron que `allowlist-osint.conf`,
contenant la cible du scénario de démonstration (`example.com`). C'est un
scaffolding de preuve — il prouve que httpx sort bien par l'allowlist A côté
sas, pas que l'allowlist A se régénère automatiquement par engagement.

La génération dynamique par engagement (résoudre le scope actif, pousser la
politique résultante à la passerelle — fichier régénéré + `docker compose
restart egress-gateway`, ou une future API interne) reste explicitement hors
périmètre, tracée comme itération séparée (B5, cf. §6/§10 du design doc) —
pas traitée ici. Ne pas confondre : le Scope Enforcer applicatif (barrière 1,
toujours actif, cf. plus bas) refuse déjà toute cible hors scope AVANT la
mise en file ; l'allowlist A statique de cette PR est la barrière 2 (réseau),
volontairement restreinte à la seule cible de démonstration pour ne pas
élargir le sas au-delà du strict nécessaire.

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

## Vérifier subfinder à travers le sas (E3b)

Preuve de bout en bout : scope → enqueue → worker → sas d'egress (allowlist B)
→ résultat → persistance → audit.

```
make up
make create-admin   # ADMIN_EMAIL=... ADMIN_PASSWORD=... si non interactif

TOKEN=$(curl -s -X POST http://127.0.0.1:8001/auth/login -H "Content-Type: application/json" \
  -d '{"email":"<ADMIN_EMAIL>","password":"<ADMIN_PASSWORD>"}' | jq -r .access_token)

# 1. Engagement actif + cible in-scope.
EID=$(curl -s -X POST http://127.0.0.1:8001/engagements -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"e3b","mode":"ctf"}' | jq -r .id)
curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/authorization" -H "Authorization: Bearer $TOKEN" \
  -F source_kind=program_url -F program_url=https://p/rules
curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/activate" -H "Authorization: Bearer $TOKEN"
curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/scope" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"kind":"domain","value":"hackerone.com","disposition":"in_scope"}'

# 2. Job subfinder réel sur la cible in-scope.
TID=$(curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/tasks/subfinder" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"target":"hackerone.com"}' | jq -r .id)

# 3. Attendre la fin du job, puis poller (le poll persiste assets + audit).
sleep 20
curl -s "http://127.0.0.1:8001/engagements/$EID/tasks/$TID" -H "Authorization: Bearer $TOKEN"
# -> {"status":"done", ...}

# 4. Les 8 sources OSINT contactées apparaissent, AUCUNE en refus, dans les logs du sas.
docker compose logs egress-gateway | grep -E \
  "api.hackertarget.com|rapiddns.io|anubisdb.com|www.sitedossier.com|web.archive.org|certificatedetails.com|index.commoncrawl.org|api.sub.md"
docker compose logs egress-gateway | grep -iE "deny|403" | grep -E \
  "api.hackertarget.com|rapiddns.io|anubisdb.com|www.sitedossier.com|web.archive.org|certificatedetails.com|index.commoncrawl.org|api.sub.md"
# -> ne doit rien renvoyer : aucune des 8 sources n'a été bloquée.

# 5. Deny-par-défaut TOUJOURS intact : une destination hors allowlist reste bloquée.
docker compose exec worker python3 -c "
import socket, ssl
ctx = ssl.create_default_context()
ctx.wrap_socket(socket.create_connection(('example.org', 443), timeout=6), server_hostname='example.org')"
                                                          # doit échouer (SSLEOFError)
docker compose logs egress-gateway | grep example.org    # refus loggé

# 6. Scope enforcé : cible hors scope refusée avant même la mise en file.
curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://127.0.0.1:8001/engagements/$EID/tasks/subfinder" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"target":"hors-scope.example"}'
# -> 403 (+ ligne audit "scope.violation" — voir table audit_log)

# 7. Régression E1/E3a : le worker n'a toujours aucun accès direct DB/Internet.
docker compose exec worker python3 -c "
import socket
socket.create_connection(('postgres', 5432), timeout=3)" # doit échouer
docker compose exec worker env | grep -i postgres         # doit être vide
```

Les sources sans clé peuvent renvoyer 0 résultat pour un domaine donné sans
que ce soit un échec de la barrière (c'est le contenu OSINT qui varie, pas le
filtrage réseau) — ce qui compte pour la preuve E3b est l'absence de refus
dans les logs du sas pour les 8 hôtes de l'allowlist B, pas le nombre exact de
sous-domaines trouvés.

## Vérifier httpx à travers le sas (E3 final)

Preuve de bout en bout : scope → enqueue → worker → sas d'egress (allowlist A,
cible de TEST) → résultat → persistance (assets `kind=host`) → audit. Suite
directe du scénario subfinder ci-dessus (même engagement, ou un nouveau).

```
TOKEN=$(curl -s -X POST http://127.0.0.1:8001/auth/login -H "Content-Type: application/json" \
  -d '{"email":"<ADMIN_EMAIL>","password":"<ADMIN_PASSWORD>"}' | jq -r .access_token)

EID=$(curl -s -X POST http://127.0.0.1:8001/engagements -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"name":"e3-final","mode":"ctf"}' | jq -r .id)
curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/authorization" -H "Authorization: Bearer $TOKEN" \
  -F source_kind=program_url -F program_url=https://p/rules
curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/activate" -H "Authorization: Bearer $TOKEN"
# La cible in-scope DOIT être la même que l'allowlist A de test
# (policy/allowlist-target-test.conf) pour que le job sorte réellement du sas.
curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/scope" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"kind":"domain","value":"example.com","disposition":"in_scope"}'

# 1. Job httpx réel sur la cible in-scope == cible de l'allowlist A.
TID=$(curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/tasks/httpx" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"target":"example.com"}' | jq -r .id)

sleep 10
curl -s "http://127.0.0.1:8001/engagements/$EID/tasks/$TID" -H "Authorization: Bearer $TOKEN"
# -> {"status":"done", ...}

# 2. httpx a bien contacté example.com par le sas, aucun refus loggé pour cet hôte.
docker compose logs egress-gateway | grep -i "example.com" | grep -viE "deny|403"
docker compose logs egress-gateway | grep -iE "deny|403" | grep -i "example.com"
# -> ne doit rien renvoyer.

# 3. L'hôte vivant est persisté en assets (kind=host, discovered_by=httpx) + audit task.run.
SCHEMA=$(docker compose exec -T postgres psql -U ${POSTGRES_USER:-tegbessou_app} \
  -d ${POSTGRES_DB:-tegbessou} -tAc "SELECT schema_name FROM engagements WHERE id='$EID'")
docker compose exec -T postgres psql -U ${POSTGRES_USER:-tegbessou_app} -d ${POSTGRES_DB:-tegbessou} \
  -c "SELECT kind, value, discovered_by FROM \"$SCHEMA\".assets;"
# -> kind=host, discovered_by=httpx, value contient example.com

# 4. Scope enforcé : cible hors scope refusée avant même la mise en file.
curl -s -o /dev/null -w "%{http_code}\n" -X POST "http://127.0.0.1:8001/engagements/$EID/tasks/httpx" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"target":"hors-scope.example"}'
# -> 403 (+ ligne audit "scope.violation")

# 5. Le sas ne fait PAS confiance au seul scope applicatif : même en mettant
# artificiellement une cible in-scope QUI N'EST PAS dans l'allowlist A de
# test, le job doit rester bloqué au niveau réseau (timeout/échec du poll, ou
# `failed` selon le comportement de httpx sur une connexion refusée).
curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/scope" -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" -d '{"kind":"domain","value":"example.org","disposition":"in_scope"}'
TID2=$(curl -s -X POST "http://127.0.0.1:8001/engagements/$EID/tasks/httpx" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"target":"example.org"}' | jq -r .id)
sleep 10
curl -s "http://127.0.0.1:8001/engagements/$EID/tasks/$TID2" -H "Authorization: Bearer $TOKEN"
# -> httpx échoue à se connecter (hôte hors allowlist A) : la tâche ne persiste aucun asset.
docker compose logs egress-gateway | grep -i "example.org"   # refus loggé (SNI/Host)

# 6. Étanchéité des deux allowlists chargées ensemble : subfinder n'atteint
# QUE les 8 sources OSINT (allowlist B), jamais example.com (allowlist A) ;
# httpx n'atteint QUE la cible donnée (ici example.com), jamais une source
# OSINT. Ce n'est pas une propriété du sas seul (les deux hôtes sont
# effectivement autorisés par la politique combinée) mais de la commande
# construite par chaque wrapper : `SubfinderWrapper.build_args` ne passe
# jamais `-u example.com`, `HttpxWrapper.build_args` ne référence jamais les
# hôtes OSINT. Le job subfinder de la section précédente (E3b) reste
# reproductible ici sans régression :
docker compose logs egress-gateway | grep -c "example.com"    # > 0 (httpx, cette section)
docker compose logs egress-gateway | grep -iE \
  "api.hackertarget.com|rapiddns.io|anubisdb.com|www.sitedossier.com|web.archive.org|certificatedetails.com|index.commoncrawl.org|api.sub.md" \
  | grep -c "example.com"                                      # -> 0 : aucune ligne ne mélange les deux

# 7. Régression E1/E3a/E3b : le worker n'a toujours aucun accès direct DB/Internet.
docker compose exec worker python3 -c "
import socket
socket.create_connection(('postgres', 5432), timeout=3)" # doit échouer
docker compose exec worker env | grep -i postgres         # doit être vide
```

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
