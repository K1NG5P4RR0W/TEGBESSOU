#!/usr/bin/env bash
# =====================================================================
# TEGBESSOU — scaffolding du dépôt
# À lancer UNE FOIS à la racine du dépôt fraîchement cloné.
#   chmod +x scaffold.sh && ./scaffold.sh
# Crée l'arborescence (§15 du document), les fichiers de gouvernance,
# les workflows CI et la config pre-commit. Ne contient AUCUN secret.
# =====================================================================
set -euo pipefail

echo "==> Création de l'arborescence…"
mkdir -p \
  .github/workflows \
  docs \
  gateway/app/{core,security,llm,mcp,tools,rag,jobs,proxy,models,api} gateway/tests gateway/alembic \
  api_pentest/app/{auth,ws,devtools_gw,aggregators,api} api_pentest/tests \
  dashboard/src/{pages,components,devtools,api,ws,design-system} \
  cli/tegbessou/commands cli/tests \
  orchestrator/flows orchestrator/modules \
  knowledge_base/ingest \
  deploy/{nginx,ca,worker}

# .gitkeep pour versionner les dossiers vides
find gateway api_pentest dashboard cli orchestrator knowledge_base deploy -type d -empty -exec touch {}/.gitkeep \;

echo "==> Fichiers de gouvernance…"

cat > .gitignore << 'EOF'
# Secrets — NE JAMAIS committer
.env
.env.*
!.env.example
*.key
*.pem
secrets/
/run/secrets/

# Python
__pycache__/
*.py[cod]
.venv/
venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
*.egg-info/

# Node / front
node_modules/
dist/
build/
.vite/

# Divers
.DS_Store
*.log
.idea/
.vscode/
EOF

cat > .env.example << 'EOF'
# ---- Chiffrement ----
TEGBESSOU_MASTER_KEY=            # 32 octets base64 — GÉNÉRER, ne jamais committer
JWT_PRIVATE_KEY_PATH=/run/secrets/jwt_ed25519

# ---- Base de données ----
POSTGRES_HOST=orchestration-host
POSTGRES_DB=tegbessou
POSTGRES_USER=tegbessou_app       # droits restreints (pas de DDL en prod)
POSTGRES_PASSWORD=

# ---- Redis ----
REDIS_URL=redis://orchestration-host:6379/0

# ---- Réseau / TLS ----
PUBLIC_DOMAIN=tegbessou.exemple.tld
GATEWAY_INTERNAL_URL=https://gateway.internal:8443
MTLS_CA_PATH=/run/secrets/internal_ca.pem
PROXY_LISTEN=0.0.0.0:8888         # proxy DevTools (nœud d'exécution)

# ---- LLM (optionnel : sinon saisi au dashboard) ----
# ANTHROPIC_API_KEY=
# OPENAI_API_KEY=
# GOOGLE_API_KEY=
OLLAMA_BASE_URL=http://ollama:11434
EOF

cat > LICENSE << 'EOF'
Copyright (c) 2026 zeromisconfig. Tous droits réservés.

LOGICIEL PROPRIÉTAIRE ET CONFIDENTIEL.

Ce code et la documentation associée sont confidentiels. Toute utilisation,
copie, modification ou distribution sans autorisation écrite préalable est
interdite. Diffusion restreinte aux intervenants sous accord de
confidentialité (NDA).
EOF

cat > README.md << 'EOF'
# TEGBESSOU

> **CONFIDENTIEL — Diffusion restreinte (NDA).** Plateforme d'assistance au
> pentest Web2/Web3 : orchestration multi-agent, *human-in-the-loop*.

Outil réservé à un usage sur des systèmes **explicitement autorisés**
(mission sous contrat, programme de bug bounty, CTF, lab). Voir `SECURITY.md`.

## Documentation

- `docs/IMPLEMENTATION.md` — document d'implémentation complet (architecture, sécurité, déploiement).
- `docs/AGENTS.md` — spécification approfondie des agents et de la méthodologie.

## Démarrage

Voir la section « Installation et déploiement » de `docs/IMPLEMENTATION.md`.
En bref (développement) :

    cp .env.example .env    # renseigner les secrets
    make up
    make migrate
    make seed-kb
    make seed-modules
    make create-admin

## État

Projet en cours d'implémentation par briques (voir feuille de route dans la doc).
EOF

cat > SECURITY.md << 'EOF'
# Politique de sécurité

## Usage autorisé uniquement
TEGBESSOU est un outil offensif. Son usage est strictement limité aux systèmes
pour lesquels une **autorisation explicite** existe (SoW signé, périmètre d'un
programme de bug bounty, machine de CTF, environnement de lab contrôlé). Tout
autre usage est interdit.

## Confidentialité
Le dépôt et la documentation sont confidentiels. Accès réservé aux intervenants
sous NDA. Ne pas rendre public, ne pas forker hors organisation.

## Secrets
Aucun secret ne doit être committé. `gitleaks` s'exécute en pre-commit et en CI.
Le `.gitignore` bloque `.env`, `*.key`, `*.pem`, `secrets/`. En cas de fuite :
révoquer immédiatement le secret, puis nettoyer l'historique.

## Signalement d'une vulnérabilité du produit
Contact : security@exemple.tld  (à renseigner). Ne pas ouvrir d'issue publique.
EOF

