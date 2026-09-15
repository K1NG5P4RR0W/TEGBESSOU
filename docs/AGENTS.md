# TEGBESSOU — Spécification approfondie des agents et de la méthodologie

> Complément technique au document d'implémentation. Détaille, agent par agent, les modules, techniques, outils, données capturées, rôle du LLM et garde-fous.
>
> **Le produit s'appelle désormais Tegbessou** (remplace « PENTAFORGE » partout). À propager dans le dépôt et le document maître.
>
> **Marque :** zeromisconfig — **Version :** 1.0 — **Août 2026**
>
> État de l'art arrêté à août 2026. Le domaine bouge vite : revalider avant chaque phase majeure.

---

## Principe directeur de la conception des agents

Un agent Tegbessou n'est pas « un LLM qui lance des outils ». C'est un **pipeline structuré** où chaque module fait une chose précise, produit une donnée structurée, et où le LLM intervient à des points choisis pour **raisonner, corréler et prioriser** — jamais pour halluciner un résultat.

Trois règles transversales gouvernent tous les agents :

1. **Passif avant actif.** On épuise les sources publiques (aucun paquet vers la cible) avant de toucher la cible. C'est plus sûr, plus discret, et souvent plus riche.
2. **Preuve obligatoire.** Aucune donnée n'est présentée comme un fait sans son artefact source (fichier, ligne, réponse HTTP). « Trouvé l'endpoint X » ne suffit pas ; il faut « trouvé X dans le fichier Y, ligne Z, présent uniquement dans les builds depuis Q3, ne correspond à aucune API documentée » — c'est cette note qui dit *comment valider*.
3. **Le LLM raisonne, le code exécute.** Le LLM ne voit jamais un dump brut ; il reçoit des données normalisées et rend des hypothèses priorisées. L'exécution passe par la file de jobs (voir document maître §12).

Le passage d'« énumération » à « intelligence » est le cœur du métier : vider LinkFinder dans un fichier de 800 endpoints, ce n'est pas de la recon, c'est de la collecte. L'intelligence, c'est repérer que `/api/v2/admin/users` ne correspond à aucune surface d'API documentée et formuler une hypothèse sur son existence et son contrôle d'accès. **C'est exactement ce que le LLM apporte** — et c'est là qu'on le place.

---

# AGENT 1 — RECON (Reconnaissance)

Objectif : construire la carte la plus complète possible de la surface d'attaque **sans jamais sortir du scope**, puis produire une liste d'hypothèses priorisées qui oriente tout le reste de l'engagement.

RECON est découpé en **9 modules**. Chacun alimente une base commune (`assets`, voir document maître §11) et publie ses résultats en temps réel au dashboard.

```
 RECON
 ├─ M1  OSINT & intelligence organisationnelle (passif)
 ├─ M2  Énumération de sous-domaines (multi-source)
 ├─ M3  Découverte d'infrastructure & IP d'origine
 ├─ M4  Sondage des hôtes vivants & fingerprinting
 ├─ M5  Identification technologique fine & versions
 ├─ M6  Corrélation CVE
 ├─ M7  Crawling & analyse du code source des pages (JS mining)
 ├─ M8  Cartographie des points d'entrée
 ├─ M9  Dorking & OSINT ciblé sur identifiants découverts
 └─▶ Synthèse LLM → hypothèses priorisées → CHECKPOINT humain
```

---

## M1 — OSINT & intelligence organisationnelle (passif)

But : comprendre *qui* est la cible avant de comprendre *quoi* attaquer. Aucun paquet vers la cible.

Collecte :
- **WHOIS / RDAP** : titulaire, dates, registrar, serveurs de noms.
- **ASN & plages IP** : identifier les blocs réseau de l'organisation (`amass intel` avec org/ASN, requêtes RDAP). Un ASN découvert élargit tout le scope potentiel.
- **Certificats (Certificate Transparency)** : chaque certificat SSL émis est un enregistrement public — source passive parmi les plus rentables. On interroge `crt.sh`, Censys, et les logs CT.
- **DNS complet** : A, AAAA, MX, TXT, NS, CNAME, SPF/DMARC (le TXT révèle souvent des fournisseurs tiers utilisés).
- **Actifs liés** : un même identifiant d'analytics (Google Analytics, Tag Manager) ou un même favicon peut relier filiales, sociétés acquises et domaines internationaux. Un ID d'analytics peut révéler toute une famille corporate.
- **Fuites de code public** : `github-subdomains`, GitDorker, githound sur les dépôts publics de l'organisation et de ses employés — sous-domaines, endpoints internes, secrets committés par erreur.

