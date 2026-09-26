"""Installe subfinder (version épinglée, vérifiée par sha256) dans l'image
worker, sans dépendre d'apt (contourne un souci d'environnement de build sans
rapport avec ce module : validation de signature des dépôts Debian en échec
dans ce sandbox — voir la PR). N'utilise que la stdlib, déjà présente dans
l'image de base."""

from __future__ import annotations

import hashlib
import io
import os
import sys
import urllib.request
import zipfile

DEST = "/usr/local/bin/subfinder"


def main() -> None:
    version = os.environ["SUBFINDER_VERSION"]
    expected_sha256 = os.environ["SUBFINDER_SHA256"]
    url = (
        "https://github.com/projectdiscovery/subfinder/releases/download/"
        f"v{version}/subfinder_{version}_linux_amd64.zip"
    )
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        data = resp.read()

    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != expected_sha256:
        sys.exit(f"sha256 mismatch for {url}: got {actual_sha256}, expected {expected_sha256}")

    with zipfile.ZipFile(io.BytesIO(data)) as zf, zf.open("subfinder") as src:
        with open(DEST, "wb") as dst:
            dst.write(src.read())
    # Binaire CLI dans /usr/local/bin, exécuté par l'utilisateur non-root
    # `appuser` (pas dans le groupe propriétaire) : l'exécution "other" est
    # nécessaire, pas d'écriture ni de contenu sensible dans ce fichier.
    os.chmod(DEST, 0o755)  # noqa: S103


if __name__ == "__main__":
    main()
