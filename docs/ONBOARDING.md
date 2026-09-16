# Onboarding développeur — TEGBESSOU

> **Objectif : être opérationnel avec `make test` vert en moins de 20 minutes.**
> Diffusion restreinte (NDA). Ne partage rien de ce dépôt hors de l'équipe.

## 0. Prérequis
- Docker Engine ≥ 24 + Docker Compose v2
- Git, `pipx`
- `uv` : `pipx install uv`
- `pre-commit` : `pipx install pre-commit`

## 1. Cloner
```bash
git clone git@github.com:K1NG5P4RR0W/TEGBESSOU.git
cd TEGBESSOU
```

## 2. Générer la clé maître (ATTENTION — piège fréquent)
La clé chiffre les secrets locaux. Elle doit être **du base64 pur, seule sur sa ligne, sans commentaire**.

```bash
KEY=$(python3 -c "import os,base64;print(base64.b64encode(os.urandom(32)).decode())")
touch .env
sed -i '/^TEGBESSOU_MASTER_KEY=/d' .env
echo "TEGBESSOU_MASTER_KEY=$KEY" >> .env
grep '^TEGBESSOU_MASTER_KEY=' .env    # doit afficher 1 ligne, 44 caractères, AUCUN # ni tiret
```

> ⚠️ **Piège connu :** ne recopie jamais le commentaire de `.env.example` sur la ligne de la clé. Un tiret « — » ou un `#` dans la valeur casse le déchiffrement (« string argument should contain only ASCII characters »). La clé = 44 caractères base64, rien d'autre.

## 3. Activer le hook anti-secret (obligatoire)
```bash
pre-commit install
```
Il bloque tout secret avant même le commit (gitleaks + vérifs). Ne le désactive jamais.

## 4. Démarrer et vérifier
```bash
make up            # build + démarre postgres/redis/gateway/bff (127.0.0.1 uniquement)
make migrate       # applique les migrations
make create-admin  # crée ton compte admin local (prompt email + mot de passe)
make test          # DOIT être vert
```

`make test` vert = ton install est saine. Sinon, ne code pas avant d'avoir corrigé (colle le log dans le canal d'équipe).

## 5. Vérifier le login
```bash
read -rs PW; echo    # mot de passe masqué, hors historique
curl -s -X POST http://127.0.0.1:8001/auth/login \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"<ton-email>\",\"password\":\"$PW\"}"; unset PW
```
→ tu dois recevoir `access_token` + `refresh_token`.

## 6. Hygiène quotidienne
- `make down` quand tu arrêtes (libère la RAM ; le volume `pgdata` persiste).
- Ne tape jamais un mot de passe en clair dans une commande (utilise `read -rs`).
- Ne commite jamais `.env` (déjà dans `.gitignore`).

## Modèle de fonctionnement
Chacun lance **sa propre instance en local** (hybride) : le code, la méthodo et les modules sont partagés via Git ; les données de mission restent locales à chacun. Il n'y a pas de serveur central.

## En cas de blocage
1. `make down && make up` (redémarrage propre).
2. `docker compose logs --tail=50 gateway` pour voir l'erreur.
3. Si `make up` échoue au build : accès réseau à ghcr.io/PyPI, ou Docker non démarré.
4. Toujours bloqué → canal d'équipe avec le log exact.
