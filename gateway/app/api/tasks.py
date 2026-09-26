"""Plomberie d'exécution (E1) + modules RECON réels (E3b subfinder, E3 final httpx).

E1 : une commande triviale et sûre (`echo`/`id`/`sleep`, args typés) est mise
en file pour le worker arq — aucune cible réseau.
E3b : un job subfinder réel est mis en file pour un engagement ACTIF, cible
validée par le Scope Enforcer (hors scope = 403 + audit). Le worker exécute
subfinder à travers le sas d'egress (allowlist B, E3a) et ne touche jamais la
base ; c'est cette API qui récupère son résultat (poll), parse la sortie
(`SubfinderWrapper`), persiste les sous-domaines découverts comme assets et
journalise. Voir docs/EXECUTION_DESIGN.md (E1) et docs/E3_EGRESS_DESIGN.md (E3b).
E3 final : même patron pour httpx, mais ACTIF (il touche la cible in-scope,
donc l'allowlist A du sas — pas l'allowlist B). Wrapper récupéré via le
registre (`app.wrappers.registry`, E2-3).
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
from app.security.scope import ScopeViolationError, enforce_scope
from app.services.assets import insert_discovered_assets
from app.services.execution import create_queued_task, finalize_task, get_task, mark_task_running
from app.wrappers.httpx import InvalidTargetError as InvalidHttpxTargetError
from app.wrappers.registry import get_wrapper
from app.wrappers.subfinder import InvalidTargetError, SubfinderWrapper

router = APIRouter(prefix="/engagements/{engagement_id}/tasks", tags=["tasks"])

CommandName = Literal["echo", "id", "sleep"]


class NoopTaskIn(BaseModel):
    command: CommandName = "echo"
    message: str = Field(default="tegbessou-e1-noop", max_length=200)
    seconds: int = Field(default=0, ge=0, le=60)
    timeout_seconds: float = Field(default=5.0, gt=0, le=20)


class SubfinderTaskIn(BaseModel):
    target: str = Field(..., min_length=1, max_length=253)
    recursive: bool = False
    timeout_seconds: float = Field(default=60.0, gt=0, le=120)


class HttpxTaskIn(BaseModel):
    target: str = Field(..., min_length=1, max_length=253)
    timeout_seconds: float = Field(default=30.0, gt=0, le=60)


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
    await arq_pool.enqueue_job("run_noop", args, body.timeout_seconds, _job_id=str(task_id))
    return TaskOut(id=str(task_id), tool="noop", target=body.command, status="queued")


@router.post("/subfinder", status_code=status.HTTP_201_CREATED)
async def enqueue_subfinder_task(
    engagement_id: uuid.UUID,
    body: SubfinderTaskIn,
    actor: CurrentUser = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> TaskOut:
    """Met en file un job subfinder réel — passif, sources fixes sans clé
    (voir app/wrappers/subfinder.py), sortie réseau via le sas d'egress."""
    eng = await _get_active_engagement(session, engagement_id)
    try:
        await enforce_scope(
            session, engagement_id=engagement_id, target=body.target, actor_id=actor.id
        )
    except ScopeViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    wrapper = SubfinderWrapper(recursive=body.recursive)
    try:
        args = wrapper.build_args(body.target)
    except InvalidTargetError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    task_id = uuid.uuid4()
    await create_queued_task(
        session,
        eng.schema_name,
        task_id=task_id,
        phase="recon",
        tool="subfinder",
        target=body.target,
        args_json={"args": args, "timeout_seconds": body.timeout_seconds},
    )
    await append_audit(
        session,
        action="task.enqueue",
        actor_id=actor.id,
        engagement_id=engagement_id,
        target=body.target,
        params={"task_id": str(task_id), "tool": "subfinder"},
    )
    await session.commit()
    await arq_pool.enqueue_job("run_subfinder", args, body.timeout_seconds, _job_id=str(task_id))
    return TaskOut(id=str(task_id), tool="subfinder", target=body.target, status="queued")


@router.post("/httpx", status_code=status.HTTP_201_CREATED)
async def enqueue_httpx_task(
    engagement_id: uuid.UUID,
    body: HttpxTaskIn,
    actor: CurrentUser = Depends(require_role("analyst")),
    session: AsyncSession = Depends(get_session),
    arq_pool: ArqRedis = Depends(get_arq_pool),
) -> TaskOut:
    """Met en file un job httpx réel — ACTIF (touche la cible in-scope),
    sortie réseau via le sas d'egress (allowlist A, cible de l'engagement)."""
    eng = await _get_active_engagement(session, engagement_id)
    try:
        await enforce_scope(
            session, engagement_id=engagement_id, target=body.target, actor_id=actor.id
        )
    except ScopeViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc

    wrapper = get_wrapper("httpx")
    try:
        args = wrapper.build_args(body.target)
    except InvalidHttpxTargetError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    task_id = uuid.uuid4()
    await create_queued_task(
        session,
        eng.schema_name,
        task_id=task_id,
        phase="recon",
        tool="httpx",
        target=body.target,
        args_json={"args": args, "timeout_seconds": body.timeout_seconds},
    )
    await append_audit(
        session,
        action="task.enqueue",
        actor_id=actor.id,
        engagement_id=engagement_id,
        target=body.target,
        params={"task_id": str(task_id), "tool": "httpx"},
    )
    await session.commit()
    await arq_pool.enqueue_job("run_httpx", args, body.timeout_seconds, _job_id=str(task_id))
    return TaskOut(id=str(task_id), tool="httpx", target=body.target, status="queued")


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
            job_status = await job.status()
            if row["status"] == "queued" and job_status == JobStatus.in_progress:
                await mark_task_running(session, eng.schema_name, task_id)
                await session.commit()
                row = await _require_task(session, eng.schema_name, task_id)
            elif job_status == JobStatus.not_found:
                # Tâche orpheline : plus de job arq correspondant (le process a
                # pu mourir entre le commit `queued` et l'enqueue arq), et le
                # job n'a jamais tourné (pas de résultat) — jamais coincée
                # indéfiniment, on la clôt en échec.
                result = {"status": "failed", "exit_code": None, "reason": "orphaned"}
                await finalize_task(
                    session, eng.schema_name, task_id, status="failed", result=result
                )
                await append_audit(
                    session,
                    action="task.run",
                    actor_id=actor.id,
                    engagement_id=engagement_id,
                    target=str(row["tool"]),
                    params={"task_id": str(task_id), "status": "failed", "reason": "orphaned"},
                )
                await session.commit()
                row = await _require_task(session, eng.schema_name, task_id)
        else:
            result = info.result if info.success else {"status": "failed", "exit_code": None}
            new_status = str(result.get("status", "failed"))
            if str(row["tool"]) == "subfinder" and new_status == "done":
                parsed = SubfinderWrapper().parse(str(result.get("stdout", "")), str(row["target"]))
                await insert_discovered_assets(
                    session,
                    eng.schema_name,
                    engagement_id=engagement_id,
                    items=parsed.items,
                    discovered_by="subfinder",
                )
            elif str(row["tool"]) == "httpx" and new_status == "done":
                stdout = str(result.get("stdout", ""))
                parsed = get_wrapper("httpx").parse(stdout, str(row["target"]))
                await insert_discovered_assets(
                    session,
                    eng.schema_name,
                    engagement_id=engagement_id,
                    items=parsed.items,
                    discovered_by="httpx",
                )
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
