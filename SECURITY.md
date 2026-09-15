# Politique de sécurité

## Usage autorisé uniquement
TEGBESSOU est un outil offensif. Son usage est strictement limité aux systèmes
pour lesquels une **autorisation explicite** existe (SoW signé, périmètre d'un
programme de bug bounty, machine de CTF, environnement de lab contrôlé). Tout
autre usage est interdit.

## Confidentialité
Le dépôt et la documentation sont confidentiels. Accès réservé aux intervenants
sous NDA. Ne pas rendre public, ne pas forker hors organisation.

## Secrets
Aucun secret ne doit être committé. `gitleaks` s'exécute en pre-commit et en CI.
Le `.gitignore` bloque `.env`, `*.key`, `*.pem`, `secrets/`. En cas de fuite :
révoquer immédiatement le secret, puis nettoyer l'historique.

## Signalement d'une vulnérabilité du produit
Contact : security@exemple.tld  (à renseigner). Ne pas ouvrir d'issue publique.
