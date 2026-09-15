"""Chiffrement symétrique AES-256-GCM (Credential Vault, §13.1).

Format du blob : nonce (12 o) || ciphertext+tag. La clé maître vient de
TEGBESSOU_MASTER_KEY (base64 de 32 octets), injectée par l'environnement,
jamais en base ni en dépôt.
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

_NONCE_LEN = 12


class MasterKeyMissingError(RuntimeError):
    pass


def _key() -> bytes:
    if not settings.master_key:
        raise MasterKeyMissingError(
            "TEGBESSOU_MASTER_KEY absente. Génère-la puis mets-la dans .env :\n"
            '  python -c "import os,base64; print(base64.b64encode(os.urandom(32)).decode())"'
        )
    raw = base64.b64decode(settings.master_key)
    if len(raw) != 32:
        raise ValueError("TEGBESSOU_MASTER_KEY doit décoder en 32 octets (AES-256).")
    return raw


def ensure_key() -> None:
    """Valide la présence/format de la clé maître ; lève sinon."""
    _key()


def encrypt(plaintext: bytes) -> bytes:
    nonce = os.urandom(_NONCE_LEN)
    return nonce + AESGCM(_key()).encrypt(nonce, plaintext, None)


def decrypt(blob: bytes) -> bytes:
    return AESGCM(_key()).decrypt(blob[:_NONCE_LEN], blob[_NONCE_LEN:], None)
