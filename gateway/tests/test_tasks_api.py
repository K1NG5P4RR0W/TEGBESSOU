"""Tests d'intégration E1 + E3b : enqueue (API) -> worker arq -> collecte -> audit.

Le worker de test (`run_worker`, ou un `arq_worker.Worker` construit ad hoc
pour subfinder) exécute le même contrat que `app.worker.WorkerSettings`, en
mode burst contre un Redis en mémoire partagé avec l'API (fakeredis).
"""

import asyncio
import uuid
from collections.abc import Callable, Coroutine

from arq import worker as arq_worker
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import User
from app.security import tokens
from app.security.audit import append_audit, verify_chain
from app.security.passwords import hash_password
from app.services.execution import create_queued_task
from tests.conftest import _fake_arq_pool


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def run_subfinder(
    ctx: dict[str, object], args: list[str], timeout_seconds: float = 60.0
) -> dict[str, object]:
    """Remplace le binaire réel dans les tests : sortie subfinder d'exemple,
    jamais de réseau. Doit rester une fonction de MODULE : arq enregistre le
    job sous ce nom (`enqueue_job("run_subfinder", ...)`), et une closure
    imbriquée dans une fonction de test n'est pas résolue correctement."""
    return {
        "status": "done",
        "stdout": (
            '{"host":"api.example.com","source":"hackertarget"}\n'
            '{"host":"mail.example.com","source":"rapiddns"}\n'
        ),
        "exit_code": 0,
        "duration_ms": 1,
    }


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
        (
            await session.execute(
                text(f'SELECT status, tool, output_ref FROM "{schema}".tasks WHERE id = :id'),  # noqa: S608
                {"id": uuid.UUID(task_id)},
            )
        )
        .mappings()
        .first()
    )
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


async def _add_scope(
    client: AsyncClient, token: str, eid: str, *, kind: str, value: str, disposition: str
) -> None:
    resp = await client.post(
        f"/engagements/{eid}/scope",
        headers=_auth(token),
        json={"kind": kind, "value": value, "disposition": disposition},
    )
    assert resp.status_code == 201, resp.text


async def test_subfinder_enqueue_out_of_scope_is_403_and_audited(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)
    # Aucune règle in_scope pour ce domaine : default deny.
    enq = await client.post(
        f"/engagements/{eid}/tasks/subfinder",
        headers=_auth(token),
        json={"target": "hors-scope.example"},
    )
    assert enq.status_code == 403

    assert await verify_chain(session) is True
    row = (
        (
            await session.execute(
                text(
                    "SELECT action, target FROM audit_log "
                    "WHERE engagement_id = :eid AND action = 'scope.violation' "
                    "ORDER BY ts DESC LIMIT 1"
                ),
                {"eid": uuid.UUID(eid)},
            )
        )
        .mappings()
        .first()
    )
    assert row is not None
    assert row["target"] == "hors-scope.example"


async def test_subfinder_task_persists_discovered_assets(
    client: AsyncClient,
    session: AsyncSession,
    fake_redis_server: object,
) -> None:
    """Parsing + persistance (E3b), testables hors réseau (docs/E3_EGRESS_DESIGN.md
    §9) : le job arq est ici une sortie subfinder d'exemple, jamais le binaire
    réel ni un accès réseau — la preuve réseau réelle (sas/allowlist B) se fait
    en runtime Docker (voir egress-gateway/README.md et la PR)."""
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)
    await _add_scope(client, token, eid, kind="domain", value="example.com", disposition="in_scope")

    enq = await client.post(
        f"/engagements/{eid}/tasks/subfinder",
        headers=_auth(token),
        json={"target": "example.com"},
    )
    assert enq.status_code == 201, enq.text
    task_id = enq.json()["id"]

    worker_redis = _fake_arq_pool(fake_redis_server)
    w = arq_worker.Worker(
        functions=[run_subfinder], redis_pool=worker_redis, burst=True, poll_delay=0.05
    )
    await w.async_run()
    await worker_redis.aclose()

    poll = await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))
    assert poll.status_code == 200
    assert poll.json()["status"] == "done"

    schema = await session.scalar(
        text("SELECT schema_name FROM engagements WHERE id = :id"), {"id": uuid.UUID(eid)}
    )
    rows = (
        (
            await session.execute(
                text(f'SELECT value, kind, discovered_by, in_scope FROM "{schema}".assets'),  # noqa: S608
            )
        )
        .mappings()
        .all()
    )
    values = {r["value"] for r in rows}
    assert values == {"api.example.com", "mail.example.com"}
    for r in rows:
        assert r["kind"] == "subdomain"
        assert r["discovered_by"] == "subfinder"
        assert r["in_scope"] is True


