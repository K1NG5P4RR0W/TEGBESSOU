import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.models.tables import User
from app.security import mfa, tokens
from app.security.audit import verify_chain
from app.security.passwords import hash_password


async def _make_user(session: AsyncSession, role: str, password: str = "pw") -> User:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password(password),
        totp_secret=crypto.encrypt(mfa.new_secret().encode()),
        role=role,
    )
    session.add(user)
    await session.flush()
    await session.commit()
    return user


async def test_login_success_and_me(client: AsyncClient, session: AsyncSession) -> None:
    user = await _make_user(session, "lead", "hunter2")
    resp = await client.post("/auth/login", json={"email": user.email, "password": "hunter2"})
    assert resp.status_code == 200
    access = resp.json()["access_token"]
    me = await client.get("/auth/me", headers={"Authorization": f"Bearer {access}"})
    assert me.status_code == 200
    assert me.json()["role"] == "lead"


async def test_login_wrong_password(client: AsyncClient, session: AsyncSession) -> None:
    user = await _make_user(session, "analyst", "good")
    resp = await client.post("/auth/login", json={"email": user.email, "password": "bad"})
    assert resp.status_code == 401


async def test_refresh_issues_new_access(client: AsyncClient, session: AsyncSession) -> None:
    user = await _make_user(session, "viewer", "pw")
    login = await client.post("/auth/login", json={"email": user.email, "password": "pw"})
    refresh_token = login.json()["refresh_token"]
    resp = await client.post("/auth/refresh", json={"refresh_token": refresh_token})
    assert resp.status_code == 200
    assert "access_token" in resp.json()


async def test_create_user_requires_admin(client: AsyncClient, session: AsyncSession) -> None:
    analyst = await _make_user(session, "analyst")
    token = tokens.create_access(analyst.id, "analyst")
    resp = await client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "x@example.com", "password": "pw", "role": "analyst"},
    )
    assert resp.status_code == 403


async def test_admin_creates_user_and_audit_chain(
    client: AsyncClient, session: AsyncSession
) -> None:
    admin = await _make_user(session, "admin")
    token = tokens.create_access(admin.id, "admin")
    resp = await client.post(
        "/users",
        headers={"Authorization": f"Bearer {token}"},
        json={"email": "newbie@example.com", "password": "pw", "role": "lead"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["role"] == "lead"
    assert body["totp_provisioning_uri"].startswith("otpauth://")
    # l'action est journalisée et la chaîne d'audit reste intègre
    assert await verify_chain(session) is True


async def test_mfa_enforced_when_enabled(
    client: AsyncClient, session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    secret = mfa.new_secret()
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("pw"),
        totp_secret=crypto.encrypt(secret.encode()),
        role="lead",
    )
    session.add(user)
    await session.flush()
    await session.commit()

    monkeypatch.setattr(settings, "require_mfa", True)
    # sans code TOTP -> refus
    no_totp = await client.post("/auth/login", json={"email": user.email, "password": "pw"})
    assert no_totp.status_code == 401
    # avec le bon code -> succès
    import pyotp

    good = await client.post(
        "/auth/login",
        json={"email": user.email, "password": "pw", "totp": pyotp.TOTP(secret).now()},
    )
    assert good.status_code == 200
