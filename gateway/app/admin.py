"""Création du premier compte admin (hors HTTP).

Usage : docker compose run --rm gateway python -m app.admin
Variables optionnelles : ADMIN_EMAIL, ADMIN_PASSWORD (sinon demandées).
"""

import asyncio
import getpass
import os

from sqlalchemy import func, select

from app.core import crypto
from app.core.db import make_engine, make_sessionmaker
from app.models.tables import User
from app.security import mfa
from app.security.audit import append_audit
from app.security.passwords import hash_password


async def _run() -> None:
    crypto.ensure_key()  # échoue tôt et clairement si TEGBESSOU_MASTER_KEY absente
    email = os.environ.get("ADMIN_EMAIL") or input("Email admin : ").strip()
    password = os.environ.get("ADMIN_PASSWORD") or getpass.getpass("Mot de passe : ")
    engine = make_engine()
    maker = make_sessionmaker(engine)
    async with maker() as session:
        existing = await session.scalar(
            select(func.count()).select_from(User).where(User.role == "admin")
        )
        if existing:
            print("Un compte admin existe déjà. Abandon.")
            await engine.dispose()
            return
        secret = mfa.new_secret()
        user = User(
            email=email,
            password_hash=hash_password(password),
            totp_secret=crypto.encrypt(secret.encode()),
            role="admin",
        )
        session.add(user)
        await session.flush()
        await append_audit(
            session, action="user.create", actor_id=user.id, target=email, params={"role": "admin"}
        )
        await session.commit()
        print(f"Admin créé : {email}")
        uri = mfa.provisioning_uri(secret, email)
        print("URI TOTP (à ajouter dans un authenticator si MFA activée) :")
        print(f"  {uri}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(_run())
