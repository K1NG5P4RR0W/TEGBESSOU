# TEGBESSOU — Document d'implémentation complet

> Plateforme d'assistance au pentest Web2 / Web3 — orchestration multi-agent, *human-in-the-loop*, pilotable via dashboard (avec DevTools intégrés) et CLI.
>
> **Marque produit :** zeromisconfig
> **Version du document :** 2.3 — **Août 2026** (v2.0 : renommage + intro + DevTools + modularité ; v2.1 : orchestration des modules dans la Gateway → ~6 workflows n8n, mode bug bounty enrichi + upload du lien de programme ; v2.2 : document rendu partageable ; v2.3 : marque éditrice retirée du corps, ajout de la carte de reconnaissance — graphe de surface d'attaque type BloodHound orienté web)
> **Public visé :** équipe cybersécurité (2 personnes aujourd'hui, extensible)
> **Documents liés :** `docs/AGENTS.md` (spécification approfondie des agents et de la méthodologie).
> **Statut :** spécification d'implémentation — à lire intégralement avant le premier `git init`.

---

## Table des matières

0. [Introduction — pourquoi cette architecture et non un simple agent](#0-introduction--pourquoi-cette-architecture-et-non-un-simple-agent)
1. [Vision et principes non négociables](#1-vision-et-principes-non-négociables)
2. [Ce que l'outil fait (et ne fait pas)](#2-ce-que-loutil-fait-et-ne-fait-pas)
3. [Architecture globale](#3-architecture-globale)
4. [Topologie de déploiement](#4-topologie-de-déploiement)
5. [Les composants en détail](#5-les-composants-en-détail)
6. [Le modèle multi-agent et son évolutivité](#6-le-modèle-multi-agent-et-son-évolutivité)
7. [Couche LLM multi-fournisseurs](#7-couche-llm-multi-fournisseurs)
8. [Base de connaissances (RAG)](#8-base-de-connaissances-rag)
9. [Le dashboard — pilotage complet et DevTools intégrés](#9-le-dashboard--pilotage-complet-et-devtools-intégrés)
10. [La CLI](#10-la-cli)
11. [Modèle de données](#11-modèle-de-données)
12. [Performance — les décisions qui comptent](#12-performance--les-décisions-qui-comptent)
13. [Sécurité de l'outil lui-même](#13-sécurité-de-loutil-lui-même)
14. [Gardes anti-usage malhonnête](#14-gardes-anti-usage-malhonnête)
15. [Structure du dépôt GitHub](#15-structure-du-dépôt-github)
16. [Installation et déploiement](#16-installation-et-déploiement)
17. [Workflow de développement en équipe](#17-workflow-de-développement-en-équipe)
18. [Feuille de route par briques](#18-feuille-de-route-par-briques)
19. [Annexes](#19-annexes)

---

## 0. Introduction — pourquoi cette architecture et non un simple agent

La tentation, en 2026, est de brancher un LLM puissant sur une boîte à outils (nmap, nuclei, Burp exposés en MCP) et de le laisser « faire le pentest ». C'est séduisant sur une démo. C'est une impasse pour un cabinet qui engage sa responsabilité. Tegbessou fait un autre choix, et voici **pourquoi**, argument par argument.

**1. Le plafond d'autonomie est réel et bas.** Les meilleurs systèmes agentiques documentés n'accomplissent de façon autonome que 15 à 25 % des tâches d'un pentest ; au-delà, ils hallucinent, perdent le contexte sur les séquences longues, et enchaînent des actions sans comprendre l'enjeu. Un outil qui « marche à 20 % tout seul » n'est pas un outil de production — c'est une démo. Tegbessou vise 100 % des missions menées à bien, avec l'humain aux commandes des 80 % que la machine ne sait pas trancher seule.

**2. Un pentest doit être imputable.** Une mission repose sur une autorisation signée, un scope, une traçabilité et une signature humaine. Un agent autonome ne peut pas *porter* cette responsabilité : il ne peut pas attester avoir respecté le mandat, ni répondre en cas de litige. L'architecture de Tegbessou câble l'autorisation, le scope et l'audit dans le chemin critique — ce n'est pas une politique, c'est du code bloquant. En cas de contestation, le journal inaltérable et l'autorisation scellée prouvent que l'équipe a agi dans le cadre.

**3. La qualité vient de la spécialisation et de la preuve, pas de l'omniscience.** Cinq agents spécialisés, chacun avec un prompt taillé, un jeu d'outils borné et une base de connaissances ciblée, produisent un raisonnement plus net qu'un LLM généraliste qui fait tout dans une seule boucle. Surtout : chaque affirmation est étayée par un artefact. « Trouvé un endpoint » ne vaut rien ; « trouvé cet endpoint dans ce fichier, absent de l'API documentée, voici comment le valider » vaut de l'or. Un agent unique noyé dans son contexte produit des findings fantômes ; une chaîne spécialisée produit des findings défendables.

**4. L'expertise du pentester EST la valeur.** Le client ne paie pas pour un scanner, il paie pour le jugement d'un professionnel qui comprend les risques, oriente l'effort, et écarte les fausses pistes. Tegbessou **amplifie** ce jugement (il fait le travail lourd : recon massive, lecture de 3 000 lignes de JS obfusqué, corrélation CVE, rédaction) et le **laisse décider** aux points qui comptent. Remplacer le jugement par une boucle autonome, c'est jeter la seule chose qui a de la valeur.

**5. Le coût et le comportement doivent être prévisibles.** Une boucle agentique qui balance tout dans le contexte du LLM inonde ce contexte de schémas d'outils et de traces, dégrade le raisonnement, et fait exploser la facture (un framework de référence tournait à ~96 $ le run non maîtrisé). En sortant l'exécution du contexte (file de jobs + sorties normalisées) et en bornant le budget par engagement, on rend le coût prévisible et le comportement reproductible.

**6. Un livrable se reproduit ; une boîte noire, non.** Un rapport et un scénario rejouable exigent des étapes déterministes et journalisées. Une chaîne d'agent opaque ne permet ni de reproduire un finding, ni de vérifier une correction, ni de rejouer une régression six mois plus tard. La structure de Tegbessou rend chaque pas explicite, donc rejouable.

**7. La sécurité offensive bouge vite — l'outil doit évoluer sans se réécrire.** Les techniques de recon d'août 2026 ne sont pas celles de janvier ; le fuzzing Web3, le JS mining, les patterns MCP changent tous les mois. Un pipeline **modulaire** laisse ajouter/retirer une technique par étape sans toucher au reste. Un agent monolithique de bout en bout est opaque à mettre à jour : on ne sait pas *où* injecter la nouveauté. L'évolutivité par module (voir §6) est un choix d'architecture, pas un détail.

> **En une phrase :** un simple agent optimise la démo ; cette architecture optimise la mission — performante grâce au LLM, sûre et défendable grâce à l'humain, et durable grâce à la modularité.

Le reste du document décline cette thèse en composants, données, sécurité, installation et feuille de route.

---

## 1. Vision et principes non négociables

Tegbessou est un **copilote expert**, pas un autopilote. Le système fait le travail lourd ; l'humain garde la stratégie, l'autorisation et la décision.

### Les six principes qui gouvernent chaque décision technique

1. **Human-in-the-loop obligatoire.** Aucune phase offensive ne démarre sans validation humaine explicite. Le système propose, l'humain dispose.
2. **Le scope est sacré.** Toute action est vérifiée contre une liste blanche d'autorisation avant exécution. Hors scope = refus + log + alerte. Non contournable, y compris par l'opérateur.
3. **Traçabilité totale.** Chaque appel d'outil, chaque décision LLM, chaque validation humaine est journalisée de façon inaltérable. Un pentest doit être rejouable et auditable.
4. **Spécialisation plutôt qu'omniscience.** Cinq agents spécialisés battent un LLM généraliste qui fait tout à la fois — en performance comme en fiabilité.
5. **Officiellement supporté plutôt que bricolé.** Outils standards, protocoles standards (MCP), dépendances maintenues. Pas de hack fragile.
6. **Modularité évolutive.** Chaque agent est un ensemble de modules qu'on peut **ajouter, retirer ou remplacer** au fil des apprentissages, sans réécrire l'orchestration. La méthodologie est un organisme vivant, versionné (voir §6).

### Fondations architecturales retenues

L'architecture repose sur des patterns éprouvés en production, choisis pour leur robustesse et leur maintenabilité :

- **La Gateway FastAPI comme point de passage unique** vers tout service externe.
- **Le chiffrement AES-256-GCM des credentials** au repos.
- **L'isolation par schéma PostgreSQL** (ici : un schéma par *engagement*).
- **n8n comme orchestrateur** qui n'appelle jamais un service externe directement.
- **La discipline de travail** : lire l'état réel avant de concevoir, autorisation explicite avant toute écriture, une brique prouvée et testée avant la suivante.

---

## 2. Ce que l'outil fait (et ne fait pas)

### Modes de fonctionnement

Quatre modes, choisis à la création d'un engagement. Le mode conditionne les gardes, les templates et les outils disponibles.

| Mode | Usage | Spécificités |
|---|---|---|
| `pentest` | Mission client formelle | SoW obligatoire, rapport PTES, scope strict |
| `bug_bounty` | Programmes HackerOne / Bugcrowd / Intigriti / YesWeHack / self-hosted | **Lien du programme uploadé et parsé** (scope, hors-scope, techniques interdites, rate limits, en-têtes d'identification, politique de divulgation), scope auto-rempli puis validé, techniques interdites bloquées, en-têtes hunter obligatoires, rate limits conservateurs, format « un finding = une soumission » (voir §2.1) |
| `ctf` | Entraînement / compétition | Scope = machine cible déclarée, exploration libre, pas de rapport formel |
| `audit_code` | Audit de code source Web2/Web3 | Pas de trafic vers une cible, analyse statique pure |

### Capacités

- **Reconnaissance** : OSINT, cartographie de surface, énumération de sous-domaines, découverte d'IP d'origine, fingerprinting, corrélation CVE, JS mining, cartographie des points d'entrée, dorking. (Détail : `docs/AGENTS.md`, agent RECON, 9 modules.)
- **Analyse statique (SAST)** : Web2 (Semgrep, Bandit, VulnHuntr) et Web3 (Slither, Mythril).
- **Analyse dynamique (DAST)** : scan orienté OWASP WSTG v4.2.
- **Test et validation** : confirmation contrôlée des vulnérabilités, avec preuve reproductible.
- **Inspection interactive** : DevTools intégrés au dashboard (proxy, repeater, inspecteur) — voir §9.
- **Scoring** : CVSS 4.0 proposé puis validé par l'humain, corrélation CVE (NVD) et MITRE ATT&CK.
- **Coordination** : suivi par phase, checklist WSTG, tableau de findings temps réel.
- **Reporting** : rapport structuré + scénario de ré-exploitation rejouable.
- **Apprentissage** : chaque action est expliquée ; base de connaissances consultable.

### Non-objectifs (limites assumées)

- **Pas d'exploitation destructive automatique** (double confirmation humaine obligatoire).
- **Pas d'autonomie totale** : aucun mode « lance et va dormir » sur une cible réelle.
- **Pas de contournement de scope** : impossible par conception, pas seulement par politique.
- **Pas un scanner de plus** : la valeur est dans l'orchestration, la corrélation et le raisonnement assisté.

### 2.1 Le mode bug bounty en détail

Le bug bounty ne fonctionne pas comme un pentest sous contrat : le cadre est fixé par le **programme**, pas par un SoW. Dépasser ce cadre (scope, techniques interdites, débit) fait perdre le bounty et bannir le compte. Tegbessou traite donc le programme comme la source d'autorité de la mission.

**Upload et parsing du programme.** À la création d'un engagement `bug_bounty`, l'opérateur fournit le **lien du programme** (page de règles HackerOne/Bugcrowd/Intigriti/YesWeHack ou programme auto-hébergé). Deux voies :
- L'outil **récupère la page** (via le fetcher passant par la Gateway) et la **parse par LLM** pour en extraire une structure : actifs in-scope, hors-scope, exclusions, **techniques interdites** (DoS, scan automatisé, ingénierie sociale, tests physiques, spam…), **rate limits imposés**, **en-tête(s) d'identification requis**, politique de divulgation, barème de sévérité/récompense, statut (VDP gratuit vs programme payant).
- Ou l'opérateur **colle le texte des règles** (utile si la page exige un login ou bloque le fetch).

Dans les deux cas, le lien et le texte des règles sont **scellés dans l'autorisation** (hash + horodatage), au même titre qu'un SoW. C'est la preuve du cadre accepté.

**Validation humaine du parsing.** Le scope et les contraintes extraits sont **proposés**, jamais appliqués aveuglément — un parsing peut se tromper. L'opérateur relit et valide avant que l'engagement ne devienne actif. Le scope validé alimente le Scope Enforcer ; les techniques interdites deviennent des **modules désactivés de force** pour cet engagement (impossible à réactiver).

**Comportements spécifiques au mode :**
- **En-têtes d'identification obligatoires** : beaucoup de programmes exigent un en-tête portant le handle du chercheur pour distinguer le trafic de test (`X-Bug-Bounty: <handle>`, `X-HackerOne: <username>`, etc.). Pré-rempli depuis les règles parsées, injecté sur **toute** requête sortante — y compris le Repeater des DevTools.
- **Rate limits conservateurs** : on applique le plus strict entre le réglage opérateur et la limite du programme. Fenêtre horaire respectée si imposée.
- **Hors-scope strict** : les entrées hors-scope du programme deviennent des exclusions dures dans le Scope Enforcer, pas de simples avertissements.
- **Techniques interdites** : les modules correspondants (ex. un module de fuzzing agressif, un module de scan de masse) sont bloqués pour l'engagement. Le mode `bug_bounty` désactive par défaut les modules à fort volume/bruit.
- **Conscience du doublon et de l'impact** : l'agent ANALYSE évalue la nouveauté et l'impact réel d'un finding (le bug bounty récompense l'unique et l'impactant, pas le doublon connu), et priorise en conséquence.
- **Format de soumission** : REPORT produit une variante « **un finding = une soumission** » alignée sur le format du programme (titre, classe, impact, PoC reproductible, étapes), prête à copier dans la plateforme. Le barème de sévérité du programme est appliqué s'il est connu.

> **Garde spécifique.** Le module de pivot OSINT sur personnes (RECON M9, voir `docs/AGENTS.md`) reste **désactivé** en bug bounty sauf si les règles du programme l'autorisent explicitement — la plupart l'interdisent.

---

## 3. Architecture globale

Quatre plans strictement séparés : présentation (dashboard/CLI), contrôle (BFF), orchestration (n8n + Gateway), exécution (nœuds outils). Cette séparation permet de scaler l'exécution sans toucher au reste, et de confiner les composants dangereux.

```
┌───────────────────────────── PLAN PRÉSENTATION ─────────────────────────────┐
│                                                                              │
│   Dashboard React (SPA)                    CLI (Python / Typer)              │
│   - pilotage complet                       - mêmes capacités                 │
│   - DevTools intégrés (proxy/repeater)     - scriptable / CI                 │
│   - temps réel (WebSocket)                                                   │
│                                                                              │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                     │  HTTPS + JWT
┌────────────────────────────── PLAN CONTRÔLE ─────────────────────────────────┐
│   api_pentest — BFF FastAPI (Poste opérateur)                                │
│   - Auth (JWT + MFA TOTP)      - RBAC (admin/lead/analyst/viewer)            │
│   - Validation des entrées     - Agrégation pour l'UI                        │
│   - WebSocket hub (push temps réel)   - Passerelle DevTools ↔ proxy          │
└───────────────────────────────────┬──────────────────────────────────────────┘
                                     │  mTLS (réseau privé)
┌──────────────────────────── PLAN ORCHESTRATION ──────────────────────────────┐
│   Orchestrateur n8n (Serv. orchestr.)     API Gateway FastAPI (Serv. orch.)   │
│   ┌──────────────────────────┐            ┌──────────────────────────────┐   │
│   │ Flows par phase +        │            │ Scope Enforcer (bloquant)    │   │
│   │ sous-flows par module    │──HTTP────▶ │ Rate Limiter                 │   │
│   │ (checkpoints humains)    │            │ Credential Vault (AES-GCM)   │   │
│   └──────────────────────────┘            │ LLM Router (multi-provider)  │   │
│                                            │ MCP Router (par phase)       │   │
│   PostgreSQL (schéma/engagement+pgvector)  │ Audit Logger (append-only)   │   │
│   Redis (jobs + cache + pub/sub)           │ Job Dispatcher (Redis queue) │   │
│                                            │ Proxy scellé (DevTools)      │   │
│                                            └───────────────┬──────────────┘   │
└────────────────────────────────────────────────────────────┼──────────────────┘
                                                              │  jobs
┌───────────────────────────── PLAN EXÉCUTION ─────────────────────────────────┐
│   Execution Worker(s) — conteneurs sandboxés (isolés, egress contrôlé)       │
│   Web2 : nmap · httpx · subfinder · katana · gau · nuclei · ffuf · sqlmap    │
│          · semgrep · arjun · linkfinder · dalfox · whatweb · gowitness       │
│   Web3 : slither · mythril · foundry · echidna · medusa · halmos             │
│   SAST : bandit · semgrep · VulnHuntr · trufflehog                           │
│   Proxy d'interception (mitmproxy) pour les DevTools                         │
│   Scalable horizontalement : +1 worker = +capacité                          │
└──────────────────────────────────────────────────────────────────────────────┘
```

### Pourquoi cette séparation

- **Le plan exécution est le seul qui touche la cible** → isolé, privilèges minimaux, egress contrôlé. Blast radius confiné.
- **Le plan orchestration ne fait jamais d'appel externe direct** (principe architectural) → tout passe par la Gateway, qui applique scope/rate/log *avant* que quoi que ce soit ne parte.
- **Le plan contrôle est le seul exposé aux humains** et ne connaît pas les outils → surface d'attaque réduite.
- **Le plan présentation est interchangeable** : dashboard et CLI consomment la même API. Parité par construction.

### Flux d'un engagement type

```
1. Création engagement + upload autorisation (SoW) ──▶ BFF ──▶ Gateway ──▶ DB
   (aucune action offensive tant que l'autorisation n'est pas validée)
2. Scope + rate + headers + LLM ──▶ persistés (chiffrés si secrets)
3. Lancement Phase RECON ──▶ n8n (flow phase → sous-flows modules) ──▶ Gateway
   ├─ Scope Enforcer valide chaque cible
   ├─ Job Dispatcher → file Redis → Execution Worker (sandbox)
   ├─ Résultats normalisés ──▶ DB + pub/sub ──▶ WebSocket ──▶ Dashboard (temps réel)
   └─ Agent RECON (LLM) synthétise ──▶ hypothèses priorisées
4. CHECKPOINT HUMAIN ──▶ relecture, ajustement scope, validation phase suivante
5. ... SCAN, EXPLOIT, ANALYSE ... (idem, avec checkpoints)
6. Phase REPORT ──▶ rapport + scénarios rejouables
```

Le **checkpoint humain** entre chaque phase est le cœur du modèle. Il n'est pas optionnel.

---

## 4. Topologie de déploiement

Le déploiement se répartit sur **trois rôles machine**, qui peuvent être trois hôtes distincts ou des VM sur un même hyperviseur. On ne colocalise jamais l'exécution des outils avec l'orchestration : l'exécution est gourmande et doit rester isolée.

| Rôle machine | Composants | Justification |
|---|---|---|
| **Poste opérateur** | Dashboard + `api_pentest` (BFF) + Nginx (reverse proxy/TLS) | Interface humaine, peu gourmande, exposée aux opérateurs |
| **Serveur d'orchestration** | n8n + API Gateway + PostgreSQL + Redis | Orchestration et état. À dimensionner en RAM selon la charge |
| **Nœud d'exécution** | Execution Worker(s) + proxy d'interception | Isolation, egress contrôlé, scalable, idéalement jetable après mission |

> **Dimensionnement.** Le serveur d'orchestration porte l'état (DB, file, cache) : prévoir la RAM en conséquence, ou imposer des `mem_limit` explicites par conteneur si l'hôte est partagé. Le nœud d'exécution peut être une VM légère (2 vCPU / 8 Go suffisent par worker) et se multiplie pour scaler. **Aucun build sur les hôtes de production** : les images sont construites en CI et seulement tirées (`pull`) via le registre (`ghcr.io`).

### Réseau

- **Présentation ↔ Contrôle** : HTTPS + JWT. Le dashboard n'atteint jamais la Gateway directement.
- **Contrôle ↔ Orchestration** : réseau privé, **mTLS** (CA interne, voir §13).
- **Exécution** : réseau **isolé**, egress restreint aux cibles autorisées (double barrière : Gateway + pare-feu du nœud).
- **Domaine & TLS** : un domaine dédié, DNS géré, Nginx reverse proxy + TLS devant le BFF. Gateway et n8n **non** exposés publiquement.

---

## 5. Les composants en détail

### 5.1 `api_pentest` — le BFF

La seule porte d'entrée des humains. N'exécute aucun outil, ne parle à aucune cible.

- **Authentification** : login → JWT (access court + refresh rotatif révocable), MFA TOTP obligatoire.
- **Autorisation (RBAC)** : quatre rôles (§13.3). Chaque endpoint déclare le rôle minimal.
- **Validation** : schémas Pydantic stricts. Aucune donnée brute ne transite vers la Gateway.
- **Agrégation** : compose les vues du dashboard.
- **Hub WebSocket** : s'abonne au pub/sub Redis, pousse les événements aux dashboards.
- **Passerelle DevTools** : relaie le flux du proxy d'interception vers l'onglet DevTools du dashboard (voir §9).

Stack : FastAPI, Pydantic v2, SQLAlchemy 2.x async, `python-jose`, `pyotp`, `websockets`.

### 5.2 API Gateway — le point de passage unique

Le composant le plus critique en sécurité. Applique les règles *avant* toute action.

- **Scope Enforcer** — middleware bloquant : chaque requête d'outil porte une `target`, comparée à la liste blanche. Hors scope → `403` + log + alerte. Non désactivable côté opérateur.
- **Rate Limiter** — token bucket par engagement (Redis).
- **Credential Vault** — chiffre/déchiffre les secrets AES-256-GCM. Clé maître en variable d'environnement, jamais en base ni en git.
- **LLM Router** — abstraction multi-fournisseurs (§7) : sélection, budget, fallback.
- **MCP Router** — expose *uniquement* les outils de la phase courante (anti-flood de contexte).
- **Phase Runner** — exécute une phase en itérant sur les **modules activés** de cette phase (lus dans `module_registry`), dans l'ordre. C'est **ici** que vit l'orchestration des modules — pas dans n8n. Ajouter un module = une entrée au registre, pas un nouveau workflow.
- **Job Dispatcher** — pousse les tâches en file Redis, suit leur cycle de vie.
- **Audit Logger** — journal append-only chaîné par hash (§13.4).
- **Proxy scellé** — point d'entrée du trafic DevTools, soumis au Scope Enforcer et au logging comme tout le reste.

Stack : FastAPI, `cryptography`, `redis-py`, `httpx`, SQLAlchemy async.

### 5.3 Orchestrateur n8n

Matérialise la méthodologie (PTES / WSTG) en flows explicites. n8n n'appelle **que** la Gateway (pattern HTTP Request), jamais un outil ni un service externe.

Choisi parce que c'est un orchestrateur éprouvé, que les flows sont lisibles et modifiables sans redéploiement, et que les checkpoints humains y sont natifs (nœud « Wait for approval »).

**n8n reste au niveau des phases, pas des modules.** Un flow de phase se résume à : déclencheur → appel Gateway `POST /engagements/{id}/phases/{phase}/run` → attente de fin (callback) → présentation de la synthèse → **checkpoint humain (Wait)** → sur validation, clôture de la phase. Le Phase Runner de la Gateway (§5.2) se charge d'itérer sur les modules ; n8n ne connaît pas les modules individuellement. Un flow de phase fait donc ~12-18 nœuds, pas 40.

Conséquence sur la volumétrie : **~6 workflows** au total — 5 flows de phase (RECON, SCAN, EXPLOIT, ANALYSE, REPORT) + 1 workflow d'erreur global n8n (kill/notification). Un flow de monitoring planifié (re-recon périodique pour un programme bug bounty actif) est optionnel (+1). C'est tout. Flows versionnés en git (`orchestrator/flows/*.json`).

> **Pourquoi pas un sous-flow par module.** Mettre chaque module dans un sous-flow n8n dupliquait le concept de module (une fois en config, une fois en workflow) et gonflait la volumétrie à ~40 flows sans bénéfice pour une équipe qui code. La modularité vit dans le **registre de modules** côté Gateway (§6, §11), lu par le Phase Runner. n8n orchestre les phases ; la Gateway orchestre les modules.

### 5.4 Execution Worker

Le seul composant qui touche la cible. Conteneur avec toolset et privilèges minimaux (`cap_drop: ALL`, non-root, `read_only` sauf `/tmp`). Consomme la file Redis, exécute, **normalise** la sortie (parsing structuré, jamais de dump brut), renvoie via la Gateway. **Jamais** de shell avec interpolation utilisateur (§13.5). Scalable : N workers sur la même file.

Stack : Python (wrappers), conteneurs par famille d'outils, worker de file (RQ ou Celery + Redis).

---

## 6. Le modèle multi-agent et son évolutivité

Cinq agents, un par phase. Chaque agent = **un ensemble de modules (exécutés par le Phase Runner de la Gateway) + prompt système spécialisé + jeu d'outils MCP borné à sa phase + contexte RAG ciblé**. Le séquencement des phases et les checkpoints humains sont portés par n8n (un flow par phase, §5.3). La spécification détaillée (modules, techniques, outils, rôle du LLM, garde-fous) est dans **`docs/AGENTS.md`** — ici on donne la vue d'ensemble et le **mécanisme d'évolution**.

| Agent | Phase | Entrée | Sortie | Checkpoint sortant |
|---|---|---|---|---|
| **RECON** | Intelligence Gathering / WSTG-INFO | scope validé | surface d'attaque + hypothèses | validation des cibles/pistes |
| **SCAN** | Vulnerability Analysis | actifs | vulns candidates + preuves | tri des candidates |
| **EXPLOIT** | Exploitation | candidates | vulns confirmées + PoC | **validation explicite** |
| **ANALYSE** | (transverse) | vulns confirmées | findings scorés/dédupliqués | validation des scores |
| **REPORT** | Reporting | findings | rapport + scénarios rejouables | relecture avant livraison |

### 6.1 Anatomie d'un agent : un registre de modules

Un agent n'est pas un bloc figé. C'est un **registre de modules** ordonnés. Exemple RECON : 9 modules (OSINT, sous-domaines, infra/IP d'origine, hôtes vivants, techno+versions, corrélation CVE, JS mining, points d'entrée, dorking/OSINT ciblé). SCAN : 5, EXPLOIT : 3, ANALYSE : 4, REPORT : 3.

Chaque module est décrit de façon déclarative (fichier de config versionné) :

```yaml
# orchestrator/modules/recon/m07_js_mining.yaml
id: recon.m07_js_mining
agent: recon
order: 70
title: "Crawling & analyse du code source des pages (JS mining)"
enabled_by_default: true
tools: [gau, waybackurls, katana, linkfinder, secretfinder, trufflehog]
llm_step: true            # ce module sollicite le LLM pour hiérarchiser
produces: [asset.endpoint, asset.param, finding.candidate.secret]
guards: [scope, rate_limit]
requires_mode: [pentest, bug_bounty, ctf]   # exclu en audit_code
version: "2026.08"
```

### 6.2 Ajout, retrait, remplacement à chaque étape

C'est le principe **modularité évolutive** (principe n°6). Concrètement :

- **Ajouter un module** : déposer un fichier de config + son wrapper d'outil éventuel, et une entrée au `module_registry`. Le Phase Runner le prend en compte par son `order` — **aucun nouveau workflow n8n, aucune réécriture de l'agent**. Exemple : demain, une nouvelle technique de découverte d'IP d'origine apparaît → nouveau module `recon.m03b_...`, activé après validation.
- **Retirer / désactiver** : `enabled_by_default: false`, ou désactivation par engagement depuis le dashboard. Un module qui produit trop de bruit ou devient obsolète sort sans casser la chaîne.
- **Remplacer** : une technique dépassée cède la place à une meilleure ; on garde l'ancienne en `deprecated` le temps de valider la nouvelle (une brique prouvée avant la suivante).
- **Versionner** : chaque module porte une `version` (ex. `2026.08`). La méthodologie globale est taguée. Un rapport indique quelle version de méthodologie l'a produit — reproductibilité et audit.

> **Pourquoi c'est structurant.** La sécurité offensive change tous les mois (recon, JS mining, fuzzing Web3, patterns MCP). Un pipeline modulaire absorbe ces changements par ajout/retrait ciblé. Un agent monolithique, lui, faut le réécrire — et on ne sait jamais où injecter la nouveauté sans tout casser. La réflexion de l'équipe, les nouvelles approches découvertes en mission, se traduisent en **modules**, pas en refontes.

### 6.3 Gouvernance des modules

- Tout nouveau module passe par une PR (tests + revue, §17) et une entrée au **registre** (`module_registry`, §11).
- Un module qui touche à l'exécution active hérite **automatiquement** des gardes (`scope`, `rate_limit`) — impossible d'ajouter un module qui contourne le Scope Enforcer.
- `docs/AGENTS.md` documente l'ensemble courant ; il **grandira et rétrécira**. C'est attendu, pas une dérive.

### 6.4 Pourquoi c'est plus performant qu'un agent unique

1. Contexte borné par agent → moins de tokens, moins d'hallucination.
2. RAG métier → hypothèses orientées par des writeups réels *avant* le scan.
3. Checkpoints humains → correction de trajectoire tôt.
4. Preuves obligatoires → pas de finding fantôme.
5. Orchestration hors du contexte de chat → coût borné, comportement prévisible.
6. Modularité → l'outil reste à l'état de l'art sans réécriture.

---

## 7. Couche LLM multi-fournisseurs

Choisir le LLM et fournir sa clé depuis le dashboard. Abstraction unique : ajouter un fournisseur ne touche qu'une classe.

| Fournisseur | Modèles cibles | Usage recommandé |
|---|---|---|
| Anthropic | Claude (Sonnet quotidien, Opus revues critiques) | Raisonnement, synthèse, code |
| OpenAI | GPT-4o / o-series | Alternative généraliste |
| Google | Gemini 2.5 Pro/Flash | Volume, coût réduit |
| Local | Ollama (Llama, Qwen, DeepSeek…) | Missions sensibles / air-gapped, données non exfiltrées |

> Le support **local (Ollama)** est stratégique : pour un audit sensible, garder les données chez soi est un argument commercial et de conformité.

Interface commune :

```python
# gateway/app/llm/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class LLMResponse:
    text: str
    input_tokens: int
    output_tokens: int
    cost_usd: float
    model: str

class LLMProvider(ABC):
    @abstractmethod
    async def complete(self, system: str, messages: list[dict],
                       temperature: float, max_tokens: int) -> LLMResponse: ...
    @abstractmethod
    def estimate_cost(self, in_tok: int, out_tok: int) -> float: ...
```

Le **LLM Router** choisit l'implémentation selon la config de l'engagement, applique le **budget cap** (arrêt au dépassement) et le **fallback** (bascule sur le secondaire configuré).

**Gestion des clés** : saisies au dashboard, chiffrées AES-256-GCM avant persistance, jamais renvoyées en clair (affichage `sk-...abcd`). Résolution par précédence user → engagement → global. Rotation sans impact sur les logs (on garde le fingerprint).

**Consommation** : chaque appel journalisé (tokens, coût). Le dashboard affiche par engagement/agent/jour. Le budget cap protège de la facture surprise.

---

## 8. Base de connaissances (RAG)

PostgreSQL + **pgvector** (pas de service vectoriel externe — une dépendance et une surface d'attaque de moins).

| Source | Contenu | Rafraîchissement |
|---|---|---|
| OWASP WSTG v4.2 | 109 tests, procédures | à chaque version |
| OWASP Top 10 (2021+2025) | classes de vulns, CWE | à chaque version |
| CVE / NVD | descriptions, CVSS, produits | hebdomadaire (API) |
| CISA KEV | CVE activement exploitées | hebdomadaire |
| MITRE ATT&CK | tactiques, techniques | à chaque version |
| Writeups bug bounty publics | chemins d'exploitation réels | manuel / périodique |
| Checklists Web3 | Cyfrin, patterns SWC | à chaque version |

> **Éthique/légal** : sources publiques et licites uniquement. Aucun contenu volé, aucun dump de données.

Pipeline `knowledge_base/ingest/` : scripts idempotents *fetch → normalise → chunk → embed → upsert*, un par source. Embeddings via le provider configuré ou un modèle local (air-gap possible).

Usage : avant qu'un agent ne raisonne, le Router injecte les *k* chunks pertinents. RECON connaît les patterns d'attaque de la stack détectée ; ANALYSE propose des chemins vus dans des writeups similaires.

---

## 9. Le dashboard — pilotage complet et DevTools intégrés

Tout se pilote depuis un seul endroit : paramètres, LLM et clés, progression, données collectées, inspection interactive, compréhension de ce qui a été fait.

### 9.1 Écran « Engagements » (accueil)

Liste avec, par engagement : nom, mode, cible principale, phase courante, findings par sévérité, statut, progression. Bouton « Nouvel engagement ».

### 9.2 Assistant de création d'engagement

Étapes bloquantes, dans l'ordre :

1. **Identité** — nom, client, mode.
2. **Autorisation** — en `pentest`/`audit_code` : upload du SoW. En `bug_bounty` : **lien du programme** (l'outil le récupère et le parse) ou collage du texte des règles ; le lien/texte est scellé dans l'audit (hash + horodatage). **Sans autorisation validée, aucune action offensive.**
3. **Scope** — liste blanche (domaines, IP, CIDR, contrats on-chain ; in-scope/out-of-scope/exclusions). En bug bounty, **pré-rempli depuis les règles parsées** ; l'opérateur relit et valide (le parsing peut se tromper).
4. **Contraintes du programme** (bug bounty) — techniques interdites, rate limits imposés, fenêtre horaire, barème de sévérité, extraits des règles parsées ; validation humaine avant activation.
5. **Trafic** — req/s, concurrence, délai (bornés par les limites du programme en bug bounty).
6. **En-têtes** — User-Agent + en-tête(s) d'identification hunter (pré-remplis depuis les règles), clé/valeur libre.
7. **LLM** — fournisseur, modèle, clé chiffrée, température, budget, fallback.
8. **Outils & modules** — activer/désactiver par module (§6). En bug bounty, les techniques interdites sont **verrouillées désactivées**.

### 9.3 Écran « Cockpit » (vue engagement)

Panneaux :
- **Progression par phase** : RECON → SCAN → EXPLOIT → ANALYSE → REPORT, état de chaque phase, bouton de checkpoint « Valider et passer à la suite ».
- **File des tâches en direct** : chaque tâche outil (statut, durée, lien vers sortie normalisée), temps réel.
- **Panneau « Ce qui a été fait »** : timeline en langage naturel — l'agent explique chaque action (volet apprentissage).
- **Données collectées** : onglets Sous-domaines / Ports & services / Technologies / Endpoints / Paramètres / Points d'entrée. Triables, filtrables, exportables.
- **Tableau des findings** : temps réel, sévérité / CVSS / classe / statut / preuve.
- **Consommation LLM** : tokens et coût cumulés, jauge vs budget.

### 9.4 Carte de reconnaissance (graphe de surface d'attaque)

Une vue graphe inspirée de BloodHound — qui cartographie l'Active Directory en nœuds et arêtes menant au Domain Admin — mais **orientée web**. Elle transforme le dump de reconnaissance en **carte de risque explorable** : d'un coup d'œil, l'opérateur voit les technologies, les vulnérabilités possibles, et les zones les plus critiques à explorer.

**Modèle du graphe.** Nœuds et arêtes sont dérivés des données déjà collectées (`assets`, `findings`, `asset_edges`) :
- **Nœuds** : domaine, sous-domaine, hôte/IP (origine vs CDN), service/port, technologie (+version), endpoint, paramètre, point d'entrée (formulaire/upload/recherche/API/GraphQL), CVE, secret, finding.
- **Arêtes** (relations) : `résout_vers`, `héberge`, `exécute`, `expose`, `contient`, `affecté_par` (techno→CVE), `révèle` (JS→endpoint interne), `mène_potentiellement_à` (chaîne d'exploitation candidate).

**Code couleur et zones (le cœur visuel).**
- **Couleur du nœud par criticité** : gris (inconnu/info), vert (faible intérêt), jaune/orange (à explorer), rouge (critique — vuln confirmée, panneau d'admin exposé, upload non contrôlé, CVE dans la liste CISA KEV).
- **Taille du nœud par importance** : centralité, nombre de findings rattachés.
- **Zones de chaleur** : des halos de fond colorent des régions entières du graphe par risque agrégé — un sous-graphe autour d'un panneau d'admin exposé sur un framework obsolète « rougeoie », signalant où concentrer l'effort.
- **Style d'arête** : trait plein = relation confirmée ; pointillé = chemin hypothétique/candidat.

**De l'analyse, pas juste du dessin (ce qui le rend BloodHound-like).** La criticité et la structure sont calculées, pas décoratives :
- **Marquer un nœud « objectif »** (actif à forte valeur) → le graphe met en évidence les chemins les plus courts et les plus exploitables qui y mènent.
- **Points de convergence (choke points)** : l'analyse de centralité surligne les actifs par lesquels passent le plus de chemins — meilleur rapport effort/impact, à tester (ou corriger) en priorité.
- **Requêtes prédéfinies** : « tous les points d'upload », « technos avec CVE exploitée (KEV) », « endpoints non authentifiés révélés par le JS », « chemins vers l'objectif ».
- **Filtres** : par technologie, sévérité, phase, in-scope uniquement, points d'entrée uniquement.

**Temps réel et ponts.** Le graphe est vivant : à mesure que la reconnaissance progresse (streaming WebSocket), les nœuds apparaissent. Depuis un nœud : envoyer vers EXPLOIT (promotion en test), ouvrir dans le Repeater (§9.5), voir la preuve, ou exclure du scope. C'est le prolongement visuel du « mieux orienter le pentest ».

**Réalisation technique.** Rendu par **Cytoscape.js** — le choix 2026 quand le graphe exige de l'**analyse** (plus courts chemins, centralité, détection de communautés pour les zones) et pas seulement du rendu, avec une intégration React mature et un moteur de styles expressif. Les algorithmes tournent côté client via Cytoscape ; pour un périmètre très large (>50 000 nœuds, rare sur une cible web), bascule vers **Sigma.js** (rendu WebGL) avec pré-calcul du layout côté serveur. Le graphe est **exportable** (image + interactif) pour le rapport client.

**Backend.** Le BFF expose `GET /engagements/{id}/graph` (nœuds + arêtes + scores de criticité calculés par l'agent ANALYSE). Les relations sont persistées dans `asset_edges` (§11).

### 9.5 DevTools intégrés

Un environnement d'inspection interactive équivalent aux outils de développement du navigateur (onglet réseau, console, stockage, inspecteur), **plus** un éditeur/rejoueur de requêtes de type Repeater — le tout adossé au **proxy scellé** de la Gateway, donc soumis au scope, au rate limit et au logging.

Onglets :

- **Réseau** : chaque requête/réponse qui transite par le proxy (comme l'onglet Network d'un navigateur) — méthode, URL, en-têtes, corps, statut, timing, taille. Filtrable par hôte/type/statut. C'est la vue de vérité de ce qui part réellement vers la cible.
- **Repeater** : sélectionner une requête, la **modifier** (méthode, en-têtes — dont le pseudo bug bounty, paramètres, corps) et la **rejouer**. Contrôle fin manuel, indispensable pour valider une hypothèse à la main. Respecte scope + rate ; chaque envoi est loggé.
- **Console** : exécuter du JS dans le contexte d'une page chargée par le navigateur piloté (test DOM/XSS contrôlé).
- **Stockage** : cookies, `localStorage`, `sessionStorage`, tokens (décodage JWT à la volée). Repérer un flag de session manquant, un token mal scoppé.
- **Inspecteur DOM** : arbre du DOM, avec les sources/sinks DOM-XSS repérés par le module JS mining surlignés.

**Ponts avec les agents** : une requête capturée peut être **promue en test** (envoyée à l'agent EXPLOIT comme candidate) ; un endpoint observé devient un `asset` ; une anomalie repérée à la main crée un finding `candidate`. L'inspection manuelle et l'automatisation partagent la même base.

> **Réalisation.** Proxy basé sur **mitmproxy** côté nœud d'exécution ; le flux remonte au dashboard via la passerelle DevTools du BFF (WebSocket). Un navigateur piloté (Playwright) fournit console/DOM. Rien ne court-circuite le Scope Enforcer : le proxy est *dans* le chemin gardé.

### 9.6 Contrôles temps réel (toujours accessibles)

Réglage du débit à chaud (req/s, concurrence) ; pause/reprise globale ; **kill switch** (arrêt d'urgence de toutes les tâches) ; édition du scope à chaud (loggée).

### 9.7 Écran « Finding »

Détail : description, classe, CVSS (vecteur éditable), preuves (échanges HTTP, extraits de code, captures), remédiation, statut, historique. Bouton « Générer le scénario rejouable » (YAML).

### 9.8 Écran « Rapport »

Prévisualisation, édition des sections, sélection des findings, export PDF/Markdown, relecture/signature avant « livré ».

### 9.9 Écran « Base de connaissances »

Recherche dans le RAG (WSTG, CVE, techniques). Apprendre et comprendre sans quitter l'outil.

### 9.10 Écran « Administration » (rôle admin)

Utilisateurs et rôles, clés LLM globales, **registre des modules** (activer/versionner — §6), état des workers, journaux d'audit (lecture seule), config système, rotation des secrets.

**Stack front** : React, TanStack Query, WebSocket natif, Recharts, design system maison. Design-to-code via Figma.

---

## 10. La CLI

Parité fonctionnelle avec le dashboard (même API BFF). Stack : Python + **Typer**, sortie `rich`, config `~/.pentaforge/config.toml` → `~/.tegbessou/config.toml`.

```
tegbessou auth login                       # login + MFA
tegbessou engagement create                # assistant (mêmes étapes que le dashboard)
tegbessou engagement scope add <id> <target>
tegbessou engagement authorize <id> --file sow.pdf
tegbessou llm set <id> --provider anthropic --model <m>   # clé en prompt masqué
tegbessou rate set <id> --rps 5 --concurrency 3 --delay 200ms
tegbessou header set <id> --key "X-Bug-Bounty" --value "<handle>"
tegbessou module toggle <id> recon.m09_dorking --off       # active/désactive un module
tegbessou run recon <id>                   # lance une phase
tegbessou run exploit <id> --confirm       # exige --confirm (garde)
tegbessou phase approve <id> --phase recon # checkpoint humain
tegbessou tasks watch <id>                 # suit la file en temps réel
tegbessou proxy tail <id>                  # flux réseau du proxy en CLI (équiv. onglet Réseau)
tegbessou replay send <id> --from <req_id> # rejoue/édite une requête (équiv. Repeater)
tegbessou findings list <id> [--severity high]
tegbessou report generate <id> --format pdf
tegbessou scenario export <id> <finding_id> --out replay.yaml
tegbessou kill <id>                        # kill switch
tegbessou kb search "IDOR"
```

Mêmes gardes qu'au dashboard (même API) : pas d'`exploit` sans autorisation validée ni `--confirm` ; scope vérifié côté Gateway. Bandeau de consentement légal au premier usage, journalisé.

---

## 11. Modèle de données

PostgreSQL. Socle partagé dans `public` ; **un schéma par engagement** (`eng_<uuid>`) pour les données sensibles (findings, artefacts, tâches, requêtes proxy), avec suppression propre en fin de mission.

### Schéma `public` (partagé)

```sql
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,           -- argon2id
    totp_secret BYTEA NOT NULL,            -- chiffré AES-GCM
    role TEXT NOT NULL CHECK (role IN ('admin','lead','analyst','viewer')),
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE engagements (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    mode TEXT NOT NULL CHECK (mode IN ('pentest','bug_bounty','ctf','audit_code')),
    client TEXT,
    schema_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'draft' CHECK (status IN ('draft','active','paused','closed')),
    current_phase TEXT,
    methodology_version TEXT,              -- version du registre de modules utilisée
    owner_id UUID NOT NULL REFERENCES users(id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    closed_at TIMESTAMPTZ
);

CREATE TABLE authorizations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    source_kind TEXT NOT NULL CHECK (source_kind IN ('sow','program_url','program_text')),
    document_name TEXT,                    -- pour un SoW uploadé
    program_url TEXT,                      -- lien du programme bug bounty
    rules_text_ref TEXT,                   -- texte des règles (récupéré ou collé), stockage chiffré
    parsed_rules JSONB,                    -- scope/OOS/techniques interdites/rate/en-têtes/sévérité extraits
    content_hash TEXT NOT NULL,            -- SHA-256 du SoW ou du texte des règles scellé
    storage_ref TEXT,
    validated_by UUID REFERENCES users(id),
    validated_at TIMESTAMPTZ,
    UNIQUE (engagement_id)
);

-- Techniques interdites par le programme (verrouillage de modules pour l'engagement)
CREATE TABLE forbidden_techniques (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    label TEXT NOT NULL,                   -- ex: "automated_scanning", "dos", "social_engineering"
    blocks_module TEXT REFERENCES module_registry(id),  -- module verrouillé désactivé, si mappable
    source TEXT NOT NULL DEFAULT 'program' -- program|manual
);

CREATE TABLE scope_entries (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('domain','ip','cidr','contract')),
    value TEXT NOT NULL,
    disposition TEXT NOT NULL CHECK (disposition IN ('in_scope','out_of_scope','exclusion')),
    chain TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE traffic_configs (
    engagement_id UUID PRIMARY KEY REFERENCES engagements(id) ON DELETE CASCADE,
    max_rps NUMERIC NOT NULL DEFAULT 5,
    max_concurrency INT NOT NULL DEFAULT 3,
    delay_ms INT NOT NULL DEFAULT 0,
    allowed_window TSRANGE
);

CREATE TABLE custom_headers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    header_key TEXT NOT NULL,
    header_value TEXT NOT NULL
);

CREATE TABLE llm_configs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    scope_level TEXT NOT NULL CHECK (scope_level IN ('global','engagement','user')),
    engagement_id UUID REFERENCES engagements(id) ON DELETE CASCADE,
    user_id UUID REFERENCES users(id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    api_key_enc BYTEA,                     -- AES-256-GCM ; NULL pour ollama
    key_fingerprint TEXT,
    temperature NUMERIC NOT NULL DEFAULT 0.2,
    budget_cap_usd NUMERIC,
    fallback_provider TEXT
);

-- Registre des modules d'agents (support de la modularité évolutive, §6)
CREATE TABLE module_registry (
    id TEXT PRIMARY KEY,                   -- ex: recon.m07_js_mining
    agent TEXT NOT NULL,                   -- recon|scan|exploit|analyse|report
    title TEXT NOT NULL,
    ordering INT NOT NULL,
    version TEXT NOT NULL,                 -- ex: 2026.08
    status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','deprecated','disabled')),
    enabled_by_default BOOLEAN NOT NULL DEFAULT true,
    config_json JSONB NOT NULL,            -- tools, guards, requires_mode, produces...
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Surcharge par engagement (activer/désactiver un module pour une mission)
CREATE TABLE engagement_modules (
    engagement_id UUID NOT NULL REFERENCES engagements(id) ON DELETE CASCADE,
    module_id TEXT NOT NULL REFERENCES module_registry(id),
    enabled BOOLEAN NOT NULL,
    PRIMARY KEY (engagement_id, module_id)
);

CREATE TABLE audit_log (
    id BIGSERIAL PRIMARY KEY,
    ts TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor_id UUID REFERENCES users(id),
    engagement_id UUID,
    action TEXT NOT NULL,                  -- tool.exec, phase.approve, scope.violation, proxy.replay...
    target TEXT,
    params_json JSONB,
    prev_hash TEXT NOT NULL,
    entry_hash TEXT NOT NULL               -- SHA-256(prev_hash || contenu)
);

CREATE TABLE llm_usage (
    id BIGSERIAL PRIMARY KEY,
    engagement_id UUID NOT NULL,
    agent TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    input_tokens INT NOT NULL,
    output_tokens INT NOT NULL,
    cost_usd NUMERIC NOT NULL,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

### Schéma par engagement `eng_<uuid>`

```sql
CREATE TABLE assets (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    kind TEXT NOT NULL,                    -- subdomain|host|port|endpoint|param|contract
    value TEXT NOT NULL,
    metadata JSONB,                        -- tech, version, confiance, source
    in_scope BOOLEAN NOT NULL,
    criticality NUMERIC NOT NULL DEFAULT 0, -- score 0-100 (couleur du graphe), calculé par ANALYSE
    discovered_by TEXT,                    -- module/outil source
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Relations entre actifs (arêtes de la carte de reconnaissance, §9.4)
CREATE TABLE asset_edges (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    src_asset UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    dst_asset UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    relation TEXT NOT NULL,                -- resolves_to|hosts|runs|exposes|contains|affected_by|reveals|leads_to
    confirmed BOOLEAN NOT NULL DEFAULT true, -- false = chemin hypothétique/candidat (arête pointillée)
    metadata JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE tasks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    phase TEXT NOT NULL,
    module_id TEXT,                        -- module d'origine
    tool TEXT NOT NULL,
    target TEXT NOT NULL,
    args_json JSONB NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued'
        CHECK (status IN ('queued','running','done','failed','killed')),
    output_ref TEXT,
    started_at TIMESTAMPTZ,
    finished_at TIMESTAMPTZ
);

CREATE TABLE findings (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    title TEXT NOT NULL,
    vuln_class TEXT,                       -- WSTG/CWE/SWC
    cve TEXT,
    attack_id TEXT,                        -- MITRE ATT&CK
    cvss_vector TEXT,                      -- CVSS 4.0
    cvss_score NUMERIC,
    severity TEXT CHECK (severity IN ('info','low','medium','high','critical')),
    status TEXT NOT NULL DEFAULT 'candidate'
        CHECK (status IN ('candidate','confirmed','rejected','reported')),
    description TEXT,
    remediation TEXT,
    created_by TEXT,                       -- agent/module ou utilisateur
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE evidences (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    kind TEXT NOT NULL,                    -- http_exchange|code_snippet|screenshot|trace|foundry_poc
    content_ref TEXT NOT NULL,             -- stockage chiffré
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Requêtes capturées/rejouées par les DevTools (proxy)
CREATE TABLE proxy_requests (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    origin TEXT NOT NULL CHECK (origin IN ('captured','replayed')),
    method TEXT NOT NULL,
    url TEXT NOT NULL,
    req_headers JSONB,
    req_body_ref TEXT,
    resp_status INT,
    resp_headers JSONB,
    resp_body_ref TEXT,
    replayed_from UUID REFERENCES proxy_requests(id),
    actor_id UUID,
    ts TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE replay_scenarios (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    finding_id UUID NOT NULL REFERENCES findings(id) ON DELETE CASCADE,
    yaml_ref TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Le RAG (embeddings) vit dans un schéma dédié `knowledge` avec l'extension `pgvector`.

---

## 12. Performance — les décisions qui comptent

1. **Sortir l'orchestration du contexte de chat.** L'exécution passe par une file de jobs (Redis) et des boucles de code, pas par le contexte du LLM. Le LLM décide *quoi* faire ; le code exécute et ne renvoie que des résultats **normalisés et condensés**. Tokens bornés, comportement prévisible, moins d'hallucination.
2. **Normalisation des sorties d'outils.** Un dump `nmap`/`nuclei` brut = des milliers de tokens. Chaque wrapper parse en structure minimale. Le LLM ne voit jamais du brut.
3. **Parallélisme borné par le rate limit.** N workers en parallèle, mais token bucket par engagement → on ne dépasse jamais le débit autorisé. Essentiel en bug bounty (dépasser = bannissement).
4. **Cache agressif** (Redis) : recon déjà résolue, réponses LLM déterministes (par empreinte de prompt), chunks RAG chauds.
5. **Streaming vers l'UI** : résultats et flux proxy poussés au fil de l'eau (WebSocket). Checkpoint humain rapide.
6. **Scalabilité horizontale de l'exécution** : +1 worker = +capacité. VM légères (référence académique : 2 vCPU / 8 Go par worker).
7. **Base vectorielle dans PostgreSQL** : une dépendance, une surface et une latence de moins.
8. **Modèle adapté à la tâche** : modèle rapide/économique pour normalisation et tri, modèle fort pour raisonnement et corrélation. On ne paie cher que là où ça change le résultat.

---

## 13. Sécurité de l'outil lui-même

La sécurité du produit est traitée dès la première ligne de code.

### 13.1 Secrets
Aucun secret en code ni en git (`.gitignore` strict, **gitleaks** en pre-commit + CI). Clé maître via variable d'environnement (jamais en base/image ; en prod, envisager HashiCorp Vault). Secrets applicatifs chiffrés **AES-256-GCM** au repos, déchiffrés en mémoire à l'usage. Jamais renvoyés en clair à l'UI ni en log.

### 13.2 Authentification
Mots de passe **argon2id**. **MFA TOTP obligatoire**. JWT access court (15 min) + refresh rotatif révocable, signature asymétrique (clé privée sur le BFF). Verrouillage progressif.

### 13.3 Autorisation (RBAC)
| Rôle | Droits |
|---|---|
| `admin` | Tout : utilisateurs, clés globales, registre des modules, config système |
| `lead` | Créer/piloter des engagements, valider checkpoints, lancer EXPLOIT, livrer |
| `analyst` | RECON/SCAN/ANALYSE, éditer findings ; **pas** d'EXPLOIT ni de validation solo |
| `viewer` | Lecture seule |

Lancement EXPLOIT et validation d'autorisation : rôle `lead` minimum.

### 13.4 Journal d'audit inaltérable
`entry_hash = SHA-256(prev_hash || ts || actor || action || target || params)`. Toute altération casse la chaîne. Append-only (compte applicatif : `INSERT` seul). Journalise chaque exécution d'outil, décision d'agent, validation humaine, violation de scope, requête proxy rejouée, changement de config/module.

### 13.5 Prévention de l'injection de commande
**Jamais** de `shell=True` ni d'interpolation. Commandes en **tableaux d'arguments** validés (`["nmap","-p",port,target]`). Chaque argument validé par schéma : `target` matche une regex domaine/IP **et** est dans le scope ; `port` entier dans la plage ; wordlist dans une liste blanche. Outils sans shell interactif quand possible.

### 13.6 Isolation d'exécution
Conteneurs workers : `cap_drop: ALL`, non-root, `read_only` (sauf `/tmp` tmpfs), `no-new-privileges`, profils **seccomp**/**AppArmor**. Réseau isolé, **egress restreint** aux cibles autorisées (Gateway + pare-feu). Un worker compromis ne pivote pas, n'exfiltre pas, n'escalade pas.

### 13.7 Chaîne d'approvisionnement
Dépendances **épinglées** (lockfiles committés), **Dependabot**, **Trivy** + **Semgrep** + **Bandit** en CI (on s'audite avec nos outils), **SBOM** à chaque build, **commits signés** sur `main`.

### 13.8 Données d'engagement
Chiffrées au repos (schéma par engagement + fichiers chiffrés). **Rétention** : suppression sécurisée en fin de mission (`DROP SCHEMA` + purge artefacts). Sauvegardes chiffrées testées. Séparation stricte entre engagements.

### 13.9 Kill switch
Vide la file Redis, `SIGTERM`→`SIGKILL` aux process outils, tâches en `killed`, événement loggé. Un clic (dashboard) ou une commande (`tegbessou kill`).

### 13.10 Sécurité des DevTools
Le proxy est **dans** le chemin gardé : toute requête (capturée ou rejouée) passe par le Scope Enforcer et le rate limit. Une requête Repeater hors scope est refusée + loggée comme n'importe quelle tâche. Le navigateur piloté (Playwright) tourne sur le nœud d'exécution isolé, pas sur le poste opérateur.

---

## 14. Gardes anti-usage malhonnête

Câblées dans l'architecture, pas de simples avertissements.

1. **Autorisation bloquante** : aucune action offensive déblocable sans document d'autorisation validé (hash scellé dans l'audit).
2. **Scope enforcement matériel** : middleware bloquant sur le chemin de *chaque* appel d'outil **et** de chaque requête DevTools. Hors scope = refus + log + alerte.
3. **Traçabilité nominative** : chaque action attribuée à un utilisateur MFA. Pas d'anonymat opérationnel.
4. **Rate limiting imposé** : impossible d'en faire une machine à DoS.
5. **Double confirmation** des actions à impact.
6. **Bandeau de consentement légal** (dashboard + CLI), horodaté et loggé.
7. **Séparation des rôles** : `viewer`/`analyst` ne peuvent pas exploiter.
8. **Pas de mode autonome sur cible réelle** : checkpoints humains obligatoires ; seul `ctf` est « libre », restreint à une cible déclarée.

> Ces gardes protègent l'équipe autant que les tiers : en cas de litige, journal d'audit et autorisations scellées prouvent le cadre autorisé.

---

## 15. Structure du dépôt GitHub

**Monorepo.** Un seul dépôt, cohérence et atomicité des changements transverses.

```
tegbessou/
├── README.md
├── LICENSE
├── SECURITY.md
├── CONTRIBUTING.md
├── .gitignore                    # strict : .env, *.key, secrets/
├── .env.example
├── docker-compose.yml            # dev
├── docker-compose.prod.yml       # prod
├── Makefile
│
├── .github/
│   ├── workflows/{ci.yml, security.yml, release.yml}
│   ├── dependabot.yml
│   └── PULL_REQUEST_TEMPLATE.md
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── AGENTS.md                 # spec approfondie des agents (document livré)
│   ├── INSTALL.md
│   ├── SECURITY.md
│   ├── API.md
│   └── RUNBOOK.md
│
├── gateway/                      # API Gateway (serveur d'orchestration)
│   ├── app/{main.py, core/, security/, llm/, mcp/, tools/, rag/, jobs/, proxy/, models/, api/}
│   ├── tests/  ├── alembic/  ├── Dockerfile  └── pyproject.toml
│
├── api_pentest/                  # BFF (poste opérateur)
│   ├── app/{main.py, auth/, ws/, devtools_gw/, aggregators/, api/}
│   ├── tests/  ├── Dockerfile  └── pyproject.toml
│
├── dashboard/                    # React
│   ├── src/{pages/, components/, devtools/, api/, ws/, design-system/}
│   ├── package.json  └── Dockerfile
│
├── cli/                          # Typer
│   ├── tegbessou/{__main__.py, commands/, client.py}
│   ├── tests/  └── pyproject.toml
│
├── orchestrator/                 # n8n
│   ├── flows/                    # ~6 flows de phase (JSON versionnés) : phase_recon.json … phase_report.json + error_handler.json
│   ├── modules/                  # config déclarative des modules (*.yaml, §6) — lue par le Phase Runner de la Gateway
│   ├── INDEX.md                  # index des flows : rôle, version, dépendances
│   └── README.md
│
├── knowledge_base/               # RAG
│   ├── ingest/  └── README.md
│
└── deploy/
    ├── nginx/  ├── ca/  └── worker/   # image(s) worker + proxy + profils seccomp/apparmor
```

Conventions : Python `ruff`+`mypy`+`pytest` ; front `eslint`+`prettier` ; migrations Alembic versionnées `V0xx` (jamais éditées après merge) ; commits *Conventional* (`feat:`,`fix:`,`sec:`,`docs:`) signés.

---

## 16. Installation et déploiement

Objectif : un nouveau membre opérationnel en **moins de 15 minutes**. Tout via Docker Compose et un `.env`.

### 16.1 Prérequis
Docker Engine ≥ 24 + Compose v2, Git, accès au dépôt. Les binaires d'outils sont **dans l'image** worker.

> **Aucun build sur les hôtes de production** (surtout si la RAM est limitée). Images construites en CI, poussées sur `ghcr.io`, seulement **tirées** (`pull`) sur les machines.

### 16.2 Récupération et configuration
```bash
git clone git@github.com:zeromisconfig/tegbessou.git
cd tegbessou
cp .env.example .env      # renseigner les secrets
```

Variables `.env` essentielles :
```dotenv
TEGBESSOU_MASTER_KEY=          # 32 octets base64 — GÉNÉRER, ne jamais committer
JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_ed25519
POSTGRES_HOST=orchestration-host
POSTGRES_DB=tegbessou
POSTGRES_USER=tegbessou_app    # droits restreints (pas de DDL en prod)
POSTGRES_PASSWORD=
REDIS_URL=redis://orchestration-host:6379/0
PUBLIC_DOMAIN=tegbessou.exemple.tld
GATEWAY_INTERNAL_URL=https://gateway.internal:8443
MTLS_CA_PATH=/run/secrets/internal_ca.pem
PROXY_LISTEN=0.0.0.0:8888      # proxy DevTools (nœud d'exécution)
# ANTHROPIC_API_KEY= / OPENAI_API_KEY= / GOOGLE_API_KEY=  (optionnel : sinon au dashboard)
OLLAMA_BASE_URL=http://ollama:11434
```

Génération de la clé maître :
```bash
python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"
```

### 16.3 Démarrage (développement, sur le poste opérateur)
```bash
make up            # docker compose up -d (dev)
make migrate       # migrations Alembic
make seed-kb       # ingère la base de connaissances
make seed-modules  # charge le registre des modules (§6)
make create-admin  # premier compte admin + enrôlement MFA
```

### 16.4 Déploiement production
**Serveur d'orchestration** (orchestration + état) :
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d postgres redis gateway n8n
docker compose -f docker-compose.prod.yml run --rm gateway alembic upgrade head
```
**Poste opérateur** (présentation + contrôle) :
```bash
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d dashboard api_pentest nginx
```
**Nœud worker** (exécution + proxy) :
```bash
docker compose -f docker-compose.prod.yml pull worker
docker compose -f docker-compose.prod.yml up -d worker
# Scaler : --scale worker=4
```
**n8n** : importer `orchestrator/flows/*.json` (UI ou API).

### 16.5 Vérification
```bash
make healthcheck   # DB, Redis, Gateway, mTLS, worker, proxy
tegbessou auth login
```
Vert = installation réussie ; sinon le check indique le composant fautif.

### 16.6 CLI seule
```bash
pipx install "git+https://github.com/zeromisconfig/tegbessou.git#subdirectory=cli"
tegbessou auth login
```

---

## 17. Workflow de développement en équipe

Léger mais discipliné.

### 17.1 Branches
`main` protégée (toujours déployable), `develop` (intégration, optionnel à deux), `feat/<brique>`, `fix/`, `sec/`. Protection `main` : commits signés, CI verte, ≥1 revue (2 quand l'équipe grandit), pas de push direct.

### 17.2 CI
- **ci.yml** : lint (`ruff`,`eslint`), typage (`mypy`), tests (`pytest`, front), build.
- **security.yml** : `gitleaks`, `semgrep`+`bandit`, `trivy`, SBOM. **Bloquant** sur `main`.
- **release.yml** : tag → images signées vers `ghcr.io`.

### 17.3 Tests — « une brique prouvée »
Chaque brique et chaque **module** livre ses tests. Suite d'intégration bout en bout sur cibles de lab contrôlées (DVWA, OWASP Juice Shop, VM volontairement vulnérables dédiées aux tests). **Jamais** de cible tierce pour tester le produit.

### 17.4 Revue de code (`PULL_REQUEST_TEMPLATE.md`)
Tests verts · pas de secret (gitleaks) · entrées validées (anti-injection) · actions sensibles journalisées · scope enforcement respecté si nouvel appel d'outil ou nouveau module · registre des modules mis à jour · doc `docs/` à jour si contrat d'API changé.

### 17.5 Design-to-code
Figma pour le design-to-code : maquetter, générer le squelette, raffiner. Design system maison réutilisable.

---

## 18. Feuille de route par briques

Une brique n'est « faite » que testée et documentée. Ne pas commencer la suivante avant que la précédente soit verte.

**Phase 0 — Fondations** : dépôt+CI/CD+compose dev (B0.1) ; DB+migrations+registre modules (B0.2) ; BFF auth JWT+MFA+RBAC+audit chaîné (B0.3) ; Gateway Vault+Scope Enforcer+Rate Limiter+Audit Logger (B0.4). *Preuve* : requête hors scope refusée+loggée.

**Phase 1 — Exécution & RECON** : Job Dispatcher+file+worker sandbox (B1.1) ; wrappers subfinder/httpx/nmap/katana/gau (B1.2) ; Phase Runner + registre + modules RECON M1-M9 + flow n8n `phase_recon` + agent RECON (B1.3) ; dashboard cockpit + données recon temps réel (B1.4). *Preuve* : RECON complet sur VM de lab, surface affichée, tout in-scope et loggé.

**Phase 2 — SCAN & findings** : wrappers nuclei/semgrep + agent SCAN + WSTG RAG (B2.1) ; findings+preuves+tableau temps réel (B2.2) ; agent ANALYSE (dédup, CVSS 4.0, NVD/ATT&CK, scores de criticité + relations `asset_edges`) (B2.3) ; **carte de reconnaissance** (graphe Cytoscape.js : nœuds/arêtes, code couleur criticité, zones de chaleur, plus courts chemins, choke points, filtres) (B2.4). *Preuve* : findings scorés/étayés/dédupliqués ; graphe de surface d'attaque explorable avec zones critiques mises en évidence.

**Phase 3 — Multi-LLM, DevTools & CLI** : LLM Router complet (OpenAI/Google/Ollama, budgets, fallback) (B3.1) ; **DevTools intégrés** (proxy mitmproxy + Repeater + inspecteurs) (B3.2) ; CLI Typer à parité (B3.3). *Preuve* : bascule de provider ; requête rejouée via Repeater dans le scope ; engagement piloté en CLI.

**Phase 4 — EXPLOIT, Web3 & reporting** : agent EXPLOIT + double confirmation + scénarios YAML (B4.1) ; Web3 (Slither/Mythril/Foundry/Echidna/Medusa, méthodo 3-temps) (B4.2) ; agent REPORT + PDF (B4.3). *Preuve* : engagement complet RECON→REPORT sur lab Web2 + audit d'un contrat Solidity de test.

**Phase 5 — Durcissement & échelle** : mTLS+CA interne+seccomp/apparmor (B5.1) ; scalabilité workers+cache+optim tokens (B5.2) ; runbook incident+kill switch testé+sauvegardes+rétention (B5.3). *Preuve* : audit de sécurité interne du produit sans finding critique.

---

## 19. Annexes

### 19.1 Récapitulatif de la stack
| Couche | Technologie |
|---|---|
| Frontend | React + TanStack Query + Recharts |
| Carte de surface d'attaque | Cytoscape.js (Sigma.js si > 50k nœuds) |
| DevTools | mitmproxy (proxy) + Playwright (navigateur piloté) |
| BFF | FastAPI + Pydantic v2 |
| Gateway | FastAPI + cryptography + redis-py |
| Orchestration | n8n (flows JSON versionnés) |
| LLM | Anthropic / OpenAI / Google / Ollama |
| RAG / DB | PostgreSQL + pgvector (schéma/engagement) |
| File / cache / pub-sub | Redis |
| Outils Web2 | nmap, httpx, subfinder, katana, gau, nuclei, ffuf, sqlmap, semgrep, arjun, linkfinder, dalfox, whatweb, gowitness |
| Outils Web3 | Slither, Mythril, Foundry, Echidna, Medusa, Halmos |
| SAST produit | Semgrep, Bandit, Trivy, gitleaks |
| CLI | Python + Typer + rich |
| Conteneurs / CI | Docker + Compose / GitHub Actions + ghcr.io |

### 19.2 Glossaire
BFF (Backend-For-Frontend) · MCP (Model Context Protocol) · WSTG (OWASP Web Security Testing Guide v4.2) · PTES (Penetration Testing Execution Standard) · CVSS 4.0 (scoring de sévérité) · RAG (Retrieval-Augmented Generation) · IDOR/BOLA (failles d'autorisation) · SAST/DAST (analyse statique/dynamique) · KEV (CISA Known Exploited Vulnerabilities) · Checkpoint humain (arrêt de validation obligatoire) · Module (unité d'un agent, ajoutable/retirable — §6).

### 19.3 Sources et références (état de l'art août 2026)
OWASP WSTG v4.2, OWASP Top 10 (2021/2025), PTES ; recherche sur les agents LLM de pentest (PentestAgent AsiaCCS 2025, AutoPentest 2025) et le plafond d'autonomie 15-25 % ; pattern MCP pour outils de sécurité et saturation du contexte ; méthodologies de recon 2026 (JS mining, favicon hashing, corrélation techno→CVE, 23,6 % de CVE exploitées dès la divulgation) ; Web3 (GPTScan/MetaScan 3-temps, Slither, Mythril, fuzzing Foundry/Echidna/Medusa, vérification formelle Halmos/Certora — inflection 2025) ; NVD, CISA KEV, MITRE ATT&CK.

> Ces références datent d'août 2026. Le domaine bouge vite : revalider avant chaque phase majeure. La modularité (§6) est là pour absorber ces évolutions sans réécriture.

---

*Fin du document maître. À lire avec `docs/AGENTS.md`. Toute décision qui s'écarte de ce document doit être discutée en équipe et répercutée ici — le document est la source de vérité de l'architecture.*
