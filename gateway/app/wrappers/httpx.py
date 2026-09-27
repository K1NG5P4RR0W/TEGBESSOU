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

# Signature du refus HTTP du sas d'egress (egress-gateway/nginx.conf, bloc
# `return 403;` nu -> page d'erreur nginx par défaut). Repli de défense en
# profondeur si l'en-tête X-Egress-Denied n'apparaît pas dans la sortie httpx
# (mauvais flag, version différente, autre chemin de refus) : voir
# egress-gateway/README.md.
_SAS_DENIAL_WEBSERVER = "nginx/1.27.5"
_SAS_DENIAL_STATUS_CODE = 403
_SAS_DENIAL_CONTENT_LENGTH = 153


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
        timeout: int = 7,
        retries: int = 0,
    ) -> None:
        self.tech_detect = tech_detect
        self.status_code = status_code
        self.title = title
        self.web_server = web_server
        self.timeout = timeout
        self.retries = retries

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
        # Borne le temps passé sur une cible injoignable/bloquée par le sas :
        # sans ça httpx retente ~30s dans le vide avant d'être tué par le
        # timeout du job (cf. egress-gateway/README.md, § httpx à travers le sas).
        args += ["-timeout", str(self.timeout), "-retries", str(self.retries)]
        # Expose les en-têtes de réponse dans le JSON (champ `header`, un
        # objet clé/valeur normalisé — PAS `raw_header`, qui n'existe pas
        # dans le JSON de httpx v1.12.0, cf. runner/types.go) pour que
        # `parse` puisse détecter X-Egress-Denied (clé `x_egress_denied`) et
        # écarter le refus du sas.
        args.append("-include-response-header")
        return args

    @staticmethod
    def _is_sas_denial(obj: dict[str, Any]) -> bool:
        """Écarte une réponse qui est en fait le refus du sas d'egress, jamais
        une vraie réponse de la cible. Deux filets indépendants (défense en
        profondeur, cf. egress-gateway/README.md) :
        - primaire : en-tête `X-Egress-Denied` présent dans l'objet `header`
          (champ ajouté par `-include-response-header` ; httpx v1.12.0
          l'expose sous la clé normalisée `x_egress_denied`, PAS dans un
          champ `raw_header` — ce dernier n'existe pas dans cette version) ;
        - repli : signature exacte (webserver, status_code, content_length)
          de la page d'erreur 403 nue de nginx, au cas où l'en-tête n'aurait
          pas été émis ou capturé (flag oublié, autre chemin de refus…).
        """
        header = obj.get("header")
        if isinstance(header, dict) and str(header.get("x_egress_denied", "")).strip():
            return True
        return (
            obj.get("webserver") == _SAS_DENIAL_WEBSERVER
            and obj.get("status_code") == _SAS_DENIAL_STATUS_CODE
            and obj.get("content_length") == _SAS_DENIAL_CONTENT_LENGTH
        )

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
            if self._is_sas_denial(obj):
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
