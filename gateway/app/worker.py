"""Worker arq isolé — E1 (plomberie) + E3b (subfinder réel) + E3 final (httpx réel).

Ce worker ne connaît QUE Redis (pas de credentials PostgreSQL, pas de secret).
Il exécute une commande via un tableau d'arguments typé (jamais `shell=True`),
la normalise, et renvoie le résultat à la gateway via le résultat du job arq.
C'est la gateway (voir `app/services/execution.py`) qui persiste en base et
journalise — le worker n'écrit jamais en base.

`run_noop` (E1) n'ouvre aucun réseau externe. `run_subfinder` (E3b, passif) et
`run_httpx` (E3 final, actif) sortent réellement vers le réseau — via le sas
d'egress (E3a), jamais en direct (le worker n'a aucune route Internet
directe) : subfinder par l'allowlist B (sources OSINT), httpx par l'allowlist
A (cible in-scope de l'engagement). Les trois tâches partagent le même modèle
d'exécution (`_run_subprocess`) : timeout + kill switch identiques.
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


async def _run_subprocess(
    ctx: dict[str, Any], args: list[str], timeout_seconds: float
) -> dict[str, Any]:
    """Exécute une commande (args typés) et renvoie un résultat normalisé.

    Résultat : {status, stdout, exit_code, duration_ms}. status ∈
    {done, failed, killed}. Surveille en parallèle le kill switch posé par la
    gateway dans Redis (clé `job:cancel:<job_id>`). Ne touche jamais la base ;
    le réseau éventuellement ouvert par `args` passe par le sas d'egress (E3a),
    jamais en direct — le worker n'a aucune route Internet propre.
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


async def run_noop(
    ctx: dict[str, Any], args: list[str], timeout_seconds: float = 5.0
) -> dict[str, Any]:
    """E1 : commande locale triviale et sûre, aucun réseau externe."""
    return await _run_subprocess(ctx, args, timeout_seconds)


async def run_subfinder(
    ctx: dict[str, Any], args: list[str], timeout_seconds: float = 60.0
) -> dict[str, Any]:
    """E3b : exécute la commande produite par `SubfinderWrapper.build_args`.

    Même modèle que `run_noop` (timeout + kill switch). La sortie brute
    (JSON lines) est renvoyée telle quelle ; c'est la gateway qui la parse
    (`SubfinderWrapper.parse`) et persiste les sous-domaines découverts.
    """
    return await _run_subprocess(ctx, args, timeout_seconds)


async def run_httpx(
    ctx: dict[str, Any], args: list[str], timeout_seconds: float = 60.0
) -> dict[str, Any]:
    """E3 final : exécute la commande produite par `HttpxWrapper.build_args`.

    httpx est du trafic ACTIF : il touche la cible in-scope de l'engagement,
    contrairement à subfinder (passif). Même modèle que `run_noop`/
    `run_subfinder` (timeout + kill switch) ; la sortie brute (JSON lines) est
    renvoyée telle quelle, c'est la gateway qui la parse (`HttpxWrapper.parse`)
    et persiste les hôtes vivants.
    """
    return await _run_subprocess(ctx, args, timeout_seconds)


class WorkerSettings:
    functions = (run_noop, run_subfinder, run_httpx)
    redis_settings = RedisSettings.from_dsn(settings.redis_url)
    max_jobs = 4
    job_timeout = 90
    allow_abort_jobs = True
