"""Registre des wrappers d'outils (E2-3).

Point unique pour récupérer un wrapper par son nom, afin que le worker/la
gateway n'aient pas à connaître les classes concrètes. Ajouter un outil =
une ligne ici, rien d'autre à modifier.
"""

from __future__ import annotations

from app.wrappers.base import ToolWrapper
from app.wrappers.httpx import HttpxWrapper
from app.wrappers.subfinder import SubfinderWrapper


class UnknownWrapperError(KeyError):
    pass


_REGISTRY: dict[str, ToolWrapper] = {
    SubfinderWrapper.name: SubfinderWrapper(),
    HttpxWrapper.name: HttpxWrapper(),
}


def get_wrapper(name: str) -> ToolWrapper:
    """Renvoie le wrapper enregistré sous `name`, ou lève UnknownWrapperError."""
    try:
        return _REGISTRY[name]
    except KeyError as exc:
        raise UnknownWrapperError(f"wrapper inconnu : {name!r}") from exc


def available_wrappers() -> list[str]:
    """Liste triée des noms de wrappers enregistrés."""
    return sorted(_REGISTRY)
