import base64
import os

# Clé maître de test — définie avant tout import de l'application.
os.environ.setdefault("TEGBESSOU_MASTER_KEY", base64.b64encode(b"0" * 32).decode())

import tempfile  # noqa: E402

os.environ.setdefault("FILE_VAULT_DIR", tempfile.mkdtemp())

import pathlib  # noqa: E402
import urllib.parse  # noqa: E402
from collections.abc import AsyncIterator, Iterator  # noqa: E402

import pgserver  # noqa: E402
import psycopg  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from alembic.config import Config  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from alembic import command  # noqa: E402

GATEWAY_DIR = pathlib.Path(__file__).resolve().parent.parent


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


@pytest_asyncio.fixture
async def client(engine: AsyncEngine) -> AsyncIterator[AsyncClient]:
    from app.api.deps import get_session
    from app.main import app

    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)

    async def _override() -> AsyncIterator[AsyncSession]:
        async with maker() as s:
            yield s

    app.dependency_overrides[get_session] = _override
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c
    app.dependency_overrides.clear()
