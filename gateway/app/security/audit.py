"""Journal d'audit inaltérable — chaînage par hash (§13.4).

entry_hash = SHA-256(prev_hash | ts | actor_id | action | target | params)
Chaque entrée dépend de la précédente : toute altération casse la chaîne.
Les appends sont sérialisés par un verrou consultatif PostgreSQL pour éviter
toute course entre écritures concurrentes.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import uuid
from collections.abc import Mapping
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import AuditLog

GENESIS_HASH = "0" * 64
_AUDIT_LOCK_KEY = 0x7E6BAD17  # constante de verrou consultatif dédiée à l'audit


def _canonical(params: Mapping[str, Any] | None) -> str:
    if params is None:
        return ""
    return json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)


def compute_entry_hash(
    prev_hash: str,
    ts: dt.datetime,
    actor_id: uuid.UUID | None,
    action: str,
    target: str | None,
    params: Mapping[str, Any] | None,
) -> str:
    payload = "|".join(
        [
            prev_hash,
            ts.astimezone(dt.UTC).isoformat(),
            str(actor_id) if actor_id else "",
            action,
            target or "",
            _canonical(params),
        ]
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


async def append_audit(
    session: AsyncSession,
    *,
    action: str,
    actor_id: uuid.UUID | None = None,
    engagement_id: uuid.UUID | None = None,
    target: str | None = None,
    params: Mapping[str, Any] | None = None,
) -> AuditLog:
    """Ajoute une entrée à la chaîne. À appeler dans une transaction ouverte."""
    await session.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _AUDIT_LOCK_KEY})
    prev_hash = await session.scalar(
        select(AuditLog.entry_hash).order_by(AuditLog.id.desc()).limit(1)
    )
    prev_hash = prev_hash or GENESIS_HASH
    ts = dt.datetime.now(tz=dt.UTC)
    entry_hash = compute_entry_hash(prev_hash, ts, actor_id, action, target, params)
    row = AuditLog(
        ts=ts,
        actor_id=actor_id,
        engagement_id=engagement_id,
        action=action,
        target=target,
        params_json=dict(params) if params is not None else None,
        prev_hash=prev_hash,
        entry_hash=entry_hash,
    )
    session.add(row)
    await session.flush()
    return row


async def verify_chain(session: AsyncSession) -> bool:
    """Recalcule toute la chaîne et vérifie son intégrité."""
    rows = (await session.scalars(select(AuditLog).order_by(AuditLog.id.asc()))).all()
    expected_prev = GENESIS_HASH
    for row in rows:
        if row.prev_hash != expected_prev:
            return False
        recomputed = compute_entry_hash(
            row.prev_hash, row.ts, row.actor_id, row.action, row.target, row.params_json
        )
        if recomputed != row.entry_hash:
            return False
        expected_prev = row.entry_hash
    return True
