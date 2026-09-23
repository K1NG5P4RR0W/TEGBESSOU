"""Wrapper subfinder — énumération passive de sous-domaines (E2-1, référence).

Aucun réseau ici : `build_args` fabrique la commande, `parse` normalise la
sortie JSON lines de subfinder. L'exécution réelle est faite par le worker.
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.wrappers.base import ToolWrapper, WrapperItem, WrapperResult

# Domaine plausible (labels alphanum + tirets, TLD alphabétique). Garde de
# cohérence en plus du Scope Enforcer : on ne construit pas de commande sur une
# entrée douteuse.
_DOMAIN_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


class InvalidTargetError(ValueError):
    pass


class SubfinderWrapper(ToolWrapper):
    name = "subfinder"
    default_kind = "subdomain"

    def __init__(self, *, all_sources: bool = False, recursive: bool = False) -> None:
        self.all_sources = all_sources
        self.recursive = recursive

    def build_args(self, target: str) -> list[str]:
        domain = target.strip().lower()
        if not _DOMAIN_RE.match(domain):
            raise InvalidTargetError(f"domaine invalide : {target!r}")
        args = ["subfinder", "-d", domain, "-silent", "-json"]
        if self.all_sources:
            args.append("-all")
        if self.recursive:
            args.append("-recursive")
        return args

    def parse(self, stdout: str, target: str) -> WrapperResult:
        seen: dict[str, WrapperItem] = {}
        for raw_line in stdout.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            try:
                obj: Any = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(obj, dict):
                continue
            host = obj.get("host")
            if not isinstance(host, str) or not host.strip():
                continue
            host = host.strip().lower()
            metadata: dict[str, Any] = {}
            source = obj.get("source")
            if isinstance(source, str) and source:
                metadata["source"] = source
            if host not in seen:
                seen[host] = WrapperItem(kind=self.default_kind, value=host, metadata=metadata)
        return WrapperResult(
            tool=self.name, target=target.strip().lower(), items=list(seen.values())
        )
