"""Provisionnement du schéma par engagement (§11, Option A).

Chaque engagement possède son propre schéma PostgreSQL `eng_<uuid>` contenant
ses données sensibles (assets, tasks, findings…). Isolation stricte + suppression
propre en fin de mission. Le DDL est versionné ici (pas dans Alembic, qui reste
responsable du seul schéma `public`).
"""

from __future__ import annotations

import re

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# Version du schéma par engagement (si le DDL évolue, on incrémente + routine de migration).
ENGAGEMENT_SCHEMA_VERSION = "2026.01"

# Un nom de schéma est TOUJOURS de la forme eng_<32 hexa> (généré par nous).
# On le valide avant toute interpolation : un identifiant SQL ne peut pas être
# passé en paramètre lié, donc la validation stricte est la garde anti-injection.
_SCHEMA_RE = re.compile(r"^eng_[0-9a-f]{32}$")


class InvalidSchemaNameError(ValueError):
    pass


def _validate(schema: str) -> str:
    if not _SCHEMA_RE.match(schema):
        raise InvalidSchemaNameError(f"nom de schéma invalide : {schema!r}")
    return schema


def _ddl(schema: str) -> list[str]:
    s = f'"{schema}"'
    return [
        f"CREATE SCHEMA IF NOT EXISTS {s}",
        f"""CREATE TABLE {s}.assets (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind          TEXT NOT NULL,
            value         TEXT NOT NULL,
            metadata      JSONB,
            in_scope      BOOLEAN NOT NULL,
            criticality   NUMERIC NOT NULL DEFAULT 0,
            discovered_by TEXT,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
        f"""CREATE TABLE {s}.asset_edges (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            src_asset  UUID NOT NULL REFERENCES {s}.assets(id) ON DELETE CASCADE,
            dst_asset  UUID NOT NULL REFERENCES {s}.assets(id) ON DELETE CASCADE,
            relation   TEXT NOT NULL,
            confirmed  BOOLEAN NOT NULL DEFAULT true,
            metadata   JSONB,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
        f"""CREATE TABLE {s}.tasks (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            phase       TEXT NOT NULL,
            module_id   TEXT,
            tool        TEXT NOT NULL,
            target      TEXT NOT NULL,
            args_json   JSONB NOT NULL,
            status      TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN ('queued','running','done','failed','killed')),
            output_ref  TEXT,
            started_at  TIMESTAMPTZ,
            finished_at TIMESTAMPTZ
        )""",
        f"""CREATE TABLE {s}.findings (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            title       TEXT NOT NULL,
            vuln_class  TEXT,
            cve         TEXT,
            attack_id   TEXT,
            cvss_vector TEXT,
            cvss_score  NUMERIC,
            severity    TEXT CHECK (severity IN ('info','low','medium','high','critical')),
            status      TEXT NOT NULL DEFAULT 'candidate'
                        CHECK (status IN ('candidate','confirmed','rejected','reported')),
            description TEXT,
            remediation TEXT,
            created_by  TEXT,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
        f"""CREATE TABLE {s}.evidences (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            finding_id  UUID NOT NULL REFERENCES {s}.findings(id) ON DELETE CASCADE,
            kind        TEXT NOT NULL,
            content_ref TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
        f"""CREATE TABLE {s}.replay_scenarios (
            id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            finding_id UUID NOT NULL REFERENCES {s}.findings(id) ON DELETE CASCADE,
            yaml_ref   TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )""",
    ]


# Tables attendues dans un schéma provisionné (sert aux vérifications/tests).
ENGAGEMENT_TABLES = ("assets", "asset_edges", "tasks", "findings", "evidences", "replay_scenarios")


async def provision_engagement_schema(session: AsyncSession, schema_name: str) -> None:
    """Crée le schéma de l'engagement et ses tables. Idempotent sur le schéma."""
    _validate(schema_name)
    for statement in _ddl(schema_name):
        await session.execute(text(statement))


async def drop_engagement_schema(session: AsyncSession, schema_name: str) -> None:
    """Supprime définitivement le schéma de l'engagement (suppression de fin de mission)."""
    _validate(schema_name)
    await session.execute(text(f'DROP SCHEMA IF EXISTS "{schema_name}" CASCADE'))
