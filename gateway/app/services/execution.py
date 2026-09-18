"""Persistance des tâches d'exécution (E1) — écriture réservée à la gateway.

Le worker arq (`app/worker.py`) n'a jamais accès à PostgreSQL : il exécute,
normalise, renvoie son résultat via Redis. C'est ici que la gateway lit ce
résultat et écrit la ligne `eng_<uuid>.tasks` correspondante + l'audit
(`task.run`, dans `app/api/tasks.py`). Voir docs/EXECUTION_DESIGN.md.

Comme `engagement_schema.py`, le nom de schéma est validé (regex `eng_<hex>`,
seule forme possible car généré par nous) avant toute interpolation dans le
SQL — un identifiant de schéma ne peut pas être passé en paramètre lié.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import filevault
from app.services.engagement_schema import validate_schema_name

_INSERT_TASK = (
    'INSERT INTO "{s}".tasks (id, phase, tool, target, args_json, status) '
    "VALUES (:id, :phase, :tool, :target, CAST(:args_json AS JSONB), 'queued')"
)
_MARK_RUNNING = "UPDATE \"{s}\".tasks SET status = 'running', started_at = now() WHERE id = :id"
_SELECT_TASK = (
    "SELECT id, phase, tool, target, status, output_ref, started_at, finished_at "
    'FROM "{s}".tasks WHERE id = :id'
)
_FINALIZE_TASK = (
    'UPDATE "{s}".tasks SET status = :status, output_ref = :output_ref, '
    "finished_at = now() WHERE id = :id"
)


def _insert_query(s: str) -> str:
    # s est déjà passé par validate_schema_name() (regex eng_<hex>) : pas d'entrée
    # utilisateur interpolée dans le SQL, seuls les :params le sont.
    return _INSERT_TASK.format(s=s)  # noqa: S608


def _mark_running_query(s: str) -> str:
    return _MARK_RUNNING.format(s=s)  # noqa: S608


def _select_query(s: str) -> str:
    return _SELECT_TASK.format(s=s)  # noqa: S608


def _finalize_query(s: str) -> str:
    return _FINALIZE_TASK.format(s=s)  # noqa: S608


async def create_queued_task(
    session: AsyncSession,
    schema_name: str,
    *,
    task_id: uuid.UUID,
    phase: str,
    tool: str,
    target: str,
    args_json: dict[str, Any],
) -> None:
    """Insère la ligne de tâche en statut `queued`, avant l'enqueue arq."""
    s = validate_schema_name(schema_name)
    await session.execute(
        text(_insert_query(s)),
        {
            "id": task_id,
            "phase": phase,
            "tool": tool,
            "target": target,
            "args_json": json.dumps(args_json),
        },
    )


async def mark_task_running(session: AsyncSession, schema_name: str, task_id: uuid.UUID) -> None:
    s = validate_schema_name(schema_name)
    await session.execute(text(_mark_running_query(s)), {"id": task_id})


async def get_task(
    session: AsyncSession, schema_name: str, task_id: uuid.UUID
) -> dict[str, Any] | None:
    s = validate_schema_name(schema_name)
    row = (await session.execute(text(_select_query(s)), {"id": task_id})).mappings().first()
    return dict(row) if row is not None else None


async def finalize_task(
    session: AsyncSession,
    schema_name: str,
    task_id: uuid.UUID,
    *,
    status: str,
    result: dict[str, Any],
) -> str:
    """Persiste le résultat normalisé (chiffré dans le coffre) et clôt la tâche.

    Renvoie la référence de stockage (`output_ref`). Jamais de dump brut en base :
    seule la référence chiffrée y est écrite.
    """
    if status not in ("done", "failed", "killed"):
        raise ValueError(f"statut de tâche invalide : {status!r}")
    s = validate_schema_name(schema_name)
    output_ref = filevault.store(json.dumps(result).encode("utf-8"))
    await session.execute(
        text(_finalize_query(s)),
        {"status": status, "output_ref": output_ref, "id": task_id},
    )
    return output_ref
