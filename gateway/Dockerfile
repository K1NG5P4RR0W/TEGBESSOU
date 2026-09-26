# Base commune : dépendances Python + code applicatif, PAS d'outil offensif.
# Deux images en découlent (stages `gateway` et `worker`) : même source, mêmes
# dépendances non dupliquées, mais les outils offensifs (subfinder ici,
# httpx/nmap plus tard) ne vivent QUE dans le stage `worker`. La gateway est
# le composant exposé (base + secrets) : elle ne doit contenir aucun binaire
# offensif, même inutilisé.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS base
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml ./
RUN uv sync --no-dev
COPY app ./app
COPY alembic.ini ./
COPY alembic ./alembic
RUN useradd -m appuser && mkdir -p /data/authorizations && chown -R appuser:appuser /app /data

# Stage `gateway` : API exposée. Aucun outil offensif.
FROM base AS gateway
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]

# Stage `worker` : conteneur sandboxé, sans accès DB/secrets, sortie réseau
# uniquement via le sas d'egress (E3a). Seul endroit où vit subfinder.
FROM base AS worker

# subfinder épinglé (pas "latest") + vérification d'intégrité par sha256.
# Sources OSINT autorisées en aval par l'allowlist B du sas d'egress — voir
# egress-gateway/policy/allowlist-osint.conf pour la correspondance
# source -> endpoint, et app/wrappers/subfinder.py pour la liste imposée via
# `-sources`. Installé via un script Python (stdlib seule, pas d'apt/curl/
# unzip supplémentaires) — voir scripts/install_subfinder.py.
ARG SUBFINDER_VERSION=2.16.0
ARG SUBFINDER_SHA256=1b7f9c608e9a5bd59e609a5e09710d63c5485e92d3d49dc2c16eb4fdbe10cb60
ENV SUBFINDER_VERSION=${SUBFINDER_VERSION} SUBFINDER_SHA256=${SUBFINDER_SHA256}

USER root
COPY scripts/install_subfinder.py /tmp/install_subfinder.py
RUN python3 /tmp/install_subfinder.py && rm /tmp/install_subfinder.py

# subfinder v2.16.0 refuse de démarrer si son fichier de configuration des
# flags n'existe PAS (il n'utilise pas silencieusement des valeurs par défaut
# — vérifié à l'exécution). Le rootfs du worker est `read_only` et seul /tmp
# (tmpfs) est inscriptible, donc pas d'écriture persistante possible dans
# $HOME : on bake un fichier vide en lecture seule dans l'image et on le
# pointe explicitement via `-config` (app/wrappers/subfinder.py). Aucune clé,
# aucune donnée — juste un fichier qui doit exister.
COPY subfinder/config.yaml /etc/subfinder/config.yaml

USER appuser
CMD ["arq", "app.worker.WorkerSettings"]
