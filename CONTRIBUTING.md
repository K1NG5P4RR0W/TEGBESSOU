# Contribution

## Branches
- `main` : protégée, toujours déployable. Aucun push direct.
- `feat/<sujet>`, `fix/<sujet>`, `sec/<sujet>` : une branche par tâche.

## Commits
Convention *Conventional Commits* : `feat:`, `fix:`, `sec:`, `docs:`, `chore:`.
Commits signés exigés sur `main`.

## Avant d'ouvrir une PR
- Tests ajoutés et verts
- Aucun secret introduit (gitleaks vert)
- Entrées validées (anti-injection)
- Actions sensibles journalisées
- Scope enforcement respecté si nouvel appel d'outil / nouveau module
- Registre des modules mis à jour si module ajouté/retiré
- Doc `docs/` à jour si contrat d'API modifié

## Discipline
Lire l'état réel avant de concevoir. Une brique prouvée et testée avant la
suivante. Officiellement supporté plutôt que bricolé.
