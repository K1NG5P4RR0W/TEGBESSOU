# Security Policy

TEGBESSOU is an offensive security platform. This document covers authorized
use, how to report a vulnerability **in TEGBESSOU itself**, and how we handle
dependency vulnerabilities.

## Authorized use only

TEGBESSOU must only be used against systems you are **explicitly authorized** to
test: a signed engagement (SoW), a bug bounty program within its stated scope, a
declared CTF target, or a lab you control. Any use against a system without
authorization is illegal in most jurisdictions and strictly prohibited. See
`USAGE_POLICY.md`. The authors and contributors accept no liability for illegal
or abusive use (see the "AS IS" clause of the `LICENSE`).

By design, TEGBESSOU enforces mandatory authorization before any action, scope
validation on every request, and an append-only, tamper-evident audit log. Do
not attempt to bypass these safeguards.

## Reporting a vulnerability in TEGBESSOU

If you find a security issue in TEGBESSOU **itself** (not in a target you are
testing), please report it privately:

- **Do not** open a public issue for security-sensitive reports.
- Email: contact@zeromisconfig.tech  *(update with your real contact)*
- Include: affected component, version/commit, impact, and steps to reproduce.

We aim to acknowledge reports promptly and to coordinate a fix and disclosure
timeline with the reporter.

## Secrets and supply chain

- No secret is ever committed. `gitleaks` runs in pre-commit and in CI; the
  `.gitignore` blocks `.env`, `*.key`, `*.pem`, `secrets/`.
- Dependencies are pinned (lockfiles committed) and monitored by Dependabot.
- CI runs security checks (secret scanning) on every push and pull request.
- In case of a leaked secret: revoke it immediately, then clean history.

## Known accepted vulnerabilities

Some dependency alerts are evaluated and knowingly accepted when they have no
real impact on the delivered product. We document them here for transparency.

- **esbuild / vite** (GHSA-67mh-4wv8-2f99, moderate; and its transitive alert)
  — affects only the Vite **development server** (`npm run dev`), which lets a
  website send requests to the local dev server. It has **no impact on
  production builds** and does not run for end users. The available fix requires
  **Vite 8**, a breaking change that currently breaks the dashboard build (caught
  by our CI). Migration to Vite 8 is planned once the ecosystem is stable. These
  Dependabot alerts are dismissed as *"vulnerable code is not actually used"*.

This section is reviewed as dependencies evolve; accepted items are removed once
a non-breaking fix is available.
