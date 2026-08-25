# E27 — Entraînement sans objectif — plan d'implémentation

**Spec** : `docs/superpowers/specs/2026-08-25-e27-entrainement-sans-objectif-design.md`
**Branche** : `feat/e27-entrainement-sans-objectif` (worktree dédié)
**Périmètre** : E27.1 → E27.5. E27.6 (transition `maintain` → `race` sans repartir de zéro)
reste *Todo* : la CTL mesurée assure déjà l'essentiel de la continuité.

**Ordre imposé** : ce plan précède E26. T2 est un refactor pur qui doit être vert avant que
la moindre ligne de logique nouvelle soit écrite.

## T1 — Migration : mode d'entraînement

`supabase/migrations/2026082512XXXX_e27_training_mode.sql` (additive) :

- `athlete_profiles.training_mode` (`race` | `maintain` | `improve`, `not null default 'race'`)
  et `training_mode_since date` ;
- commentaires SQL sur les deux colonnes : `training_mode_since` est l'**ancre de cycle**, elle
  ne bouge qu'au changement de mode — un futur lecteur ne doit pas la prendre pour un
  `updated_at` et la rafraîchir à chaque écriture ;
- backfill : `training_mode_since = current_date` pour les profils existants.

Vérifier l'horodatage : pas de collision avec une migration existante, et surtout un timestamp
**postérieur** à la dernière ligne de `schema_migrations` (piège vécu : une migration datée
derrière la dernière appliquée est ignorée silencieusement, CI verte incluse).

## T2 — Refactor sans changement de comportement : `RaceTarget` → `TrainingTarget`

Aucune fonctionnalité ajoutée dans cette tâche — c'est ce qui la rend sûre.

- renommer la dataclass, `race_day: date | None` remplace `day` ;
- `_race_day_session` n'est appelé que si `race_day is not None` ;
- `_build_week_sessions` / `_build_all_week_sessions` : le paramètre devient `target` ;
- les tests existants du planner passent **sans modification de leurs attentes**. Si un test doit
  changer, c'est que le refactor n'est pas neutre : s'arrêter et comprendre.

## T3 — Cycles et charge (fonctions pures, testées avant branchement)

`worker/src/garmin_sync/coach/cycles.py` (nouveau, pur, sans accès DB) :

- `cycle_week(mode_since: date, today: date) -> int` — position 0-3 dans le cycle, ancrée sur un
  calendrier absolu ;
- `compute_cycle_phases(weeks: int, mode: str, *, start_cycle_week: int) -> list[tuple[int, Phase]]`
  — même forme de retour que `compute_phases`, donc tout l'aval est inchangé ;
- `cycle_load_multipliers(mode: str, *, start_cycle_week: int, weeks: int) -> list[float]`
  — facteurs **intra-cycle, sans mémoire** (§2 de la spec) : `maintain` 1.0/1.0/1.0/0.70,
  `improve` 1.0/1.05/1.10/0.75.

Tests `worker/tests/test_cycles.py` :

- le deload tombe à la bonne semaine **absolue** quelle que soit la date de régénération ;
- deux générations à une semaine d'écart produisent des semaines calendaires cohérentes (la
  semaine qui était « offset 1 » devient « offset 0 » avec le même facteur) ;
- aucun facteur ne dépasse 1.10 : la garantie anti-explosion est dans le type de retour, pas
  dans le commentaire.

## T4 — Récupération post-course

`worker/src/garmin_sync/coach/recovery_window.py` :

- `post_race_recovery(race_date, elapsed_s, today) -> RecoveryWindow | None` — barème par durée
  réelle de l'épreuve (< 1 h 30 → 3 jours ; 1 h 30–4 h → 1 semaine ; > 4 h → 2 semaines) ;
- pendant la fenêtre : types limités à `recovery` / `endurance` courte, multiplicateur 0.5 puis
  0.75, aucune séance de qualité ni longue ;
- **priorité sur le mode choisi**, y compris `race` : un athlète qui enchaîne sur un nouvel
  objectif récupère d'abord.

Tests : les trois tranches, la priorité sur chaque mode, et le cas « course sans temps
exploitable » (retomber sur le format déclaré plutôt que ne rien faire).

## T5 — Branchement dans le planner

`_load_plan_inputs` cesse d'être un mur :

- lit `training_mode` + `training_mode_since` ;
- mode `race` avec course future → chemin actuel, strictement inchangé ;
- mode `maintain` / `improve` → nouveau chemin : horizon roulant de 4 semaines à partir de
  la semaine courante, `TrainingTarget(race_day=None, …)` construit depuis l'athlète
  (disciplines pratiquées sur 90 j, parts de temps observées, D+ hebdo observé maintenu) ;
- mode `race` sans course future → récupération si elle s'applique, sinon `maintain` par défaut
  (E26.6), **sans écrire** `post_race_choice` : la question reste posée.

Le statut de retour distingue les deux chemins (`{"status": "ok", "mode": "maintain", …}`) pour
que les logs et `/admin` disent quel moteur a produit le plan.

## T6 — Non-régression de la double rampe

Le test qui protège le vrai risque, à écrire **avant** T5 :

> simuler 6 régénérations hebdomadaires consécutives en mode `improve`, en réinjectant à chaque
> tour la CTL qu'aurait produite la charge de la semaine précédente ; la charge hebdo demandée
> ne doit pas dépasser la progression théorique de +5 %/semaine (tolérance 2 %).

Sans lui, la double composition rampe × CTL montante est invisible en revue de code et ne se
voit qu'en production, trois semaines plus tard, sous forme de surcharge.

Équivalent pour `maintain` : sur 8 semaines simulées, la CTL projetée reste dans ±5 % de la CTL
de départ.

## T7 — Front : une app qui ne parle plus que de course

- `/today` et `/plan` : afficher le mode courant au lieu du J-N quand il n'y a pas de course ;
- page profil / objectif : le cap est visible et **modifiable à tout moment** — créer un objectif
  écrit `training_mode = 'race'` dans la même transaction (§3 de la spec) ;
- vérifier les écrans qui supposent une course : `/stats`, cockpit, briefing — ils doivent
  dégrader proprement, pas afficher « J-NaN » ni disparaître.

## T8 — Qualité

`uv run ruff check . && uv run ruff format --check . && uv run mypy src/ && uv run pytest -v`,
puis `pnpm lint && pnpm typecheck && pnpm test && pnpm build`.

Sonar : `new_violations = 0` sur la branche, couverture des nouveaux fichiers purs (`cycles.py`,
`recovery_window.py`) au niveau du reste du worker — ce sont des fonctions pures, il n'y a pas
d'excuse à ne pas les couvrir.