Rôle LLM : à partir de ces bribes, l'agent reconstitue l'**empreinte organisationnelle** (fournisseurs tiers, stack probable, périmètre réel) et signale les extensions de scope à faire valider par l'humain (un ASN ou un domaine lié n'entre dans le scope actif *que* si l'autorisation le couvre).

Garde : tout élargissement de scope issu de l'OSINT est **proposé**, jamais activé automatiquement. Le Scope Enforcer reste la barrière.

---

## M2 — Énumération de sous-domaines (multi-source)

But : découvrir un maximum de sous-domaines. La règle empirique 2026 : **aucun outil seul ne suffit** — Amass intègre ~87 sources, Subfinder ~45, mais plus de 200 fournisseurs de données existent. On combine et on déduplique.

**Passif (premier passage, aucun trafic cible) :**
- `subfinder -d cible -all -recursive` — rapide, API multi-sources.
- `amass enum -d cible` — moteur OSINT profond, corrèle de nombreuses sources.
- `assetfinder`, `findomain` — sources complémentaires.
- `chaos` (dataset curé ProjectDiscovery, clé API) — noms déjà connus.
- `github-subdomains` — mine le code des développeurs.
- CT logs via `crt.sh` (parsing JSON), Censys, Subdominator (~50 sources freemium).

