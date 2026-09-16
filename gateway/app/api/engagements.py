"""Mécanique d'engagement : création, autorisation, scope, activation, check-target.

C'est ici que la garde de périmètre (Scope Enforcer, B0.4) se branche enfin sur
un vrai engagement, et que la règle bloquante s'applique : pas d'activation sans
autorisation (§14).
"""

import datetime as dt
import hashlib
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_session, require_role
from app.core import filevault
from app.core.config import settings
from app.models.tables import Authorization, Engagement, ScopeEntry
from app.security.audit import append_audit
from app.security.scope import ScopeViolationError, enforce_scope

router = APIRouter(prefix="/engagements", tags=["engagements"])

Mode = Literal["pentest", "bug_bounty", "ctf", "audit_code"]
ScopeKind = Literal["domain", "ip", "cidr", "contract"]
Disposition = Literal["in_scope", "out_of_scope", "exclusion"]
SourceKind = Literal["sow", "program_url", "program_text"]
_ALLOWED_TYPES = {"application/pdf", "image/png", "image/jpeg"}


class EngagementCreateIn(BaseModel):
    name: str
    mode: Mode
    client: str | None = None


class EngagementOut(BaseModel):
    id: str
    name: str
    mode: str
    status: str
    current_phase: str | None
    has_authorization: bool = False


class ScopeIn(BaseModel):
    kind: ScopeKind
    value: str
    disposition: Disposition
    chain: str | None = None


class ScopeOut(BaseModel):
    id: str
    kind: str
    value: str
    disposition: str


class AuthorizationOut(BaseModel):
    source_kind: str
    content_hash: str
    has_file: bool


class CheckTargetIn(BaseModel):
    target: str
    chain: str | None = None


class CheckTargetOut(BaseModel):
    allowed: bool
    reason: str


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


async def _get_engagement(session: AsyncSession, engagement_id: uuid.UUID) -> Engagement:
    eng = await session.get(Engagement, engagement_id)
    if eng is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="engagement introuvable")
    return eng


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_engagement(
    body: EngagementCreateIn,
    actor: CurrentUser = Depends(require_role("lead")),
    session: AsyncSession = Depends(get_session),
) -> EngagementOut:
    eng = Engagement(
        name=body.name,
        mode=body.mode,
        client=body.client,
        schema_name=f"eng_{uuid.uuid4().hex}",
        status="draft",
        owner_id=actor.id,
    )
    session.add(eng)
    await session.flush()
    await append_audit(
        session,
        action="engagement.create",
        actor_id=actor.id,
        engagement_id=eng.id,
        target=eng.schema_name,
        params={"mode": body.mode},
    )
    await session.commit()
    return EngagementOut(
        id=str(eng.id), name=eng.name, mode=eng.mode, status=eng.status, current_phase=None
    )


