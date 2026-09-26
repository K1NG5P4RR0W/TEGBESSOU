"""Persistance des actifs découverts par les outils de recon (E3b).

Le worker ne persiste jamais rien (inchangé depuis E1) : c'est la gateway qui,
après collecte du résultat normalisé (`ToolWrapper.parse`), écrit les actifs
dans le schéma `eng_<uuid>` de l'engagement. Voir docs/E3_EGRESS_DESIGN.md §7.

Comme `execution.py`, le nom de schéma est validé avant toute interpolation
SQL. On évalue `in_scope` avec la logique pure du Scope Enforcer
(`scope.evaluate`) à titre INFORMATIF : une découverte passive peut
légitimement remonter des actifs hors périmètre (ex. un sous-domaine d'une
maison mère non incluse) — on ne lève jamais `ScopeViolationError` ni
n'audite de violation ici, on marque juste l'actif. C'est `enforce_scope` seul
qui reste la barrière appliquée avant toute action offensive.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Sequence

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import ScopeEntry
from app.security.scope import ScopeRule, evaluate
from app.services.engagement_schema import validate_schema_name
from app.wrappers.base import WrapperItem

_SELECT_EXISTING_VALUES = (
    'SELECT value FROM "{s}".assets WHERE kind = :kind AND value = ANY(:values)'
)
_INSERT_ASSET = (
    'INSERT INTO "{s}".assets (kind, value, metadata, in_scope, discovered_by) '
    "VALUES (:kind, :value, CAST(:metadata AS JSONB), :in_scope, :discovered_by)"
)


def _select_existing_query(s: str) -> str:
    return _SELECT_EXISTING_VALUES.format(s=s)  # noqa: S608


def _insert_query(s: str) -> str:
    return _INSERT_ASSET.format(s=s)  # noqa: S608


async def _load_scope_rules(session: AsyncSession, engagement_id: uuid.UUID) -> list[ScopeRule]:
    rows = (
        await session.scalars(select(ScopeEntry).where(ScopeEntry.engagement_id == engagement_id))
    ).all()
    return [
        ScopeRule(kind=r.kind, value=r.value, disposition=r.disposition, chain=r.chain)
        for r in rows
    ]


async def insert_discovered_assets(
    session: AsyncSession,
    schema_name: str,
    *,
    engagement_id: uuid.UUID,
    items: Sequence[WrapperItem],
    discovered_by: str,
) -> int:
    """Insère les actifs découverts, dédupliqués par (kind, value) déjà
    présente dans le schéma. Renvoie le nombre d'actifs réellement insérés."""
    if not items:
        return 0
    s = validate_schema_name(schema_name)
    rules = await _load_scope_rules(session, engagement_id)

    by_kind: dict[str, list[WrapperItem]] = {}
    for item in items:
        by_kind.setdefault(item.kind, []).append(item)

    inserted = 0
    for kind, kind_items in by_kind.items():
        values = [item.value for item in kind_items]
        existing_rows = await session.execute(
            text(_select_existing_query(s)), {"kind": kind, "values": values}
        )
        existing = set(existing_rows.scalars().all())
        for item in kind_items:
            if item.value in existing:
                continue
            decision = evaluate(item.value, rules)
            await session.execute(
                text(_insert_query(s)),
                {
                    "kind": item.kind,
                    "value": item.value,
                    "metadata": json.dumps(item.metadata),
                    "in_scope": decision.allowed,
                    "discovered_by": discovered_by,
                },
            )
            existing.add(item.value)
            inserted += 1
    return inserted