**Actif (second passage, si scope l'autorise) :**
- Brute-force DNS avec wordlist dédiée (`amass enum -brute`, `puredns`, `dnsx`).
- Génération de permutations (`alterx`) puis résolution (`dnsx`) — attrape les patterns type `api-staging-2`.

Pipeline type : `subfinder + amass + assetfinder → dnsx (résolution) → dédup (anew/sort -u)`.

Sortie : liste dédupliquée de sous-domaines résolus, avec la source de découverte par nom (traçabilité). Chaque nom devient un `asset` de type `subdomain`.

---

## M3 — Découverte d'infrastructure & IP d'origine

But : voir *derrière* les CDN/WAF. Un test lancé sur un CDN/WAF ne teste pas l'application elle-même ; trouver l'IP d'origine est souvent la clé.

Techniques 2026 :
- **Hash de favicon (MurmurHash3, compatible Shodan).** Les entreprises réutilisent le même favicon sur toute leur infra. Le hash est une empreinte cherchable dans Shodan/Censys/FOFA/ZoomEye. Un reverse-proxy normalise les en-têtes HTTP mais **ne normalise pas le contenu du favicon** — d'où sa puissance pour retrouver l'origine sans envoyer de payload. Outils : `favUp`, `favirecon`, `FavFreak` (identifie les hash uniques sur une liste de sous-domaines — un hash différent = infra différente, à investiguer). Un seul hash a déjà rendu, dans un cas réel, 363 hôtes et 373 IP.
- **Pivot par certificat** : `ssl.cert.subject.cn:cible` sur Shodan/Censys.
- **IP historiques** : `originiphunter`, bases d'IP passées — une IP qui servait le domaine avant la mise derrière CDN reste souvent joignable.
- **Vérification d'origine** : `hakoriginfinder` — si une IP renvoie le favicon de la cible sans être une IP du CDN, c'est le serveur d'origine.
- **VHOST fuzzing** : certains hôtes ne répondent qu'avec le bon en-tête `Host` — invisibles aux scanners normaux. `ffuf` sur l'en-tête Host contre les IP découvertes expose des services internes.

Sortie : IP réelles, services exposés, hôtes virtuels cachés. `asset` de type `host`/`port`.

Garde : le fingerprinting passif (Shodan/Censys) ne touche pas la cible. Le VHOST fuzzing est **actif** et soumis au rate limit + scope.

---

## M4 — Sondage des hôtes vivants & fingerprinting initial

But : parmi tous les noms/IP découverts, savoir lesquels répondent, et capturer une première signature.

Outil pivot : **`httpx`**. En un passage : hôtes vivants, codes de statut, titres, technologies détectées (`-td`), serveur (`-server`), longueurs, redirections, sortie JSON exploitable. On ne conserve que le vivant pour la suite.

Complément : capture d'écran de masse (`gowitness`/`aquatone`) — un humain scanne visuellement 200 hôtes et repère instantanément un panneau d'admin, une page de login, une erreur de debug, une instance oubliée.

Sortie : inventaire des hôtes vivants avec statut, titre, techno préliminaire, capture. Alimente le dashboard (onglet « Technologies » + galerie de captures).

---

## M5 — Identification technologique fine & versions

But : savoir *exactement* ce qui tourne, **avec les versions**. Connaître la stack réduit la surface : CVE, chemins par défaut, astuces spécifiques au framework et contournements d'auth dépendent tous de ce qui tourne.

Signaux exploités :
- **En-têtes HTTP** : `Server`, `X-Powered-By`, cookies (noms de session révélateurs : `PHPSESSID`, `JSESSIONID`, `laravel_session`…).
- **Corps de réponse** : marqueurs de framework, chemins d'assets, commentaires.
- **Globals JavaScript** : `__REACT_DEVTOOLS_GLOBAL_HOOK__` présent en build de prod confirme React sans ambiguïté ; marqueurs Angular/Vue/Svelte.
- **Source maps** générées en CI (`--source-map=true`) : exposent la version exacte et l'arborescence du projet.
- **Hash de favicon** : mappe le hash → produit (Nuclei maintient une liste ; les templates CVE embarquent souvent le hash du produit vulnérable dans leurs métadonnées).

Outils : `whatweb -a 3`, Wappalyzer CLI, et fingerprinting orienté sécurité type `truestack` (détection de patchs rétroportés, sondage différentiel comportemental, corrélation CVE, audit des en-têtes de sécurité HSTS/CSP).

> **Point de vigilance** : la version affichée par un en-tête peut mentir (patch rétroporté, bannière falsifiée). L'agent distingue **version déclarée** et **posture réelle** ; il note le niveau de confiance de chaque identification.

Sortie : par hôte, la liste des technologies avec version et niveau de confiance. C'est l'entrée directe de M6.

---

## M6 — Corrélation CVE

But : transformer « techno + version » en « liste de CVE candidates », immédiatement, car le pipeline empreinte→exploit est court et largement automatisé. Repère marquant : **23,6 % des CVE activement exploitées le sont le jour de leur divulgation publique, voire avant** — la fenêtre de réaction est nulle, l'outil doit signaler vite.

Mécanique :
- Chaque techno/version identifiée en M5 est mappée vers son **CPE**, puis interrogée contre la base **NVD** (API) et les sources de la KB RAG (voir document maître §8).
- Croisement avec les **templates Nuclei** correspondants (les templates CVE portent le CPE et souvent le hash favicon du produit).
- Priorisation par exploitabilité réelle : existence d'un exploit public, présence dans les listes CISA KEV (Known Exploited Vulnerabilities), score CVSS, et exposition effective de l'instance.

Rôle LLM : filtrer le bruit. Une version peut matcher 40 CVE dont 3 pertinentes pour la configuration réelle. L'agent croise CVE ↔ conditions d'exploitation ↔ ce qui est réellement exposé, et ne remonte que les candidates plausibles, chacune avec sa condition de validation.

Garde : à ce stade, **rien n'est confirmé** — ce sont des candidates. La confirmation passe par SCAN puis EXPLOIT, avec preuve.

Sortie : CVE candidates priorisées, rattachées à l'`asset` concerné, avec condition de test.

---

## M7 — Crawling & analyse du code source des pages (JS mining)

But : le JavaScript est la surface d'attaque la plus sous-estimée. Les bundles exposent routinièrement des endpoints, des API internes et des secrets. Lire du JS minifié à la main est atroce ; **un LLM qui lit 3 000 lignes obfusquées et signale en dix secondes « ceci ressemble à une route admin interne : `/api/v2/internal/impersonate` » est un vrai multiplicateur de temps.** C'est le module où le LLM brille le plus.

### Étape 1 — Collecte des URLs et des JS

- **Passif** (historique) : `gau`, `waybackurls` — récupèrent les URLs connues, y compris des endpoints « retirés » mais non décommissionnés (source d'or : la fonctionnalité supprimée du front reste active côté API).
- **Actif** : crawlers JS-aware — `katana -jc -d 3`, `hakrawler`, `gospider`, `getJS`. On filtre les `.js`, on vérifie le vivant (`httpx -mc 200`), on déduplique (`anew`, `uro`).

### Étape 2 — Extraction

- **Endpoints & paramètres** : `LinkFinder` (regex sur URLs/paths/params), extraction manuelle par regex ciblant `/(api|rest|graphql|v[1-9]|internal|private|admin|debug|beta|mobile)/`.
- **Source maps (`.js.map`)** : si exposées, elles rendent le **code source non compilé**. `sourcemapper`/`restore-source-tree` reconstruit l'arborescence — c'est un accès quasi-source au front.
- **Secrets** : `SecretFinder`, `TruffleHog`, patterns `gf` (aws-keys, api-keys) — clés cloud (AWS, GCP, Firebase, Supabase, Stripe), PAT GitHub, JWT, clés RSA.
- **Sources/sinks DOM XSS** : repérage des flux dangereux dans le JS.

### Étape 3 — Raisonnement LLM (le cœur)

Chaque bundle est passé au LLM avec un prompt ciblé : identifier clés d'API en dur, chemins d'endpoints internes, noms de feature-flags, fragments de schéma GraphQL, et toute fonctionnalité d'admin/debug/impersonation. Le LLM ne se contente pas d'extraire : il **hiérarchise** (« ce fichier n'existe que dans les builds Q3, suggère une migration admin dépréciée peut-être non décommissionnée côté API ») et attache le raisonnement à chaque piste.

Sortie : inventaire JS (fichiers vivants / historiques / source maps), endpoints d'API avec fichier+ligne source et exigence d'auth supposée, secrets candidats, hypothèses classées avec test plan. `asset` de types `endpoint`, `param`, plus findings candidats pour les secrets.

> **Discipline anti-hallucination** : un secret « trouvé » est marqué `candidate` tant qu'il n'est pas vérifié comme vivant (et sa vérification, si active, passe par le scope + le rate limit). Une clé peut être révoquée, factice, ou un leurre.

---

## M8 — Cartographie des points d'entrée

But : répondre précisément à « par où peut-on interagir avec l'application ? ». C'est la synthèse qui rend l'attaque *dirigée*.

Points d'entrée catalogués :
- **Formulaires** : login, inscription, contact, recherche — chaque champ, sa méthode (GET/POST), ses paramètres, sa validation côté client (à contourner côté serveur).
- **Champs de recherche** : candidats injection (SQLi, NoSQLi, SSTI selon la stack).
- **Upload de fichiers** : type accepté, contrôle côté client vs serveur, chemin de stockage — surface classique (RCE via upload, path traversal, XXE si parsing).
- **Paramètres cachés** : `arjun` découvre des paramètres HTTP non exposés dans l'UI.
- **API & GraphQL** : endpoints REST versionnés, schéma GraphQL (introspection si activée), méthodes autorisées. Les failles d'autorisation (BOLA/IDOR, mass assignment) y dominent en 2026.
- **Architecture du site** : arborescence, séparation front/back, technologies par zone, points d'auth, transitions de rôle. `feroxbuster`/`ffuf` pour le content discovery ; croisement avec les endpoints de M7.
- **En-têtes & cookies** : mécanisme de session, flags de sécurité, CORS, CSP.

Rôle LLM : construire une **carte lisible** de l'application (qui parle à quoi, où sont les frontières de confiance) et marquer les points à fort potentiel (auth, upload, endpoints non documentés, transitions de privilège). C'est ce qui « oriente mieux le pentest » demandé.

Sortie : carte des points d'entrée, priorisée par potentiel, prête à alimenter SCAN.

---

## M9 — Dorking & OSINT ciblé sur identifiants découverts

But : deux usages. (a) Le **dorking** pour trouver de l'exposition indexée par les moteurs. (b) Le **pivot OSINT** depuis un identifiant découvert dans l'application — typiquement, en CTF, remonter sur l'admin dont on a trouvé le nom/e-mail sur le site.

### Dorking

Requêtes ciblées (Google, Bing, DuckDuckGo) sur le domaine en scope : fichiers exposés (`filetype:`), répertoires ouverts (`intitle:index.of`), panneaux d'admin (`inurl:admin`), fuites (`site:pastebin.com cible`), erreurs verbeuses, documents à métadonnées. Le LLM génère des dorks adaptés à la stack détectée en M5 et trie les résultats par pertinence. Extraction des métadonnées de documents trouvés (auteurs, logiciels, chemins internes).

### Pivot OSINT sur identifiant (mode CTF surtout, engagement autorisé sinon)

Quand l'application révèle un identifiant (nom d'admin, e-mail, pseudo, ID d'employé), l'agent peut pivoter :
- **Énumération de présence** d'un pseudo sur les plateformes (recherche de comptes homonymes) ;
- **Vérification d'exposition de credentials** via services publics d'index de fuites (le pseudo/e-mail apparaît-il dans un corpus public de brèches connues ?) ;
- **Corrélation** e-mail ↔ pseudo ↔ dépôts publics ↔ métadonnées de documents.

En CTF, c'est souvent la mécanique même du challenge (l'info trouvée sur le site débloque l'étape suivante). En pentest/bug bounty, c'est une évaluation d'exposition (utile pour un test de phishing ou un contrôle de fuite de credentials).

> **Garde renforcée.** Ce module est le plus sensible. Il n'est activable que : (1) en mode `ctf` sur un scope cible déclaré, ou (2) en mode `pentest`/`bug_bounty` **si le mandat couvre explicitement l'OSINT sur personnes**. Chaque identifiant pivoté est journalisé. L'agent ne construit pas de dossier sur une personne au-delà de ce que l'objectif d'engagement justifie, et s'appuie uniquement sur des sources publiques et licites. Aucune donnée issue de brèches n'est stockée en clair ; on stocke le fait « e-mail exposé dans brèche connue », pas le mot de passe.

---

## Synthèse RECON → hypothèses priorisées

Une fois les 9 modules passés, l'agent RECON produit la **livraison de phase** :

1. **Surface d'attaque consolidée** : sous-domaines, hôtes vivants, IP d'origine, technologies+versions, endpoints, paramètres, points d'entrée.
2. **CVE candidates** rattachées aux actifs.
3. **Hypothèses priorisées** : chaque hypothèse = {description, source/preuve, classe de vuln suspectée, impact potentiel, plan de validation, statut `pending`}. Classées par (probabilité × impact).
4. **Cartographie lisible** de l'application pour l'opérateur.

Puis **CHECKPOINT humain** : l'opérateur relit, écarte les fausses pistes, ajuste le scope, et valide (ou non) le passage à SCAN. Rien ne continue sans ce feu vert.


---

# AGENT 2 — SCAN (Analyse statique & dynamique)

Objectif : transformer les hypothèses de RECON en **vulnérabilités candidates étayées**, par analyse statique (code) et dynamique (application vivante), en suivant la méthodologie OWASP WSTG v4.2. Chaque candidate porte sa preuve.

SCAN se décline selon le mode : `audit_code` (statique pur, pas de trafic cible) et `pentest`/`bug_bounty`/`ctf` (statique + dynamique).

```
 SCAN
 ├─ M1  Scan de vulnérabilités piloté par templates (dynamique)
 ├─ M2  Couverture WSTG dirigée par hypothèses
 ├─ M3  Analyse statique Web2 (SAST code source)
 ├─ M4  Analyse statique Web3 (contrats)
 ├─ M5  Fuzzing dirigé
 └─▶ Consolidation candidates + preuves → CHECKPOINT humain
```

## M1 — Scan piloté par templates (dynamique)

**Nuclei** est le standard : des milliers de templates communautaires pour CVE, mauvaises configurations, panneaux exposés, identifiants par défaut. **Il signale des candidates — chacune est validée manuellement avant d'être revendiquée.** L'agent alimente Nuclei avec les templates correspondant aux CVE candidates de RECON (ciblage, pas scan aveugle), au rate limit de l'engagement.

Sortie : hits Nuclei avec le template déclencheur et la réponse — chaque hit est un `finding` en statut `candidate` avec preuve attachée.

## M2 — Couverture WSTG dirigée par hypothèses

L'agent suit la checklist **OWASP WSTG v4.2** (109 tests), mais **priorisée par les hypothèses de RECON**, pas déroulée mécaniquement. Les catégories à fort rendement en 2026 :
- **Contrôle d'accès / autorisation** : IDOR/BOLA (horizontal & vertical), mass assignment, path traversal, contournement RBAC — parmi les classes les mieux rémunérées en bug bounty.
- **Injection** : SQLi, NoSQLi, SSTI, XXE, injection GraphQL (ajoutée en WSTG v4.2), injection de commande.
- **Authentification & session** : logique de login, gestion de session, réinitialisation de mot de passe, MFA.
- **Logique métier** : les failles que les scanners automatiques ratent — c'est là que le raisonnement LLM + humain fait la différence.

Pour chaque test, l'agent référence l'ID WSTG, exécute la vérification (au rate limit), et attache la preuve.

## M3 — Analyse statique Web2 (SAST du code source)

En mode `audit_code` ou en complément quand le code est disponible :
- **Semgrep** avec règles communautaires + règles maison (patterns propres à la stack cible).
- **Bandit** pour le code Python.
- **VulnHuntr** pour les chaînes de vulnérabilités dans le code — utile aussi sur les pipelines No-Code/agents IA (angle MCP).

Le LLM lit les zones signalées, distingue vrai positif et bruit, et reconstruit le **flux de données** (source → sink) qui rend la vuln exploitable.

## M4 — Analyse statique Web3 (contrats)

Méthodologie éprouvée en **trois temps** (approche GPTScan/MetaScan) : décomposition de la vulnérabilité → matching par LLM → **confirmation statique**. Elle atteint >90 % de précision sur les contrats token et évite les faux positifs du LLM seul.

Outils :
- **Slither** : analyse statique de référence (reentrancy, contrôle d'accès, arithmétique, patterns SWC).
- **Mythril** : exécution symbolique sur bytecode EVM.
- Le LLM raisonne sur la **logique métier** du protocole (là où les outils échouent) : hypothèses économiques, invariants attendus, interactions inter-contrats.

## M5 — Fuzzing dirigé

**Web2** : fuzzing de paramètres et d'endpoints (`ffuf`), fuzzing de valeurs sur les points d'entrée cartographiés en RECON/M8. `dalfox` pour le XSS, `sqlmap` (contrôlé) pour confirmer une injection candidate.

**Web3** : le fuzzing d'invariants est devenu la baseline 2026. On teste des propriétés qui doivent tenir dans tous les états :
- **Foundry (invariant testing)** : baseline « proof-carrying » la moins chère, le plus répandu.
- **Echidna** (Trail of Bits) : property-based, stateful.
- **Medusa** : fuzzer Go parallélisé, coverage-guided — souvent le plus efficace en mode non guidé sur des invariants difficiles.
- **Halmos / Certora** (vérification formelle) : adoption à un point d'inflection en 2025 — ~1/3 des engagements haut de gamme embarquent au moins une suite d'invariants formelle ; les 2/3 restants s'appuient sur le fuzzing d'invariants Foundry.

Le LLM aide à **générer les invariants** (« un utilisateur ne doit jamais pouvoir retirer plus qu'il n'a déposé ») à partir de la logique du protocole — tâche où l'humain perd du temps et où le LLM accélère réellement.

Sortie SCAN : liste consolidée de vulnérabilités `candidate`, chacune avec classe (WSTG/CWE/SWC), preuve (réponse HTTP, ligne de code, contre-exemple de fuzzing), et hypothèse d'impact. **CHECKPOINT humain** : l'opérateur trie ce qui part en EXPLOIT.

---

# AGENT 3 — EXPLOIT (Test & validation)

Objectif : **confirmer l'exploitabilité** des candidates retenues, produire une preuve reproductible, **sans causer de dégât**. C'est la phase la plus encadrée de Tegbessou.

```
 EXPLOIT
 ├─ Pré-requis : validation humaine explicite de la liste des candidates
 ├─ M1  Confirmation contrôlée
 ├─ M2  Construction de la preuve reproductible
 ├─ M3  Chaînage (si pertinent et autorisé)
 └─▶ Vulns confirmées + PoC → ANALYSE
```

## Garde-fous d'entrée (non négociables)

- **Ne démarre jamais** sans validation humaine de la liste des candidates à tester (rôle `lead` minimum, voir document maître §13.3).
- Toute action à **impact potentiel** (écriture, suppression, envoi de masse, mouvement de fonds sur Web3) exige une **double confirmation** distincte.
- Rate limit renforcé ; respect strict des règles du programme (bug bounty) ou du SoW (pentest) ; fenêtre horaire respectée.

## M1 — Confirmation contrôlée

L'agent exécute la vérification **minimale** qui prouve la vuln sans l'exploiter à fond. Exemples de posture :
- IDOR : prouver l'accès à un objet d'un autre utilisateur en **lecture d'un identifiant de test**, pas en exfiltrant la base.
- Injection : prouver l'exécution avec une charge **inerte et marquée** (valeur témoin), pas un dump complet.
- Upload : prouver le contournement de contrôle avec un fichier **témoin bénin**, pas un webshell fonctionnel.
- Web3 : rejouer l'exploit sur un **fork local** (Foundry) plutôt que sur le mainnet — c'est la pratique standard 2026 pour les PoC de contrats (génération de PoC sur digital twin / fork, jamais sur l'actif réel).

> **Principe** : la preuve d'exploitabilité s'arrête au seuil de démonstration. On ne « va pas jusqu'au bout » d'un impact destructeur pour le plaisir de la preuve.

## M2 — Construction de la preuve reproductible

Chaque confirmation produit un **artefact rejouable** : requête exacte (méthode, URL, en-têtes, corps), réponse observée, condition de succès, prérequis (auth, état). Pour Web3 : le script de test Foundry qui reproduit sur fork. C'est la matière première du scénario YAML rejouable (voir REPORT).

## M3 — Chaînage (si pertinent et autorisé)

Les bugs qui comptent sont souvent des **chaînes** (ex. IDOR + mass assignment → escalade). L'agent propose des chaînes plausibles à partir des candidates confirmées ; leur exécution reste soumise aux mêmes gardes (validation + double confirmation si impact).

Sortie EXPLOIT : vulnérabilités `confirmed` avec preuve reproductible, ou `rejected` (faux positif, avec la raison — utile pour ne pas rejouer l'erreur).

---

# AGENT 4 — ANALYSE (Scoring, corrélation, priorisation)

Objectif : transformer un tas de résultats bruts en **findings exploitables, dédupliqués et priorisés**. Agent transverse, sollicité après SCAN et EXPLOIT.

```
 ANALYSE
 ├─ M1  Déduplication & corrélation multi-outils
 ├─ M2  Scoring CVSS 4.0 (proposé, validé par l'humain)
 ├─ M3  Enrichissement (CVE / ATT&CK / WSTG / KB)
 └─ M4  Priorisation par risque réel
```

## M1 — Déduplication & corrélation

Une même vuln vue par Nuclei, par le scan manuel et par le fuzzing = **un seul finding**. L'agent corrèle par actif + classe + emplacement, fusionne les preuves, et évite le rapport gonflé de doublons qui décrédibilise.

## M2 — Scoring CVSS 4.0

Calcul automatique du **vecteur CVSS 4.0** (Base + Threat + Environmental si le contexte client est connu). Le score est **proposé** ; l'humain le valide ou l'ajuste — jamais une décision autonome finale. Le vecteur est éditable au dashboard (écran Finding).

## M3 — Enrichissement

- **CVE** : correspondance NVD, statut d'exploitation (CISA KEV), exploit public éventuel.
- **MITRE ATT&CK** : technique(s) associée(s), pour le contexte défensif du client.
- **WSTG / CWE / SWC** : classification normalisée.
- **RAG** : writeups publics de vulns similaires → chemins d'exploitation et remédiations éprouvés.

## M4 — Priorisation par risque réel

Classement par (impact × probabilité × exploitabilité **dans le contexte réel**), pas par score brut. Une CVSS 9.8 non atteignable dans la configuration réelle passe derrière une 6.5 trivialement exploitable et à fort impact métier. Le LLM argumente la priorisation ; l'humain tranche.

Sortie : findings finalisés, scorés, priorisés, prêts pour le rapport.

---

# AGENT 5 — REPORT (Rédaction & rejouabilité)

Objectif : produire deux livrables — le **rapport** et les **scénarios rejouables** — et ne rien livrer sans relecture humaine.

## M1 — Rapport

Structure **PTES** :
1. Résumé exécutif (pour décideurs : risque global, findings majeurs, en langage clair).
2. Périmètre & méthodologie (scope, autorisation, phases, outils — traçabilité).
3. Findings détaillés : titre, classe, CVSS 4.0 (vecteur + score), preuve, impact, remédiation, références.
4. Annexes : preuves complètes, chronologie, actifs découverts.

Formats : Markdown → PDF. Le mode `bug_bounty` produit une variante adaptée au format du programme (un finding = un rapport soumissible). Le LLM rédige ; il **ne signe pas**.

## M2 — Scénarios rejouables

Pour chaque finding confirmé, un fichier **YAML** décrivant, étape par étape, comment reproduire l'exploitation : prérequis, requêtes exactes (ou script Foundry pour Web3), conditions de succès. Usage : le client vérifie la correction ; l'équipe rejoue plus tard (régression). C'est la valeur différenciante — pas juste « il y a un bug », mais « voici exactement comment le reproduire, et comment vérifier qu'il est corrigé ».

## M3 — Relecture obligatoire

Le rapport passe **toujours** par une relecture humaine (écran Rapport) avant marquage « livré ». L'agent peut se tromper sur un score, une formulation, une remédiation. La signature engage l'équipe : elle est humaine.

Sortie : rapport relu + scénarios rejouables, findings passés en statut `reported`.

---

## Récapitulatif : où le LLM intervient (et où il n'intervient pas)

| Agent | Le LLM fait | Le LLM ne fait PAS |
|---|---|---|
| RECON | Corréler l'OSINT, lire le JS et hiérarchiser les pistes, générer les dorks, formuler les hypothèses | Décider seul d'élargir le scope ; affirmer un secret vivant sans preuve |
| SCAN | Trier vrais/faux positifs, reconstruire les flux, générer les invariants Web3 | Confirmer une vuln sans artefact ; lancer un scan hors scope |
| EXPLOIT | Proposer des chaînes, construire la requête minimale de preuve | Démarrer sans validation humaine ; pousser un impact destructeur |
| ANALYSE | Proposer le CVSS, argumenter la priorisation, enrichir | Fixer le score final seul |
| REPORT | Rédiger rapport et scénarios | Signer / livrer sans relecture humaine |

Le fil rouge : **le LLM accélère le raisonnement, l'humain garde la décision, et rien n'est un fait sans preuve.** C'est ce qui rend Tegbessou plus performant qu'un agent autonome tout en restant sûr et défendable.

---

*Fin de la spécification des agents. À lire avec le document maître d'implémentation. Toute technique évolue : revalider l'état de l'art (surtout MCP, JS mining et fuzzing Web3) avant chaque phase de développement.*
