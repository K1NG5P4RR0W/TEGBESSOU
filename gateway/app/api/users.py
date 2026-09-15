"""Endpoints de gestion des utilisateurs (réservés admin)."""

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_session, require_role
from app.core import crypto
from app.models.tables import User
from app.security import mfa
from app.security.audit import append_audit
from app.security.passwords import hash_password

router = APIRouter(prefix="/users", tags=["users"])

Role = Literal["admin", "lead", "analyst", "viewer"]


class UserCreateIn(BaseModel):
    email: EmailStr
    password: str
    role: Role


class UserCreatedOut(BaseModel):
    id: str
    email: str
    role: str
    totp_provisioning_uri: str


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreateIn,
    actor: CurrentUser = Depends(require_role("admin")),
    session: AsyncSession = Depends(get_session),
) -> UserCreatedOut:
    secret = mfa.new_secret()
    user = User(
        email=str(body.email),
        password_hash=hash_password(body.password),
        totp_secret=crypto.encrypt(secret.encode()),
        role=body.role,
    )
    session.add(user)
    await session.flush()
    await append_audit(
        session,
        action="user.create",
        actor_id=actor.id,
        target=str(body.email),
        params={"role": body.role},
    )
    await session.commit()
    return UserCreatedOut(
        id=str(user.id),
        email=user.email,
        role=user.role,
        totp_provisioning_uri=mfa.provisioning_uri(secret, str(body.email)),
    )
