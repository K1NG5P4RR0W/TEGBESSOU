"""Dépendances FastAPI : session DB, utilisateur courant, contrôle de rôle."""

import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

import jwt as jwtlib
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.security import tokens
from app.security.rbac import role_at_least

_bearer = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: uuid.UUID
    role: str


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    maker = request.app.state.sessionmaker
    async with maker() as session:
        yield session


async def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> CurrentUser:
    if creds is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="jeton manquant")
    try:
        payload = tokens.decode(creds.credentials, expected_type="access")
    except jwtlib.PyJWTError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="jeton invalide"
        ) from exc
    return CurrentUser(id=uuid.UUID(payload["sub"]), role=str(payload["role"]))


def require_role(min_role: str) -> Callable[[CurrentUser], Awaitable[CurrentUser]]:
    async def dependency(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
        if not role_at_least(user.role, min_role):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="privilèges insuffisants"
            )
        return user

    return dependency
