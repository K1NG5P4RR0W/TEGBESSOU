"""Bloque le démarrage d'arq tant que le worker n'a pas de route par défaut.

`worker-netinit` (side-car jetable, cf. docker-compose.yml) installe la route
par défaut du worker vers le sas d'egress (10.90.0.2) APRÈS le démarrage du
conteneur worker : il partage son netns via `network_mode: service:worker`,
qui doit donc déjà exister pour qu'il puisse s'y attacher. Sans cette
attente, arq pouvait commencer à traiter des jobs (httpx, subfinder) AVANT
que la route existe : toute sortie réseau échouait alors immédiatement
("network is unreachable"), sans jamais lever d'exception — un job qui
ressort "done"/exit 0 avec un stdout vide, sans qu'aucune erreur ne le
signale. Voir egress-gateway/README.md § Piège worker-netinit.

Échoue (exit 1) plutôt que de démarrer arq sans route : un worker de sécurité
qui tourne sans savoir s'il peut sortir vers le sas doit s'arrêter, pas
continuer en silence.
"""

from __future__ import annotations

import sys
import time

_POLL_SECONDS = 0.2
_MAX_WAIT_SECONDS = 60.0
_PROC_NET_ROUTE = "/proc/net/route"


def _has_default_route() -> bool:
    with open(_PROC_NET_ROUTE, encoding="ascii") as fh:
        next(fh)  # ligne d'en-tête (Iface Destination Gateway ...)
        return any(line.split()[1] == "00000000" for line in fh if line.strip())


def main() -> int:
    deadline = time.monotonic() + _MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        if _has_default_route():
            return 0
        time.sleep(_POLL_SECONDS)
    print(
        f"aucune route par défaut après {_MAX_WAIT_SECONDS:.0f}s : "
        "worker-netinit n'a pas tourné ou a échoué (voir "
        "egress-gateway/README.md § Piège worker-netinit)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
