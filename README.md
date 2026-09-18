# TEGBESSOU

> Human-in-the-loop Web2/Web3 penetration testing platform — multi-agent
> orchestration where the operator keeps strategy, authorization, and decision.
> Not an autonomous agent: a human validates every phase.

**Authorized use only.** For systems you are explicitly permitted to test
(contractual engagement, bug bounty program, CTF, lab). See `USAGE_POLICY.md`.

## Why this design (and not an autonomous agent)

Autonomous "AI hacker" agents complete only a fraction of real work
unsupervised, hallucinate, and can't be held accountable for scope or
authorization. TEGBESSOU is a **copilot**: it does the heavy lifting (recon,
scanning, correlation, reporting) while a human controls the strategy. This is
what makes it both more useful and legally defensible for authorized work.

By design it enforces: mandatory authorization before any action, scope
validation on every request, and an append-only, tamper-evident audit log.


## Quick start (development)

Each user runs their own local instance; code and methodology are shared via Git.

    cp .env.example .env
    # generate the master key (base64, exactly 44 chars, no comment on the line):
    KEY=$(python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
    sed -i '/^TEGBESSOU_MASTER_KEY=/d' .env && echo "TEGBESSOU_MASTER_KEY=$KEY" >> .env

    pipx install pre-commit && pre-commit install
    make up
    make migrate
    make create-admin
    make test        # must be green

See `docs/ONBOARDING.md` for the full walkthrough and common pitfalls.

## Status

Under active, brick-by-brick implementation (see `docs/ROADMAP.md`).
Foundations (data model + auth + guards) and engagement mechanics are in place.

## License

AGPL-3.0-or-later — see `LICENSE`. Authorized systems only: see `USAGE_POLICY.md`.
