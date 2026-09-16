import uuid

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.tables import User
from app.security import tokens
from app.security.audit import verify_chain
from app.security.passwords import hash_password


async def _lead_token(session: AsyncSession) -> str:
    user = User(
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        password_hash=hash_password("pw"),
        totp_secret=b"\x00",
        role="lead",
    )
    session.add(user)
    await session.flush()
    await session.commit()
    return tokens.create_access(user.id, "lead")


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def _create_engagement(client: AsyncClient, token: str) -> str:
    resp = await client.post(
        "/engagements", headers=_auth(token), json={"name": "CTF box", "mode": "ctf"}
    )
    assert resp.status_code == 201, resp.text
    return resp.json()["id"]


async def test_full_engagement_lifecycle_with_file(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _lead_token(session)
    eid = await _create_engagement(client, token)

    # autorisation par FICHIER (PDF factice)
    files = {"file": ("sow.pdf", b"%PDF-1.4 fake sow", "application/pdf")}
    up = await client.post(
        f"/engagements/{eid}/authorization",
        headers=_auth(token),
        data={"source_kind": "sow"},
        files=files,
    )
    assert up.status_code == 201, up.text
    assert up.json()["has_file"] is True

    # scope
    sc = await client.post(
        f"/engagements/{eid}/scope",
        headers=_auth(token),
        json={"kind": "domain", "value": "*.target.test", "disposition": "in_scope"},
    )
    assert sc.status_code == 201

    # activation (autorisation présente -> OK)
    act = await client.post(f"/engagements/{eid}/activate", headers=_auth(token))
    assert act.status_code == 200
    assert act.json()["status"] == "active"

    # check-target dans le scope -> autorisé
    ok = await client.post(
        f"/engagements/{eid}/check-target",
        headers=_auth(token),
        json={"target": "https://api.target.test/"},
    )
    assert ok.status_code == 200
    assert ok.json()["allowed"] is True

    # check-target hors scope -> 403 (et violation journalisée)
    ko = await client.post(
        f"/engagements/{eid}/check-target",
        headers=_auth(token),
        json={"target": "https://evil.test/"},
    )
    assert ko.status_code == 403

    assert await verify_chain(session) is True


async def test_authorization_by_link(client: AsyncClient, session: AsyncSession) -> None:
    token = await _lead_token(session)
    eid = await _create_engagement(client, token)
    up = await client.post(
        f"/engagements/{eid}/authorization",
        headers=_auth(token),
        data={"source_kind": "program_url", "program_url": "https://hackerone.com/prog"},
    )
    assert up.status_code == 201
    assert up.json()["has_file"] is False


async def test_cannot_activate_without_authorization(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _lead_token(session)
    eid = await _create_engagement(client, token)
    act = await client.post(f"/engagements/{eid}/activate", headers=_auth(token))
    assert act.status_code == 400  # autorisation requise


async def test_check_target_requires_active_engagement(
    client: AsyncClient, session: AsyncSession
) -> None:
    token = await _lead_token(session)
    eid = await _create_engagement(client, token)
    resp = await client.post(
        f"/engagements/{eid}/check-target",
        headers=_auth(token),
        json={"target": "https://api.target.test/"},
    )
    assert resp.status_code == 409  # engagement non actif


async def test_rejected_file_type(client: AsyncClient, session: AsyncSession) -> None:
    token = await _lead_token(session)
    eid = await _create_engagement(client, token)
    files = {"file": ("x.exe", b"MZ...", "application/octet-stream")}
    up = await client.post(
        f"/engagements/{eid}/authorization",
        headers=_auth(token),
        data={"source_kind": "sow"},
        files=files,
    )
    assert up.status_code == 415  # type non autorisé
