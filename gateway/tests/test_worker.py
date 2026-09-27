"""Tests directs du worker (E1 + E3b + E3 final) : pas de DB, pas de réseau
réel — un script factice tient lieu de binaire subfinder/httpx pour prouver
que `run_subfinder`/`run_httpx` suivent le même modèle (timeout/kill) que
`run_noop`, sans dépendre du binaire réel ni d'une sortie réseau (voir README
pour la preuve réseau réelle, faite en runtime Docker)."""

import asyncio
import sys
import textwrap

import fakeredis.aioredis

from app.worker import run_httpx, run_noop, run_subfinder


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


def _fake_tool_script(tmp_path, stdout: str, sleep_seconds: float = 0.0) -> list[str]:
    """Script Python qui imite l'interface d'un binaire (stdout + exit code),
    sans jamais toucher le réseau — `run_subfinder` n'est ici testé que sur
    son modèle d'exécution (timeout/kill), identique à `run_noop`."""
    script = tmp_path / "fake_subfinder.py"
    script.write_text(
        textwrap.dedent(
            f"""
            import sys, time
            time.sleep({sleep_seconds})
            sys.stdout.write({stdout!r})
            """
        )
    )
    return [sys.executable, str(script)]


async def test_run_subfinder_success(tmp_path) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    ctx = {"redis": redis, "job_id": "job-subfinder-ok"}
    args = _fake_tool_script(tmp_path, '{"host":"api.example.com"}\n')
    result = await run_subfinder(ctx, args, timeout_seconds=5.0)
    assert result["status"] == "done"
    assert result["exit_code"] == 0
    assert "api.example.com" in result["stdout"]
    await redis.aclose()


async def test_run_subfinder_timeout_is_failed(tmp_path) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    ctx = {"redis": redis, "job_id": "job-subfinder-timeout"}
    args = _fake_tool_script(tmp_path, "", sleep_seconds=5.0)
    result = await run_subfinder(ctx, args, timeout_seconds=0.3)
    assert result["status"] == "failed"
    await redis.aclose()


async def test_run_subfinder_cancel_key_is_killed(tmp_path) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    job_id = "job-subfinder-kill"
    ctx = {"redis": redis, "job_id": job_id}
    args = _fake_tool_script(tmp_path, "", sleep_seconds=5.0)

    async def _cancel_soon() -> None:
        await asyncio.sleep(0.2)
        await redis.set(f"job:cancel:{job_id}", "1")

    result, _ = await asyncio.gather(run_subfinder(ctx, args, timeout_seconds=5.0), _cancel_soon())
    assert result["status"] == "killed"
    await redis.aclose()


async def test_run_httpx_success(tmp_path) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    ctx = {"redis": redis, "job_id": "job-httpx-ok"}
    args = _fake_tool_script(tmp_path, '{"url":"https://example.com","status_code":200}\n')
    result = await run_httpx(ctx, args, timeout_seconds=5.0)
    assert result["status"] == "done"
    assert result["exit_code"] == 0
    assert "example.com" in result["stdout"]
    await redis.aclose()


async def test_run_httpx_timeout_is_failed(tmp_path) -> None:
    redis = fakeredis.aioredis.FakeRedis()
    ctx = {"redis": redis, "job_id": "job-httpx-timeout"}
    args = _fake_tool_script(tmp_path, "", sleep_seconds=5.0)
    result = await run_httpx(ctx, args, timeout_seconds=0.3)
    assert result["status"] == "failed"
    await redis.aclose()
