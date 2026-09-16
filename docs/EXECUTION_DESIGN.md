# E0 — Conception de la couche d'exécution

> Document de référence (design, pas de code). À lire avant de coder tout module
> qui exécute un outil vers une cible. C'est le seul endroit où une erreur a un
> vrai coût de sécurité : on le pense à fond d'abord.

## Objectif
Permettre au système d'exécuter des outils (subfinder, httpx, nmap…) vers une
cible **sans jamais** : (a) sortir du périmètre autorisé, (b) exposer la base ou
les secrets si un outil est compromis, (c) bloquer la gateway ou noyer le LLM.

## Principes
1. **Le worker est le seul composant qui touche la cible** — donc le plus isolé.
2. **Deux barrières de périmètre** : applicative (Scope Enforcer, déjà construit)
   ET réseau (egress du worker). Une seule ne suffit jamais.
3. **Le worker n'a pas accès à la base** : il exécute, normalise, renvoie. La
   gateway persiste et journalise.
4. **Découplage par file** : la gateway pousse un job, le worker le consomme.
   L'exécution ne passe pas par le contexte du LLM.

## Décisions arrêtées

| Sujet | Décision |
|---|---|
| Où tourne le worker | Conteneur dédié, sandboxé : `cap_drop: ALL`, non-root, `read_only`, `no-new-privileges`, seccomp/apparmor |
| Communication gateway↔worker | File **arq** sur Redis (pas d'appel HTTP direct) |
| Accès DB du worker | **Aucun** — le worker ne connaît ni la base ni les secrets |
| Application du scope | À l'entrée (gateway, avant l'enqueue) + egress réseau (worker) |
| Anti-injection | Wrappers à **arguments typés**, tableau d'arguments, jamais `shell=True` |
| Résultat | Sortie **normalisée** par le worker, persistée côté gateway |
| Annulation / kill switch | `asyncio` subprocess + abort arq → tuer un job en cours proprement |
| Timeout | Chaque job a une limite de temps ; dépassement = échec journalisé |

## Modèle d'egress — strict par conception, implémenté progressivement

**Cible finale : deny par défaut.** Le worker ne peut sortir que vers :
- Redis (file de jobs, réseau interne) ;
- le résolveur DNS ;
- **les hôtes in-scope de l'engagement courant** (trafic *actif* : httpx, nmap…) ;
- **un jeu curé de sources OSINT approuvées** (trafic *passif* : crt.sh, chaos…),
  car les outils passifs interrogent des tiers, pas la cible.

> Nuance clé : l'allowlist n'est donc PAS « seulement les cibles ». C'est
> `cibles in-scope + sources OSINT approuvées`. Le trafic actif vise la cible,
> le trafic passif vise les sources — le proxy à allowlist distingue les deux.

**Le point de conception clé :** tout le trafic sortant des outils passe par un
**point d'étranglement unique** (un proxy d'egress / une chaîne de pare-feu) qui
lit la liste des cibles autorisées de l'engagement. Ainsi, durcir plus tard =
changer une configuration, pas ré-architecturer.

**Point d'étranglement — décision : proxy sidecar d'abord.** Les premiers outils
RECON sont massivement HTTP/DNS-API : un proxy à allowlist par hôte les couvre et
s'aligne sur le scope (basé hôtes). nftables complète pour les outils non-HTTP
(nmap) quand ils arrivent. Cible finale = proxy (web) + nftables (le reste).

**Plan progressif :**
- **Maintenant (E1→E3)** : la barrière *active* est le Scope Enforcer applicatif.
  Le worker tourne sur un **réseau Docker isolé**, séparé du réseau
  d'orchestration ; le trafic outil est déjà **routé** à travers le point
  d'étranglement (proxy/nftables), configuré en mode permissif. La plomberie est
  en place, la politique est lâche.
- **Durcissement (phase B5)** : bascule du point d'étranglement en **deny par
  défaut + allowlist par engagement** (les IP résolues des cibles in-scope,
  injectées pour la durée du job). Trafic HTTP(S) via proxy à allowlist ; trafic
  non-HTTP (nmap, DNS) via règles nftables sur le namespace réseau du worker.

> Conséquence concrète pour le code d'aujourd'hui : les wrappers d'outils doivent
> **accepter une configuration de proxy/sortie** dès le départ (même si elle est
> permissive), pour que le durcissement ne les touche pas.

## Architecture

```
Opérateur → Gateway
              │  1. Scope Enforcer valide la cible (sinon 403 + audit)
              │  2. enqueue_job(arq) {tool, target, args, timeout}
              ▼
         Redis (file arq)
              ▼
   Worker arq — conteneur sandboxé, SANS DB, réseau isolé
              │  3. wrapper à args typés → asyncio.create_subprocess_exec
              │     (trafic outil via le point d'étranglement d'egress)
              │  4. normalise la sortie (structure minimale, pas de dump brut)
              ▼
         Redis (résultat du job)
              ▼
         Gateway — collecteur
                 5. récupère le résultat, persiste (tasks/assets), append_audit
```

## Cycle de vie d'un job
`queued → running → done | failed | killed`
- **queued** : mis en file après validation du scope.
- **running** : pris par un worker ; timeout armé.
- **done** : résultat normalisé récupéré et persisté par la gateway.
- **failed** : erreur outil / timeout — journalisé.
- **killed** : kill switch — abort arq + `SIGTERM`/`SIGKILL` au sous-processus.

## E1 — première brique (prouver la plomberie SANS toucher une cible)
Objectif : valider tout le tuyau avec une commande **triviale et sûre**, aucun
réseau vers l'extérieur.
- Ajouter le service `worker` (arq) au `docker-compose`, **sur un réseau Docker
  dédié** séparé de l'orchestration : le worker atteint Redis et RIEN d'autre en
  interne (ni PostgreSQL, ni secrets). C'est l'ancrage sécurité réel de E1.
  Le point d'étranglement d'egress N'est PAS implémenté en E1 (aucun trafic vers
  l'extérieur à gater) — il arrive à E3 avec les vrais outils.
- Gateway : `enqueue` d'un job « noop » (ex. exécuter `echo`/`id` dans le sandbox).
- Worker : exécute via `asyncio.create_subprocess_exec` (args en tableau), renvoie
  `{stdout, exit_code, duration}` normalisé.
- Gateway : collecteur qui récupère le résultat et écrit une ligne `tasks`
  (phase=`recon`, tool=`noop`, status=`done`) + `append_audit(action="task.run")`.
- **Critères de Done** : job enqueued → exécuté → résultat persisté → audité ;
  timeout testé (un job trop long → `failed`) ; kill testé (un job en cours →
  `killed`) ; le worker n'a **pas** de credentials DB (vérifié) ; tests contre
  vrai PostgreSQL.

> Une fois E1 prouvé, E2 branche les vrais wrappers (subfinder/httpx) et E3 le
> premier module RECON réel — le trafic passe alors par le Scope Enforcer et le
> point d'étranglement d'egress.

## Ce que ça n'inclut PAS encore (volontairement)
- Le durcissement egress deny-par-défaut (conçu ici, implémenté en B5).
- Le streaming temps réel des résultats au dashboard (brique ultérieure).
- La parallélisation multi-workers (triviale ensuite : `--scale worker=N`).
