"""Coffre de fichiers : contenu chiffré AES-256-GCM sur volume, référencé en base.

La base ne garde que la métadonnée + le hash (preuve d'intégrité) ; le contenu
vit ici, chiffré au repos. Le nom de fichier est un UUID non devinable, ce qui
évite l'énumération et la traversée de chemin.
"""

import pathlib
import uuid

from app.core import crypto
from app.core.config import settings


class FileRefError(ValueError):
    pass


def _dir() -> pathlib.Path:
    d = pathlib.Path(settings.file_vault_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def store(content: bytes) -> str:
    ref = uuid.uuid4().hex
    (_dir() / f"{ref}.enc").write_bytes(crypto.encrypt(content))
    return ref


def load(ref: str) -> bytes:
    try:
        uuid.UUID(hex=ref)
    except ValueError as exc:
        raise FileRefError("référence de fichier invalide") from exc
    path = _dir() / f"{ref}.enc"
    if not path.is_file():
        raise FileRefError("fichier introuvable")
    return crypto.decrypt(path.read_bytes())
