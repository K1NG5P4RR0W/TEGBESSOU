"""Worker arq isolé — E1 : plomberie d'exécution, aucune cible réseau.

Ce worker ne connaît QUE Redis (pas de credentials PostgreSQL, pas de secret).
Il exécute une commande locale triviale et sûre via un tableau d'arguments
typé (jamais `shell=True`), la normalise, et renvoie le résultat à la gateway
via le résultat du job arq. C'est la gateway (voir `app/services/execution.py`)
qui persiste en base et journalise — le worker n'écrit jamais en base.

E2/E3 brancheront ici les vrais wrappers d'outils (subfinder, httpx…) derrière
le même contrat de sortie normalisée.
"""

from __future__ import annotations

import asyncio
import time
from typing import Any

from arq.connections import RedisSettings
from redis.asyncio import Redis

from app.core.config import settings

_CANCEL_POLL_SECONDS = 0.2
_MAX_STDOUT_BYTES = 64 * 1024


def _cancel_key(job_id: str) -> str:
    return f"job:cancel:{job_id}"


async def _watch_cancel(redis: Redis, key: str) -> None:
    """Boucle jusqu'à ce que le kill switch soit posé par la gateway."""
    while True:
        if await redis.get(key):
            return
        await asyncio.sleep(_CANCEL_POLL_SECONDS)


async def run_noop(
    ctx: dict[str, Any], args: list[str], timeout_seconds: float = 5.0
) -> dict[str, Any]:
    """Exécute une commande sûre (args typés) et renvoie un résultat normalisé.

    Résultat : {status, stdout, exit_code, duration_ms}. status ∈
    {done, failed, killed}. Surveille en parallèle le kill switch posé par la
    gateway dans Redis (clé `job:cancel:<job_id>`), sans jamais accéder à la
    base ni au réseau externe.
    """
    redis: Redis = ctx["redis"]
    job_id: str = str(ctx["job_id"])
    key = _cancel_key(job_id)
    start = time.monotonic()

    proc = await asyncio.create_subprocess_exec(
        *args, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT
    )
    comm_task: asyncio.Task[tuple[bytes, bytes | None]] = asyncio.ensure_future(proc.communicate())
    watch_task: asyncio.Task[None] = asyncio.ensure_future(_watch_cancel(redis, key))
    try:
        done, _pending = await asyncio.wait(
            {comm_task, watch_task}, timeout=timeout_seconds, return_when=asyncio.FIRST_COMPLETED
        )
        duration_ms = int((time.monotonic() - start) * 1000)

        if comm_task in done:
            watch_task.cancel()
            stdout_bytes, _ = comm_task.result()
            status = "done" if proc.returncode == 0 else "failed"
            return {
                "status": status,
                "stdout": stdout_bytes[:_MAX_STDOUT_BYTES].decode("utf-8", errors="replace"),
                "exit_code": proc.returncode,
                "duration_ms": duration_ms,
            }

        killed_by_cancel = watch_task in done
        comm_task.cancel()
        watch_task.cancel()
        proc.kill()
        await proc.wait()
        return {
            "status": "killed" if killed_by_cancel else "failed",
            "stdout": "",
            "exit_code": proc.returncode,
            "duration_ms": duration_ms,
        }
    finally:
        await redis.delete(key)


class WorkerSettings:
    functions = (run_noop,)
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 30
    allow_abort_jobs = True
