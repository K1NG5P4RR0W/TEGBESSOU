import base64
import os

# Clé maître de test — définie avant tout import de l'application.
os.environ.setdefault("TEGBESSOU_MASTER_KEY", base64.b64encode(b"0" * 32).decode())

import tempfile  # noqa: E402

os.environ.setdefault("FILE_VAULT_DIR", tempfile.mkdtemp())

import pathlib  # noqa: E402
import urllib.parse  # noqa: E402
from collections.abc import AsyncIterator, Callable, Coroutine, Iterator  # noqa: E402

import fakeredis  # noqa: E402
import pgserver  # noqa: E402
import psycopg  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic.config import Config  # noqa: E402
from arq import worker as arq_worker  # noqa: E402
from arq.connections import ArqRedis  # noqa: E402
from fakeredis.aioredis import FakeAsyncRedisConnection  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from redis.asyncio import ConnectionPool  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command  # noqa: E402

GATEWAY_DIR = pathlib.Path(__file__).resolve().parent.parent

# fakeredis n'implémente pas INFO ; arq l'appelle sans condition au démarrage
# du worker. Neutralisé ici pour les tests uniquement (pure log, pas de logique).
async def _noop_log_redis_info(redis: object, log_func: object) -> None:
    return None


arq_worker.log_redis_info = _noop_log_redis_info  # type: ignore[assignment]


@pytest.fixture(scope="session")
def pg_host(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    data_dir = tmp_path_factory.mktemp("pgdata")
    server = pgserver.get_server(data_dir)
    host = urllib.parse.parse_qs(urllib.parse.urlparse(server.get_uri()).query)["host"][0]
    with psycopg.connect(host=host, dbname="postgres", user="postgres", autocommit=True) as conn:
        conn.execute("CREATE DATABASE tegbessou_test")
    os.environ["ALEMBIC_DATABASE_URL"] = (
        f"postgresql+psycopg://postgres@/tegbessou_test?host={host}"
    )
    command.upgrade(Config(str(GATEWAY_DIR / "alembic.ini")), "head")
    yield host


@pytest_asyncio.fixture
async def engine(pg_host: str) -> AsyncIterator[AsyncEngine]:
    eng = create_async_engine(f"postgresql+asyncpg://postgres@/tegbessou_test?host={pg_host}")
    async with eng.begin() as conn:
        await conn.execute(text("TRUNCATE audit_log, engagements, users RESTART IDENTITY CASCADE"))
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def session(engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s


@pytest.fixture
def fake_redis_server() -> fakeredis.FakeServer:
    """Un seul serveur Redis en mémoire, partagé par l'API et le worker de test."""
    return fakeredis.FakeServer()


def _fake_arq_pool(server: fakeredis.FakeServer) -> ArqRedis:
    pool = ConnectionPool(connection_class=FakeAsyncRedisConnection, server=server)
    return ArqRedis(pool_or_conn=pool)


@pytest_asyncio.fixture
async def arq_pool(fake_redis_server: fakeredis.FakeServer) -> AsyncIterator[ArqRedis]:
    r = _fake_arq_pool(fake_redis_server)
    yield r
    await r.aclose()


@pytest.fixture
def run_worker(
    fake_redis_server: fakeredis.FakeServer,
) -> Callable[[], Coroutine[None, None, None]]:
    """Draine la file arq une fois (burst) — même worker que `app.worker.WorkerSettings`."""
    from app.worker import run_noop

    async def _run() -> None:
        worker_redis = _fake_arq_pool(fake_redis_server)
        w = arq_worker.Worker(
            functions=[run_noop], redis_pool=worker_redis, burst=True, poll_delay=0.05
        )
        await w.async_run()
        await worker_redis.aclose()

    return _run


@pytest_asyncio.fixture
async def client(engine: AsyncEngine, arq_pool: ArqRedis) -> AsyncIterator[AsyncClient]:
    from app.api.deps import get_arq_pool, get_session
    from app.main import app

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override_session() -> AsyncIterator[AsyncSession]:
        async with maker() as s:
            yield s

    async def _override_arq_pool() -> ArqRedis:
        return arq_pool

    app.dependency_overrides[get_session] = _override_session
    app.dependency_overrides[get_arq_pool] = _override_arq_pool
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
