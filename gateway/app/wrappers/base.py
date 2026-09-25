"""Contrat de sortie normalisée des wrappers d'outils (E2).

Tout wrapper (subfinder, httpx, nmap…) suit le MÊME contrat :
- `build_args(target)` : construit un tableau d'arguments typé (jamais de shell) ;
- `parse(stdout, target)` : normalise la sortie brute en `WrapperResult`.

Le LLM ne voit jamais la sortie brute : il reçoit ce résultat normalisé. La
gateway persiste ces items dans le schéma de l'engagement (table `assets`).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class WrapperItem(BaseModel):
    """Un élément découvert par un outil (un sous-domaine, un hôte vivant…)."""

    kind: str  # type d'actif : subdomain | host | endpoint | port | ...
    value: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class WrapperResult(BaseModel):
    """Sortie normalisée d'une exécution d'outil."""

    tool: str
    target: str
    items: list[WrapperItem] = Field(default_factory=list)


class ToolWrapper(ABC):
    """Interface commune. Un wrapper ne fait PAS d'I/O : il construit une
    commande et parse une sortie. L'exécution est du ressort du worker."""

    name: str
    default_kind: str

    @abstractmethod
    def build_args(self, target: str) -> list[str]:
        """Tableau d'arguments (jamais `shell=True`, jamais d'interpolation)."""

    @abstractmethod
    def parse(self, stdout: str, target: str) -> WrapperResult:
        """Normalise la sortie brute en résultat structuré."""
