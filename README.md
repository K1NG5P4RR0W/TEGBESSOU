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
