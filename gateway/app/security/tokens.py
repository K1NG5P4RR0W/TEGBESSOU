"""Jetons JWT signés en Ed25519 (EdDSA) : access court + refresh."""

import datetime as dt
import uuid
from typing import Any

import jwt
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)
from cryptography.hazmat.primitives.serialization import load_pem_private_key

from app.core.config import settings

_priv: Ed25519PrivateKey | None = None
_pub: Ed25519PublicKey | None = None


def _keys() -> tuple[Ed25519PrivateKey, Ed25519PublicKey]:
    global _priv, _pub
    if _priv is not None and _pub is not None:
        return _priv, _pub
    if settings.jwt_private_key:
        loaded = load_pem_private_key(settings.jwt_private_key.encode(), password=None)
        if not isinstance(loaded, Ed25519PrivateKey):
            raise TypeError("JWT_PRIVATE_KEY doit être une clé Ed25519.")
        priv = loaded
    else:
        priv = Ed25519PrivateKey.generate()
    pub = priv.public_key()
    _priv, _pub = priv, pub
    return priv, pub


def _create(sub: uuid.UUID, role: str, token_type: str, ttl: int) -> str:
    now = dt.datetime.now(tz=dt.UTC)
    payload: dict[str, Any] = {
        "sub": str(sub),
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + dt.timedelta(seconds=ttl),
        "jti": uuid.uuid4().hex,
    }
    priv, _ = _keys()
    return jwt.encode(payload, priv, algorithm="EdDSA")


def create_access(sub: uuid.UUID, role: str) -> str:
    return _create(sub, role, "access", settings.access_ttl_seconds)


def create_refresh(sub: uuid.UUID, role: str) -> str:
    return _create(sub, role, "refresh", settings.refresh_ttl_seconds)


def decode(token: str, expected_type: str) -> dict[str, Any]:
    _, pub = _keys()
    payload: dict[str, Any] = jwt.decode(token, pub, algorithms=["EdDSA"])
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError("type de jeton inattendu")
    return payload