cat > CONTRIBUTING.md << 'EOF'
# Contribution

## Branches
- `main` : protégée, toujours déployable. Aucun push direct.
- `feat/<sujet>`, `fix/<sujet>`, `sec/<sujet>` : une branche par tâche.

## Commits
Convention *Conventional Commits* : `feat:`, `fix:`, `sec:`, `docs:`, `chore:`.
Commits signés exigés sur `main`.

## Avant d'ouvrir une PR
- Tests ajoutés et verts
- Aucun secret introduit (gitleaks vert)
- Entrées validées (anti-injection)
- Actions sensibles journalisées
- Scope enforcement respecté si nouvel appel d'outil / nouveau module
- Registre des modules mis à jour si module ajouté/retiré
- Doc `docs/` à jour si contrat d'API modifié

## Discipline
Lire l'état réel avant de concevoir. Une brique prouvée et testée avant la
suivante. Officiellement supporté plutôt que bricolé.
EOF

echo "==> Templates GitHub…"

cat > .github/PULL_REQUEST_TEMPLATE.md << 'EOF'
## Objet
<!-- Que fait cette PR ? Quelle brique / quel module ? -->

## Checklist
- [ ] Tests ajoutés et verts
- [ ] Aucun secret introduit (gitleaks vert)
- [ ] Entrées validées (anti-injection)
- [ ] Actions sensibles journalisées
- [ ] Scope enforcement respecté (si nouvel appel d'outil / module)
- [ ] Registre des modules à jour (si module ajouté/retiré)
- [ ] Documentation `docs/` à jour (si contrat d'API modifié)
EOF

cat > .github/dependabot.yml << 'EOF'
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
  # Décommenter à mesure que le code arrive :
  # - package-ecosystem: "pip"
  #   directory: "/gateway"
  #   schedule: { interval: "weekly" }
  # - package-ecosystem: "npm"
  #   directory: "/dashboard"
  #   schedule: { interval: "weekly" }
EOF

echo "==> Workflows CI…"

cat > .github/workflows/security.yml << 'EOF'
name: security
on:
  push:
  pull_request:

jobs:
  gitleaks:
    name: gitleaks (détection de secrets)
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - name: gitleaks
        uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          # NOTE : si le dépôt passe sous une ORGANISATION, l'action exige une
          # licence gitleaks (gratuite). Ajouter alors :
          # GITLEAKS_LICENSE: ${{ secrets.GITLEAKS_LICENSE }}

  # À activer quand du code sera présent :
  # sast:
  #   runs-on: ubuntu-latest
  #   steps:
  #     - uses: actions/checkout@v4
  #     - name: semgrep
  #       run: pipx run semgrep scan --config auto --error
EOF

cat > .github/workflows/ci.yml << 'EOF'
name: ci
on:
  push:
  pull_request:

jobs:
  lint-test:
    name: lint & tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Squelette CI
        run: echo "CI prête. Ajouter lint/tests à mesure que le code arrive."
      # Python (décommenter quand gateway/ ou api_pentest/ existent) :
      # - uses: actions/setup-python@v5
      #   with: { python-version: "3.12" }
      # - run: pipx install ruff mypy
      # - run: ruff check .
      # - run: pytest
      # Front (décommenter quand dashboard/ existe) :
      # - uses: actions/setup-node@v4
      #   with: { node-version: "20" }
      # - run: cd dashboard && npm ci && npm run lint && npm test
EOF

cat > .github/workflows/release.yml << 'EOF'
name: release
on:
  push:
    tags:
      - "v*"

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Placeholder release
        run: echo "Build + signature + push images vers ghcr.io — à implémenter."
EOF

echo "==> Pre-commit…"

cat > .pre-commit-config.yaml << 'EOF'
repos:
  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.18.4
    hooks:
      - id: gitleaks
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.6.0
    hooks:
      - id: check-added-large-files
      - id: check-merge-conflict
      - id: detect-private-key
      - id: end-of-file-fixer
      - id: trailing-whitespace
EOF

echo "==> Makefile…"

cat > Makefile << 'EOF'
# Raccourcis (les cibles seront étoffées à mesure que le code arrive)
.PHONY: up migrate seed-kb seed-modules create-admin healthcheck lint test

up:            ## Démarre la stack de dev
	docker compose up -d
migrate:       ## Applique les migrations
	@echo "TODO: docker compose run --rm gateway alembic upgrade head"
seed-kb:       ## Ingère la base de connaissances
	@echo "TODO: ingestion RAG"
seed-modules:  ## Charge le registre des modules
	@echo "TODO: seed module_registry"
create-admin:  ## Crée le premier compte admin + MFA
	@echo "TODO: création admin"
healthcheck:   ## Vérifie l'état des composants
	@echo "TODO: DB / Redis / Gateway / mTLS / worker / proxy"
lint:
	@echo "TODO: ruff + eslint"
test:
	@echo "TODO: pytest + tests front"
EOF

cat > docs/README.md << 'EOF'
# Documentation

Déposer ici les deux documents maîtres :
- `IMPLEMENTATION.md`
- `AGENTS.md`
EOF

echo ""
echo "==> Terminé. Arborescence et fichiers créés."
echo "    Pense à copier les deux documents dans docs/ :"
echo "      docs/IMPLEMENTATION.md  et  docs/AGENTS.md"
