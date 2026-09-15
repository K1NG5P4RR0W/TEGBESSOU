"""Endpoints d'authentification."""

import uuid

import jwt as jwtlib
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_session
from app.core import crypto
from app.core.config import settings
from app.models.tables import User
from app.security import mfa, tokens
from app.security.audit import append_audit
from app.security.passwords import verify_password

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginIn(BaseModel):
    email: EmailStr
    password: str
    totp: str | None = None


class TokenOut(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105


class RefreshIn(BaseModel):
    refresh_token: str


class MeOut(BaseModel):
    id: str
    role: str


@router.post("/login")
async def login(body: LoginIn, session: AsyncSession = Depends(get_session)) -> TokenOut:
    user = await session.scalar(select(User).where(User.email == body.email))
    if user is None or not user.is_active or not verify_password(user.password_hash, body.password):
        await append_audit(session, action="user.login.failed", target=body.email)
        await session.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="identifiants invalides"
        )
    if settings.require_mfa:
        secret = crypto.decrypt(user.totp_secret).decode()
        if body.totp is None or not mfa.verify(secret, body.totp):
            await append_audit(
                session, action="user.login.mfa_failed", actor_id=user.id, target=user.email
            )
            await session.commit()
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="MFA invalide")
    await append_audit(session, action="user.login", actor_id=user.id, target=user.email)
    await session.commit()
    return TokenOut(
        access_token=tokens.create_access(user.id, user.role),
        refresh_token=tokens.create_refresh(user.id, user.role),
    )


@router.post("/refresh")
async def refresh(body: RefreshIn) -> TokenOut:
    try:
        payload = tokens.decode(body.refresh_token, expected_type="refresh")
    except jwtlib.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="refresh invalide"
        ) from exc
    sub = uuid.UUID(payload["sub"])
    role = str(payload["role"])
    return TokenOut(
        access_token=tokens.create_access(sub, role),
        refresh_token=tokens.create_refresh(sub, role),
    )


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user)) -> MeOut:
    return MeOut(id=str(user.id), role=user.role)
