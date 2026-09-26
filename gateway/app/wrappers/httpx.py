"""Wrapper httpx — sonde d'hôtes vivants (E2-2).

Même contrat que subfinder (E2-1) : `build_args` fabrique la commande (args
typés, jamais de shell), `parse` normalise la sortie JSON lines de httpx.
L'exécution réelle est faite par le worker, à travers le sas d'egress ; httpx
est du trafic ACTIF (il touche la cible), contrairement à subfinder (passif).
"""

from __future__ import annotations

import json
import re
from typing import Any

from app.wrappers.base import ToolWrapper, WrapperItem, WrapperResult

_HOST_RE = re.compile(r"^(?=.{1,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$")


class InvalidTargetError(ValueError):
    pass


class HttpxWrapper(ToolWrapper):
    name = "httpx"
    default_kind = "host"

    def __init__(
        self,
        *,
        tech_detect: bool = True,
        status_code: bool = True,
        title: bool = True,
        web_server: bool = True,
    ) -> None:
        self.tech_detect = tech_detect
        self.status_code = status_code
        self.title = title
        self.web_server = web_server

    def build_args(self, target: str) -> list[str]:
        host = target.strip().lower()
        if not _HOST_RE.match(host):
            raise InvalidTargetError(f"hôte invalide : {target!r}")
        args = ["httpx", "-u", host, "-json", "-silent"]
        if self.status_code:
            args.append("-status-code")
        if self.title:
            args.append("-title")
        if self.tech_detect:
            args.append("-tech-detect")
        if self.web_server:
            args.append("-web-server")
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
            raw_value = obj.get("url")
            if isinstance(raw_value, str) and raw_value.strip():
                value = raw_value.strip()
            else:
                host = obj.get("host")
                if not isinstance(host, str) or not host.strip():
                    continue
                value = host.strip()
            metadata: dict[str, Any] = {}
            for key in ("status_code", "title", "webserver", "scheme", "port"):
                if key in obj and obj[key] not in (None, ""):
                    metadata[key] = obj[key]
            tech = obj.get("tech")
            if isinstance(tech, list) and tech:
                metadata["tech"] = [t for t in tech if isinstance(t, str)]
            if value not in seen:
                seen[value] = WrapperItem(kind=self.default_kind, value=value, metadata=metadata)
        return WrapperResult(
            tool=self.name, target=target.strip().lower(), items=list(seen.values())
        )
