"""Plomberie d'exécution (E1) : enqueue → worker isolé → collecte → audit.

Aucune cible réseau ici : seule une commande triviale et sûre (`echo`/`id`/
`sleep`, args typés) est mise en file pour le worker arq. Le worker ne touche
pas la base ; c'est cette API qui récupère son résultat (poll), persiste la
ligne `tasks` et journalise. Voir docs/EXECUTION_DESIGN.md (E1).
"""

from __future__ import annotations

import uuid
from typing import Literal

from arq.connections import ArqRedis
from arq.jobs import Job, JobStatus
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_arq_pool, get_current_user, get_session, require_role
from app.models.tables import Engagement
from app.security.audit import append_audit
from app.services.execution import create_queued_task, finalize_task, get_task, mark_task_running

router = APIRouter(prefix="/engagements/{engagement_id}/tasks", tags=["tasks"])

CommandName = Literal["echo", "id", "sleep"]


class NoopTaskIn(BaseModel):
    command: CommandName = "echo"
    message: str = Field(default="tegbessou-e1-noop", max_length=200)
    seconds: int = Field(default=0, ge=0, le=60)
    timeout_seconds: float = Field(default=5.0, gt=0, le=20)


class TaskOut(BaseModel):
    id: str
    tool: str
    target: str
    status: str
    output_ref: str | None = None


def _build_args(body: NoopTaskIn) -> list[str]:
    """Tableau d'arguments typé — jamais de shell, jamais d'interpolation libre."""
    if body.command == "echo":
        return ["/bin/echo", body.message]
    if body.command == "id":
        return ["/usr/bin/id"]
    return ["/bin/sleep", str(body.seconds)]


async def _get_engagement(session: AsyncSession, engagement_id: uuid.UUID) -> Engagement:
    eng = await session.get(Engagement, engagement_id)
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement introuvable")
    return eng


async def _get_active_engagement(session: AsyncSession, engagement_id: uuid.UUID) -> Engagement:
    eng = await _get_engagement(session, engagement_id)
    if eng.status != "active":
        raise HTTPException(status_code=409, detail="engagement non actif")
    return eng


async def _require_task(
    session: AsyncSession, schema_name: str, task_id: uuid.UUID
) -> dict[str, object]:
    row = await get_task(session, schema_name, task_id)
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="tâche introuvable")
    return row


def _task_out(row: dict[str, object]) -> TaskOut:
    return TaskOut(
        id=str(row["id"]),
        tool=str(row["tool"]),
        target=str(row["target"]),
        status=str(row["status"]),
        output_ref=row["output_ref"] if row["output_ref"] is None else str(row["output_ref"]),
    )


@router.post("/noop", status_code=status.HTTP_201_CREATED)
async def enqueue_noop_task(
    engagement_id: uuid.UUID,
    body: NoopTaskIn,
    actor: CurrentUser = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> TaskOut:
    eng = await _get_active_engagement(session, engagement_id)
    args = _build_args(body)
    task_id = uuid.uuid4()
    await create_queued_task(
        session,
        eng.schema_name,
        task_id=task_id,
        phase="recon",
        tool="noop",
        target=body.command,
        args_json={"args": args, "timeout_seconds": body.timeout_seconds},
    )
    await append_audit(
        session,
        action="task.enqueue",
        actor_id=actor.id,
        engagement_id=engagement_id,
        target=body.command,
        params={"task_id": str(task_id)},
    )
    await session.commit()
    # TODO(E3): réconcilier les tâches orphelines (ligne `queued` sans job arq)
    # si le process meurt entre le commit et l’enqueue — balayage à ajouter.
    await arq_pool.enqueue_job("run_noop", args, body.timeout_seconds, _job_id=str(task_id))
    return TaskOut(id=str(task_id), tool="noop", target=body.command, status="queued")


@router.get("/{task_id}")
async def get_task_status(
    engagement_id: uuid.UUID,
    task_id: uuid.UUID,
    actor: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> TaskOut:
    """Poll : si le job arq est terminé, persiste le résultat et journalise `task.run`."""
    eng = await _get_engagement(session, engagement_id)
    row = await _require_task(session, eng.schema_name, task_id)

    if row["status"] in ("queued", "running"):
        job = Job(str(task_id), arq_pool)
        info = await job.result_info()
        if info is None:
            if row["status"] == "queued" and await job.status() == JobStatus.in_progress:
                await mark_task_running(session, eng.schema_name, task_id)
                await session.commit()
                row = await _require_task(session, eng.schema_name, task_id)
        else:
            result = info.result if info.success else {"status": "failed", "exit_code": None}
            new_status = str(result.get("status", "failed"))
            await finalize_task(session, eng.schema_name, task_id, status=new_status, result=result)
            await append_audit(
                session,
                action="task.run",
                actor_id=actor.id,
                engagement_id=engagement_id,
                target=str(row["tool"]),
                params={
                    "task_id": str(task_id),
                    "status": new_status,
                    "exit_code": result.get("exit_code"),
                },
            )
            await session.commit()
            row = await _require_task(session, eng.schema_name, task_id)

    return _task_out(row)


@router.post("/{task_id}/kill")
async def kill_task(
    engagement_id: uuid.UUID,
    task_id: uuid.UUID,
    actor: CurrentUser = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> dict[str, str]:
    """Kill switch : pose le flag que le worker surveille pendant l'exécution."""
    eng = await _get_engagement(session, engagement_id)
    row = await _require_task(session, eng.schema_name, task_id)
    if row["status"] not in ("queued", "running"):
        raise HTTPException(status_code=409, detail="tâche déjà terminée")
    await arq_pool.set(f"job:cancel:{task_id}", "1", ex=3600)
    await append_audit(
        session,
        action="task.kill",
        actor_id=actor.id,
        engagement_id=engagement_id,
        target=str(row["tool"]),
        params={"task_id": str(task_id)},
    )
    await session.commit()
    return {"status": "kill_requested"}
