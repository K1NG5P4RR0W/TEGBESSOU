# Répartition des chantiers — Phase 1

> Objectif : chacun avance sur une lane autonome, personne ne se marche dessus.
> À ajuster selon les préférences réelles de chacun.

| Membre | Lane | Tâches | Pourquoi |
|---|---|---|---|
| **Fréjus** (K1NG5P4RR0W) | CŒUR — exécution + RECON | E0 → E1 → E3 | Chemin critique, touche sécurité/archi : revient au mainteneur principal |
| **Coéquipier front** (React) | FRONT — Dashboard | D1 → D2 → D3 → D4 | Chantier visuel autonome, consomme l'API existante |
| **Coéquipier back** (Python) | BACK — CLI, puis wrappers | C1 → C2 → C3, puis E2 | La CLI règle le confort token/mot de passe ; les wrappers alimentent RECON |

## Règles de coordination (« rien laissé au hasard »)
1. **Une lane = un responsable.** Le responsable ouvre les issues de sa lane, les tient à jour.
2. **Revue croisée obligatoire.** Front relit Back et inversement quand c'est possible ; Fréjus relit les PR qui touchent les gardes ou l'audit.
3. **Le cœur (E) ne code pas avant E0.** La conception de l'isolation d'exécution se fait à deux (Fréjus + relecteur) — c'est le seul endroit où une erreur a un vrai coût de sécurité.
4. **Definition of Done non négociable** (voir `DEFINITION_OF_DONE.md`).
5. **On termine avant d'élargir.** Quand une lane a fini ses tâches, son responsable prend la tâche suivante prioritaire (souvent aider le cœur : wrappers, tests d'intégration).

## Onboarding d'un nouveau membre
1. NDA signé.
2. Accès GitHub (rôle **Write**, jamais Admin).
3. Suit `docs/ONBOARDING.md` jusqu'à `make test` vert.
4. Lit `docs/IMPLEMENTATION.md` (archi) + `docs/AGENTS.md` (méthodo) + cette roadmap.
5. Prend une première petite issue « good first task » pour se roder au flux PR.
