# Definition of Done — quand une tâche est « faite »

> Une tâche n'est PAS finie tant que **toutes** ces cases ne sont pas cochées.
> C'est vérifiable, pas subjectif. Pas de « ça marche chez moi ».

## Checklist obligatoire (chaque PR)
- [ ] **Tests écrits et verts** — le comportement est prouvé par des tests, pas décrit à l'oral.
- [ ] **`ruff check .` propre** et **`mypy` propre** (pour la gateway : `mypy app`).
- [ ] **CI verte** — `ci` ET `security` au vert sur la PR.
- [ ] **PR relue et approuvée** par un autre membre (jamais s'auto-merger).
- [ ] **Aucun secret** introduit (gitleaks vert ; `.env` non commité).
- [ ] **Doc à jour** si le contrat d'API ou une commande a changé (`docs/`).
- [ ] **`uv.lock` commité** si `pyproject.toml` a changé (dans le même commit).
- [ ] **Commit conventionnel** : `feat:`, `fix:`, `sec:`, `docs:`, `chore:`.

## Checklist renforcée (si la tâche touche l'offensif / l'exécution)
- [ ] **Scope respecté** : toute action vers une cible passe par le Scope Enforcer.
- [ ] **Rate limit** appliqué si la tâche envoie des requêtes.
- [ ] **Action journalisée** (`append_audit`) avec l'acteur et la cible.
- [ ] **Aucune exécution hors sandbox** ni egress non contrôlé.

## Règle d'or
**Une brique prouvée avant la suivante.** On ne démarre pas une nouvelle tâche
tant que la précédente n'est pas « Done » au sens ci-dessus. Mieux vaut une
brique lente et solide que trois briques bancales.

## Revue de PR — ce que le relecteur vérifie
1. Les tests couvrent le cas nominal ET au moins un cas d'échec.
2. Les entrées sont validées (pas d'injection possible).
3. Pas de dette évidente laissée sans `TODO` explicite.
4. Le code suit les patterns existants (regarde `app/api/engagements.py` comme
   référence : routeur → dépendances → modèles → audit).
