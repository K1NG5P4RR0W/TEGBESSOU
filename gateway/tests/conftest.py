import os
import pathlib
import urllib.parse
from collections.abc import AsyncIterator, Iterator

import pgserver
import psycopg
import pytest
import pytest_asyncio
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from alembic import command

GATEWAY_DIR = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def pg_host(tmp_path_factory: pytest.TempPathFactory) -> Iterator[str]:
    """Démarre un PostgreSQL éphémère et applique la migration Alembic."""
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
async def session(pg_host: str) -> AsyncIterator[AsyncSession]:
    engine = create_async_engine(f"postgresql+asyncpg://postgres@/tegbessou_test?host={pg_host}")
    async with engine.begin() as conn:
        await conn.execute(text("TRUNCATE audit_log, engagements, users RESTART IDENTITY CASCADE"))
    maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with maker() as s:
        yield s
    await engine.dispose()
