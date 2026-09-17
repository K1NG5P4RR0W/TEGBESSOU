import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Engagement, User
from app.security import tokens
from app.security.passwords import hash_password
from app.services.engagement_schema import (
    ENGAGEMENT_TABLES,
    InvalidSchemaNameError,
    drop_engagement_schema,
    provision_engagement_schema,
)


async def _tables_in(session: AsyncSession, schema: str) -> set[str]:
    rows = await session.scalars(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema = :s").bindparams(
            s=schema
        )
    )
    return set(rows.all())


async def _schema_exists(session: AsyncSession, schema: str) -> bool:
    val = await session.scalar(
        text("SELECT 1 FROM information_schema.schemata WHERE schema_name = :s").bindparams(
            s=schema
        )
    )
    return val is not None


# ---- tests directs (fonctions de provisionnement) ----


async def test_provision_creates_all_tables(session: AsyncSession) -> None:
    schema = f"eng_{uuid.uuid4().hex}"
    await provision_engagement_schema(session, schema)
    await session.commit()
    assert await _tables_in(session, schema) == set(ENGAGEMENT_TABLES)
    await drop_engagement_schema(session, schema)
    await session.commit()


async def test_two_engagements_are_isolated(session: AsyncSession) -> None:
    a = f"eng_{uuid.uuid4().hex}"
    b = f"eng_{uuid.uuid4().hex}"
    await provision_engagement_schema(session, a)
    await provision_engagement_schema(session, b)
    await session.commit()
    assert await _schema_exists(session, a)
    assert await _schema_exists(session, b)
    # dropper l'un ne touche pas l'autre
    await drop_engagement_schema(session, a)
    await session.commit()
    assert not await _schema_exists(session, a)
    assert await _schema_exists(session, b)
    await drop_engagement_schema(session, b)
    await session.commit()


async def test_invalid_schema_name_rejected(session: AsyncSession) -> None:
    for bad in ("public", "eng_notarealhex", "eng_x; DROP TABLE users", "engagement"):
        with pytest.raises(InvalidSchemaNameError):
            await provision_engagement_schema(session, bad)


# ---- test HTTP (cycle activate -> provision -> close -> purge) ----


async def _seed(session: AsyncSession, role: str) -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("pw"),
        totp_secret=b"\x00",
        role=role,
    )
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def test_activate_provisions_and_purge_drops(
    client: AsyncClient, session: AsyncSession
) -> None:
    lead = await _seed(session, "lead")
    admin = await _seed(session, "admin")
    lead_h = {"Authorization": f"Bearer {tokens.create_access(lead.id, 'lead')}"}
    admin_h = {"Authorization": f"Bearer {tokens.create_access(admin.id, 'admin')}"}

    eid = (
        await client.post("/engagements", headers=lead_h, json={"name": "X", "mode": "ctf"})
    ).json()["id"]
    await client.post(
        f"/engagements/{eid}/authorization",
        headers=lead_h,
        data={"source_kind": "program_url", "program_url": "https://p/rules"},
    )
    act = await client.post(f"/engagements/{eid}/activate", headers=lead_h)
    assert act.status_code == 200

    # le schéma existe et contient ses 6 tables
    schema = await session.scalar(
        select(Engagement.schema_name).where(Engagement.id == uuid.UUID(eid))
    )
    assert schema is not None
    assert await _tables_in(session, schema) == set(ENGAGEMENT_TABLES)

    # purge refusée tant que l'engagement n'est pas clos
    assert (await client.post(f"/engagements/{eid}/purge", headers=admin_h)).status_code == 409
    # purge refusée pour un non-admin même après clôture
    assert (await client.post(f"/engagements/{eid}/close", headers=lead_h)).status_code == 200
    assert (await client.post(f"/engagements/{eid}/purge", headers=lead_h)).status_code == 403
    # purge admin -> schéma supprimé
    assert (await client.post(f"/engagements/{eid}/purge", headers=admin_h)).status_code == 200
    assert not await _schema_exists(session, schema)
