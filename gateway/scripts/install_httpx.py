"""Installe httpx (version épinglée, vérifiée par sha256) dans l'image worker,
sans dépendre d'apt (même contournement que scripts/install_subfinder.py).
N'utilise que la stdlib, déjà présente dans l'image de base."""

from __future__ import annotations

import hashlib
import io
import os
import sys
import urllib.request
import zipfile

DEST = "/usr/local/bin/httpx"


def main() -> None:
    version = os.environ["HTTPX_VERSION"]
    expected_sha256 = os.environ["HTTPX_SHA256"]
    url = (
        "https://github.com/projectdiscovery/httpx/releases/download/"
        f"v{version}/httpx_{version}_linux_amd64.zip"
    )
    with urllib.request.urlopen(url, timeout=60) as resp:  # noqa: S310
        data = resp.read()

    actual_sha256 = hashlib.sha256(data).hexdigest()
    if actual_sha256 != expected_sha256:
        sys.exit(f"sha256 mismatch for {url}: got {actual_sha256}, expected {expected_sha256}")

    with zipfile.ZipFile(io.BytesIO(data)) as zf, zf.open("httpx") as src:
        with open(DEST, "wb") as dst:
            dst.write(src.read())
    # Binaire CLI dans /usr/local/bin, exécuté par l'utilisateur non-root
    # `appuser` (pas dans le groupe propriétaire) : l'exécution "other" est
    # nécessaire, pas d'écriture ni de contenu sensible dans ce fichier.
    os.chmod(DEST, 0o755)  # noqa: S103


if __name__ == "__main__":
    main()
