"""Wrapper subfinder — énumération passive de sous-domaines (E2-1/E3b).

Aucun réseau ici : `build_args` fabrique la commande, `parse` normalise la
sortie JSON lines de subfinder. L'exécution réelle est faite par le worker,
qui ne peut sortir que via le sas d'egress (allowlist B, E3a/E3b).
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

# Sources passives fixes, sans clé API (E3b, décision imposée). Vérifiées
# contre le code source réel de subfinder v2.16.0 (nom de source + endpoint
# HTTP contacté) — voir egress-gateway/policy/allowlist-osint.conf pour la
# correspondance complète source -> host et les sources volontairement
# exclues (alienvault/certspotter : clé requise désormais ; crtsh : voie
# primaire non-HTTP). Toujours appliquée via `-sources` : pas de `-all`, qui
# ouvrirait des sources à clé et contredirait la restriction imposée.
PASSIVE_SOURCES: tuple[str, ...] = (
    "hackertarget",
    "rapiddns",
    "anubis",
    "sitedossier",
    "waybackarchive",
    "digitorus",
    "commoncrawl",
    "submd",
)

# subfinder v2.16.0 refuse de démarrer si ce fichier n'existe pas (vérifié à
# l'exécution : pas de valeurs par défaut silencieuses). Baké en lecture seule
# dans l'image worker (Dockerfile, stage `worker`) — vide, aucune clé. Ne
# suffit pas seul : $HOME doit aussi être défini dans l'environnement du
# worker (docker-compose.yml, `HOME: /tmp`), sinon subfinder échoue avant
# même d'honorer `-config` — vérifié à l'exécution.
_FLAG_CONFIG_PATH = "/etc/subfinder/config.yaml"


class InvalidTargetError(ValueError):
    pass


class SubfinderWrapper(ToolWrapper):
    name = "subfinder"
    default_kind = "subdomain"

    def __init__(self, *, recursive: bool = False) -> None:
        self.recursive = recursive

    def build_args(self, target: str) -> list[str]:
        domain = target.strip().lower()
        if not _DOMAIN_RE.match(domain):
            raise InvalidTargetError(f"domaine invalide : {target!r}")
        args = [
            "subfinder",
            "-d",
            domain,
            "-silent",
            "-json",
            "-config",
            _FLAG_CONFIG_PATH,
            "-sources",
            ",".join(PASSIVE_SOURCES),
        ]
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
