"""TOTP (MFA) — optionnel, activé via REQUIRE_MFA."""

import pyotp


def new_secret() -> str:
    return pyotp.random_base32()


def provisioning_uri(secret: str, email: str) -> str:
    return pyotp.TOTP(secret).provisioning_uri(name=email, issuer_name="TEGBESSOU")


def verify(secret: str, code: str) -> bool:
    return bool(pyotp.TOTP(secret).verify(code))
