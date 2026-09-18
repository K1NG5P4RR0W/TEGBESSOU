"""Tests directs du worker (E1) : pas de DB, pas de cible réseau, juste des
commandes locales triviales via `app.worker.run_noop`."""

import asyncio

import fakeredis.aioredis

from app.worker import run_noop


async def test_run_noop_success() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    ctx = {"redis": redis, "job_id": "job-ok"}
    result = await run_noop(ctx, ["/bin/echo", "hello-e1"], timeout_seconds=5.0)
    assert result["status"] == "done"
    assert result["exit_code"] == 0
    assert "hello-e1" in result["stdout"]
    await redis.aclose()


async def test_run_noop_nonzero_exit_is_failed() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    ctx = {"redis": redis, "job_id": "job-fail"}
    result = await run_noop(ctx, ["/bin/false"], timeout_seconds=5.0)
    assert result["status"] == "failed"
    assert result["exit_code"] != 0
    await redis.aclose()


async def test_run_noop_timeout_is_failed() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    ctx = {"redis": redis, "job_id": "job-timeout"}
    result = await run_noop(ctx, ["/bin/sleep", "5"], timeout_seconds=0.3)
    assert result["status"] == "failed"
    await redis.aclose()


async def test_run_noop_cancel_key_is_killed() -> None:
    redis = fakeredis.aioredis.FakeRedis()
    job_id = "job-kill"
    ctx = {"redis": redis, "job_id": job_id}

    async def _cancel_soon() -> None:
        await asyncio.sleep(0.2)
        await redis.set(f"job:cancel:{job_id}", "1")

    result, _ = await asyncio.gather(
        run_noop(ctx, ["/bin/sleep", "5"], timeout_seconds=5.0), _cancel_soon()
    )
    assert result["status"] == "killed"
    # le kill switch est nettoyé après usage
    assert await redis.get(f"job:cancel:{job_id}") is None
    await redis.aclose()
