import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Engagement, User
from app.security.audit import GENESIS_HASH, append_audit, verify_chain


async def _seed(session: AsyncSession) -> tuple[User, Engagement]:
    user = User(email=f"{uuid.uuid4()}@t.test", password_hash="x", totp_secret=b"\x00", role="lead")
    session.add(user)
    await session.flush()
    eng = Engagement(
        name="CTF", mode="ctf", schema_name=f"eng_{uuid.uuid4().hex[:8]}", owner_id=user.id
    )
    session.add(eng)
    await session.flush()
    return user, eng


async def test_chain_links_and_verifies(session: AsyncSession) -> None:
    user, eng = await _seed(session)
    r1 = await append_audit(session, action="a1", actor_id=user.id, engagement_id=eng.id)
    r2 = await append_audit(
        session, action="a2", actor_id=user.id, engagement_id=eng.id, params={"k": "v"}
    )
    await session.commit()
    assert r1.prev_hash == GENESIS_HASH
    assert r2.prev_hash == r1.entry_hash
    assert await verify_chain(session) is True


async def test_append_only_trigger_blocks_mutations(session: AsyncSession) -> None:
    user, eng = await _seed(session)
    await append_audit(session, action="a1", actor_id=user.id, engagement_id=eng.id)
    await session.commit()
    with pytest.raises(DBAPIError):
        await session.execute(text("UPDATE audit_log SET action='x'"))
        await session.commit()
    await session.rollback()
    with pytest.raises(DBAPIError):
        await session.execute(text("DELETE FROM audit_log"))
        await session.commit()
    await session.rollback()


async def test_tampering_breaks_chain(session: AsyncSession) -> None:
    user, eng = await _seed(session)
    await append_audit(session, action="a1", actor_id=user.id, engagement_id=eng.id)
    await append_audit(session, action="a2", actor_id=user.id, engagement_id=eng.id)
    await session.commit()
    await session.execute(text("ALTER TABLE audit_log DISABLE TRIGGER audit_log_no_mutate_trg"))
    await session.execute(
        text("UPDATE audit_log SET action='tampered' WHERE id=(SELECT min(id) FROM audit_log)")
    )
    await session.execute(text("ALTER TABLE audit_log ENABLE TRIGGER audit_log_no_mutate_trg"))
    await session.commit()
    assert await verify_chain(session) is False