async def test_orphaned_queued_task_marked_failed_on_poll(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Simule le crash visé par les 2 anciens TODO(E3) : la ligne `tasks` est
    commitée `queued` mais AUCUN job arq n'est jamais mis en file (process mort
    entre le commit et l'enqueue). Le poll doit détecter l'absence de job
    (`JobStatus.not_found`) et clore la tâche en échec plutôt que la laisser
    coincée indéfiniment."""
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)
    schema = await session.scalar(
        text("SELECT schema_name FROM engagements WHERE id = :id"), {"id": uuid.UUID(eid)}
    )
    task_id = uuid.uuid4()
    await create_queued_task(
        session,
        schema,
        task_id=task_id,
        phase="recon",
        tool="noop",
        target="echo",
        args_json={"args": ["/bin/echo", "orphan"], "timeout_seconds": 5.0},
    )
    await append_audit(
        session,
        action="task.enqueue",
        engagement_id=uuid.UUID(eid),
        target="echo",
        params={"task_id": str(task_id)},
    )
    await session.commit()
    # Volontairement : aucun arq_pool.enqueue_job ici — c'est exactement le
    # trou laissé par les TODO(E3).

    poll = await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))
    assert poll.status_code == 200
    assert poll.json()["status"] == "failed"

    row = (
        (
            await session.execute(
                text(
                    "SELECT action, params_json FROM audit_log "
                    "WHERE engagement_id = :eid AND action = 'task.run' "
                    "ORDER BY ts DESC LIMIT 1"
                ),
                {"eid": uuid.UUID(eid)},
            )
        )
        .mappings()
        .first()
    )
    assert row is not None
    assert row["params_json"]["reason"] == "orphaned"
    assert row["params_json"]["status"] == "failed"

    assert await verify_chain(session) is True


async def test_queued_task_still_in_flight_is_not_marked_failed(
    client: AsyncClient, session: AsyncSession
) -> None:
    """Contre-épreuve : un job réellement en file (pas encore consommé par un
    worker) ne doit jamais être confondu avec une tâche orpheline."""
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)

    enq = await client.post(
        f"/engagements/{eid}/tasks/noop",
        headers=_auth(token),
        json={"command": "sleep", "seconds": 1},
    )
    assert enq.status_code == 201, enq.text
    task_id = enq.json()["id"]

    # Pas de run_worker() ici : le job existe dans la file mais n'a pas encore
    # été ramassé par un worker.
    poll = await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))
    assert poll.status_code == 200
    assert poll.json()["status"] == "queued"

    assert await verify_chain(session) is True


async def run_httpx(
    ctx: dict[str, object], args: list[str], timeout_seconds: float = 30.0
) -> dict[str, object]:
    """Remplace le binaire réel dans les tests : sortie httpx d'exemple, jamais
    de réseau. Fonction de MODULE (arq enregistre le job sous ce nom)."""
    return {
        "status": "done",
        "stdout": (
            '{"url":"https://example.com","host":"example.com","status_code":200,'
            '"title":"Example Domain","webserver":"ECS"}\n'
        ),
        "exit_code": 0,
        "duration_ms": 1,
    }


async def test_httpx_enqueue_out_of_scope_is_403_and_audited(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)
    # Aucune règle in_scope pour cet hôte : default deny.
    enq = await client.post(
        f"/engagements/{eid}/tasks/httpx",
        headers=_auth(token),
        json={"target": "hors-scope.example"},
    )
    assert enq.status_code == 403

    assert await verify_chain(session) is True
    row = (
        (
            await session.execute(
                text(
                    "SELECT action, target FROM audit_log "
                    "WHERE engagement_id = :eid AND action = 'scope.violation' "
                    "ORDER BY ts DESC LIMIT 1"
                ),
                {"eid": uuid.UUID(eid)},
            )
        )
        .mappings()
        .first()
    )
    assert row is not None
    assert row["target"] == "hors-scope.example"


async def test_httpx_task_persists_discovered_assets(
    client: AsyncClient,
    session: AsyncSession,
    fake_redis_server: object,
) -> None:
    """Parsing + persistance (E3 final), testables hors réseau : le job arq
    est ici une sortie httpx d'exemple, jamais le binaire réel ni un accès
    réseau — la preuve réseau réelle (sas/allowlist A) se fait en runtime
    Docker (voir egress-gateway/README.md et la PR)."""
    token = await _lead_token(session)
    eid = await _create_active_engagement(client, token)
    await _add_scope(client, token, eid, kind="domain", value="example.com", disposition="in_scope")

    enq = await client.post(
        f"/engagements/{eid}/tasks/httpx",
        headers=_auth(token),
        json={"target": "example.com"},
    )
    assert enq.status_code == 201, enq.text
    task_id = enq.json()["id"]

    worker_redis = _fake_arq_pool(fake_redis_server)
    w = arq_worker.Worker(
        functions=[run_httpx], redis_pool=worker_redis, burst=True, poll_delay=0.05
    )
    await w.async_run()
    await worker_redis.aclose()

    poll = await client.get(f"/engagements/{eid}/tasks/{task_id}", headers=_auth(token))
    assert poll.status_code == 200
    assert poll.json()["status"] == "done"

    schema = await session.scalar(
        text("SELECT schema_name FROM engagements WHERE id = :id"), {"id": uuid.UUID(eid)}
    )
    rows = (
        (
            await session.execute(
                text(f'SELECT value, kind, discovered_by, in_scope FROM "{schema}".assets'),  # noqa: S608
            )
        )
        .mappings()
        .all()
    )
    assert len(rows) == 1
    row = rows[0]
    assert row["value"] == "https://example.com"
    assert row["kind"] == "host"
    assert row["discovered_by"] == "httpx"
    assert row["in_scope"] is True

    assert await verify_chain(session) is True


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
