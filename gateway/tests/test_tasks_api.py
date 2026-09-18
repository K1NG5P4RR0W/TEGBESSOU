"""Tests d'intégration E1 : enqueue (API) -> worker arq -> collecte -> audit.

Le worker de test (`run_worker`) est le même code que `app.worker.WorkerSettings`,
exécuté en mode burst contre un Redis en mémoire partagé avec l'API (fakeredis).
"""

import asyncio
import uuid
from collections.abc import Callable, Coroutine

from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import User
from app.security import tokens
from app.security.audit import verify_chain
from app.security.passwords import hash_password


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _lead_token(session: AsyncSession) -> str:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("pw"),
        totp_secret=b"\x00",
        role="lead",
    )
    session.add(user)
    await session.flush()
    await session.commit()
    return tokens.create_access(user.id, "lead")


async def _create_active_engagement(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/engagements", headers=_auth(token), json={"name": "E1 box", "mode": "ctf"}
    )
    eid = resp.json()["id"]
    await client.post(
        f"/engagements/{eid}/authorization",
        headers=_auth(token),
        data={"source_kind": "program_url", "program_url": "https://p/rules"},
    )
    act = await client.post(f"/engagements/{eid}/activate", headers=_auth(token))
    assert act.status_code == 200, act.text
    return str(eid)


async def test_enqueue_requires_active_engagement(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _lead_token(session)
    resp = await client.post(
        "/engagements", headers=_auth(token), json={"name": "draft", "mode": "ctf"}
    )
    eid = resp.json()["id"]
    enq = await client.post(
        f"/engagements/{eid}/tasks/noop", headers=_auth(token), json={"command": "echo"}
    )
    assert enq.status_code == 409


async def test_noop_task_full_lifecycle(
    client: AsyncClient,
    session: AsyncSession,
    run_worker: Callable[[], Coroutine[None, None, None]],
) -> None:
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)

    enq = await client.post(
        f"/engagements/{eid}/tasks/noop",
        headers=_auth(token),
        json={"command": "echo", "message": "e1-ok"},
    )
    assert enq.status_code == 201, enq.text
    task = enq.json()
    assert task["status"] == "queued"
    task_id = task["id"]

    await run_worker()

    poll = await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))
    assert poll.status_code == 200
    body = poll.json()
    assert body["status"] == "done"
    assert body["output_ref"] is not None

    schema = await session.scalar(
        text("SELECT schema_name FROM engagements WHERE id = :id"), {"id": uuid.UUID(eid)}
    )
    row = (
        await session.execute(
            text(f'SELECT status, tool, output_ref FROM "{schema}".tasks WHERE id = :id'),  # noqa: S608
            {"id": uuid.UUID(task_id)},
        )
    ).mappings().first()
    assert row is not None
    assert row["status"] == "done"
    assert row["tool"] == "noop"
    assert row["output_ref"] is not None

    assert await verify_chain(session) is True


async def test_noop_task_timeout_marks_failed(
    client: AsyncClient,
    session: AsyncSession,
    run_worker: Callable[[], Coroutine[None, None, None]],
) -> None:
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)

    enq = await client.post(
        f"/engagements/{eid}/tasks/noop",
        headers=_auth(token),
        json={"command": "sleep", "seconds": 5, "timeout_seconds": 0.5},
    )
    assert enq.status_code == 201, enq.text
    task_id = enq.json()["id"]

    await run_worker()

    poll = await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))
    assert poll.json()["status"] == "failed"


async def test_noop_task_kill_switch(
    client: AsyncClient,
    session: AsyncSession,
    run_worker: Callable[[], Coroutine[None, None, None]],
) -> None:
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)

    enq = await client.post(
        f"/engagements/{eid}/tasks/noop",
        headers=_auth(token),
        json={"command": "sleep", "seconds": 5, "timeout_seconds": 10},
    )
    assert enq.status_code == 201, enq.text
    task_id = enq.json()["id"]

    async def _kill_soon() -> None:
        await asyncio.sleep(0.3)
        kill = await client.post(f"/engagements/{eid}/tasks/{task_id}/kill", headers=_auth(token))
        assert kill.status_code == 200, kill.text

    await asyncio.gather(run_worker(), _kill_soon())

    poll = await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))
    assert poll.json()["status"] == "killed"


async def test_kill_already_finished_task_rejected(
    client: AsyncClient,
    session: AsyncSession,
    run_worker: Callable[[], Coroutine[None, None, None]],
) -> None:
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)
    enq = await client.post(
        f"/engagements/{eid}/tasks/noop", headers=_auth(token), json={"command": "id"}
    )
    task_id = enq.json()["id"]
    await run_worker()
    await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))

    kill = await client.post(f"/engagements/{eid}/tasks/{task_id}/kill", headers=_auth(token))
    assert kill.status_code == 409


async def test_worker_imports_no_database_driver() -> None:
    """L'ancrage sécurité de E1 : le worker n'importe aucun driver PostgreSQL —
    seul Redis lui est nécessaire, la persistance reste du ressort de la gateway."""
    import ast

    import app.worker as worker_module

    source = worker_module.__file__
    assert source is not None
    with open(source, encoding="utf-8") as f:
        tree = ast.parse(f.read())

    imported_roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_roots.add(node.module.split(".")[0])

    assert imported_roots.isdisjoint({"asyncpg", "psycopg", "sqlalchemy"})
