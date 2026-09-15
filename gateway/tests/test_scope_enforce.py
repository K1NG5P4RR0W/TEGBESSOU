import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import Engagement, ScopeEntry, User
from app.security.audit import verify_chain
from app.security.scope import ScopeViolationError, enforce_scope


async def _engagement_with_scope(session: AsyncSession) -> Engagement:
    owner = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash="x",
        totp_secret=b"\x00",
        role="lead",
    )
    session.add(owner)
    await session.flush()
    eng = Engagement(
        name="CTF", mode="ctf", schema_name=f"eng_{uuid.uuid4().hex[:8]}", owner_id=owner.id
    )
    session.add(eng)
    await session.flush()
    session.add_all(
        [
            ScopeEntry(
                engagement_id=eng.id, kind="domain", value="*.target.test", disposition="in_scope"
            ),
            ScopeEntry(
                engagement_id=eng.id,
                kind="domain",
                value="admin.target.test",
                disposition="exclusion",
            ),
        ]
    )
    await session.flush()
    await session.commit()
    return eng


async def test_in_scope_target_allowed(session: AsyncSession) -> None:
    eng = await _engagement_with_scope(session)
    decision = await enforce_scope(session, engagement_id=eng.id, target="https://api.target.test/")
    assert decision.allowed is True


async def test_out_of_scope_target_raises_and_is_audited(session: AsyncSession) -> None:
    eng = await _engagement_with_scope(session)
    with pytest.raises(ScopeViolationError):
        await enforce_scope(session, engagement_id=eng.id, target="https://evil.test/")
    # la violation est journalisée et la chaîne d'audit reste intègre
    assert await verify_chain(session) is True


async def test_excluded_target_raises(session: AsyncSession) -> None:
    eng = await _engagement_with_scope(session)
    with pytest.raises(ScopeViolationError):
        await enforce_scope(session, engagement_id=eng.id, target="admin.target.test")