@router.get("")
async def list_engagements(
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> list[EngagementOut]:
    rows = (await session.scalars(select(Engagement).order_by(Engagement.created_at))).all()
    return [
        EngagementOut(
            id=str(e.id),
            name=e.name,
            mode=e.mode,
            status=e.status,
            current_phase=e.current_phase,
        )
        for e in rows
    ]


@router.get("/{engagement_id}")
async def get_engagement(
    engagement_id: uuid.UUID,
    _: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EngagementOut:
    eng = await _get_engagement(session, engagement_id)
    auth = await session.scalar(
        select(Authorization).where(Authorization.engagement_id == engagement_id)
    )
    return EngagementOut(
        id=str(eng.id),
        name=eng.name,
        mode=eng.mode,
        status=eng.status,
        current_phase=eng.current_phase,
        has_authorization=auth is not None,
    )


@router.post("/{engagement_id}/authorization", status_code=status.HTTP_201_CREATED)
async def upload_authorization(
    engagement_id: uuid.UUID,
    source_kind: SourceKind = Form(...),
    file: UploadFile | None = File(None),
    program_url: str | None = Form(None),
    rules_text: str | None = Form(None),
    actor: CurrentUser = Depends(require_role("lead")),
    session: AsyncSession = Depends(get_session),
) -> AuthorizationOut:
    eng = await _get_engagement(session, engagement_id)
    existing = await session.scalar(
        select(Authorization).where(Authorization.engagement_id == engagement_id)
    )
    if existing is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="autorisation déjà présente"
        )

    document_name: str | None = None
    storage_ref: str | None = None
    rules_text_ref: str | None = None
    url: str | None = None

    if source_kind == "sow":
        if file is None:
            raise HTTPException(status_code=400, detail="fichier requis pour un SoW")
        content = await file.read()
        if len(content) > settings.max_upload_bytes:
            raise HTTPException(status_code=413, detail="fichier trop volumineux (max 10 Mo)")
        if file.content_type not in _ALLOWED_TYPES:
            raise HTTPException(status_code=415, detail="type non autorisé (PDF, PNG, JPG)")
        content_hash = _sha256(content)
        storage_ref = filevault.store(content)
        document_name = file.filename
    elif source_kind == "program_url":
        if not program_url:
            raise HTTPException(status_code=400, detail="lien du programme requis")
        url = program_url
        content_hash = _sha256(program_url.encode())
    else:  # program_text
        if not rules_text:
            raise HTTPException(status_code=400, detail="texte des règles requis")
        content_hash = _sha256(rules_text.encode())
        rules_text_ref = filevault.store(rules_text.encode())

    auth = Authorization(
        engagement_id=engagement_id,
        source_kind=source_kind,
        document_name=document_name,
        program_url=url,
        rules_text_ref=rules_text_ref,
        content_hash=content_hash,
        storage_ref=storage_ref,
    )
    session.add(auth)
    await session.flush()
    await append_audit(
        session,
        action="authorization.upload",
        actor_id=actor.id,
        engagement_id=engagement_id,
        target=eng.schema_name,
        params={"source_kind": source_kind, "content_hash": content_hash},
    )
    await session.commit()
    return AuthorizationOut(
        source_kind=source_kind, content_hash=content_hash, has_file=storage_ref is not None
    )


@router.post("/{engagement_id}/scope", status_code=status.HTTP_201_CREATED)
async def add_scope(
    engagement_id: uuid.UUID,
    body: ScopeIn,
    actor: CurrentUser = Depends(require_role("lead")),
    session: AsyncSession = Depends(get_session),
) -> ScopeOut:
    await _get_engagement(session, engagement_id)
    entry = ScopeEntry(
        engagement_id=engagement_id,
        kind=body.kind,
        value=body.value,
        disposition=body.disposition,
        chain=body.chain,
    )
    session.add(entry)
    await session.flush()
    await append_audit(
        session,
        action="scope.add",
        actor_id=actor.id,
        engagement_id=engagement_id,
        target=body.value,
        params={"kind": body.kind, "disposition": body.disposition},
    )
    await session.commit()
    return ScopeOut(
        id=str(entry.id), kind=entry.kind, value=entry.value, disposition=entry.disposition
    )


@router.post("/{engagement_id}/activate")
async def activate_engagement(
    engagement_id: uuid.UUID,
    actor: CurrentUser = Depends(require_role("lead")),
    session: AsyncSession = Depends(get_session),
) -> EngagementOut:
    eng = await _get_engagement(session, engagement_id)
    if eng.status != "draft":
        raise HTTPException(status_code=409, detail="engagement déjà activé ou clos")
    auth = await session.scalar(
        select(Authorization).where(Authorization.engagement_id == engagement_id)
    )
    if auth is None:
        raise HTTPException(status_code=400, detail="autorisation requise avant activation")
    auth.validated_by = actor.id
    auth.validated_at = dt.datetime.now(tz=dt.UTC)
    eng.status = "active"
    await append_audit(
        session,
        action="engagement.activate",
        actor_id=actor.id,
        engagement_id=engagement_id,
        target=eng.schema_name,
    )
    await session.commit()
    return EngagementOut(
        id=str(eng.id),
        name=eng.name,
        mode=eng.mode,
        status=eng.status,
        current_phase=eng.current_phase,
        has_authorization=True,
    )


@router.post("/{engagement_id}/check-target")
async def check_target(
    engagement_id: uuid.UUID,
    body: CheckTargetIn,
    actor: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> CheckTargetOut:
    eng = await _get_engagement(session, engagement_id)
    if eng.status != "active":
        raise HTTPException(status_code=409, detail="engagement non actif")
    try:
        decision = await enforce_scope(
            session,
            engagement_id=engagement_id,
            target=body.target,
            chain=body.chain,
            actor_id=actor.id,
        )
    except ScopeViolationError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(exc)) from exc
    return CheckTargetOut(allowed=True, reason=decision.reason)
