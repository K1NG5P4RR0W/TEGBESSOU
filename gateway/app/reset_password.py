"""Réinitialise le mot de passe d'un compte (hors HTTP).

Usage : docker compose run --rm gateway python -m app.reset_password
Variables optionnelles : ADMIN_EMAIL (sinon 1er admin), ADMIN_PASSWORD (sinon demandé).
"""

import asyncio
import getpass
import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import make_engine, make_sessionmaker
from app.models.tables import User
from app.security.audit import append_audit
from app.security.passwords import hash_password


async def _target_user(session: AsyncSession, email: str | None) -> User | None:
    if email:
        by_email: User | None = await session.scalar(select(User).where(User.email == email))
        return by_email
    first_admin: User | None = await session.scalar(
        select(User).where(User.role == "admin").order_by(User.created_at)
    )
    return first_admin


async def _run() -> None:
    email = os.environ.get("ADMIN_EMAIL")
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Nouveau mot de passe : ")
    engine = make_engine()
    maker = make_sessionmaker(engine)
    async with maker() as session:
        user = await _target_user(session, email)
        if user is None:
            print("Aucun compte correspondant. Abandon.")
            await engine.dispose()
            return
        user.password_hash = hash_password(password)
        await append_audit(
            session, action="user.password_reset", actor_id=user.id, target=user.email
        )
        await session.commit()
        print(f"Mot de passe réinitialisé pour {user.email}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
