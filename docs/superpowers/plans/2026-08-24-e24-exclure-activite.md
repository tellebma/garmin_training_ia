# E24 — Exclure une activité — plan d'implémentation

**Spec** : `docs/superpowers/specs/2026-08-24-e24-exclure-activite-design.md`
**Branche** : `feat/e24-exclure-activite` (worktree `garmin_training-wt-exclude`)

## T1 — Migration

`supabase/migrations/20260824140000_e24_exclude_activity.sql` : colonnes `excluded_at` /
`excluded_reason`, index partiel `(user_id, start_time desc) where excluded_at is null`, RPC
`set_activity_excluded` en `security definer` + `revoke execute … from public, anon`.

## T2 — Worker : portée et filtres

- `worker/src/garmin_sync/activities_scope.py` : `counted(query)` + docstring qui dit pourquoi
  certains appelants ne l'utilisent pas.
- Appliquer dans `state.py`, `planner.py`, `discipline_level.py`, `briefing.py`, `sessions.py`,
  `chat/handlers.py`, `col_matching.py`, `home_location.py`, `race_tagging.py`.
- Tests : `worker/tests/test_activities_scope.py` (le helper pose bien le filtre) + un test par
  appelant critique (Banister, revue, race tagging) vérifiant que le filtre est demandé.
- Test de non-régression : l'upsert du sync ne contient pas `excluded_at`.

## T3 — Front : portée et filtres

- `lib/activities/scope.ts` : `countedActivities(query)`.
- Appliquer dans `/history`, `/today`, `/stats` (cockpit, volumes, widget courses),
  `/history/race/[id]`.
- `/history` : onglet/filtre `deleted` listant les exclues.

## T4 — Actions et UI

- `app/actions/activity-visibility.ts` : `deleteActivity(activityId, reason)` /
  `restoreActivity(activityId)` via la RPC, zod + `revalidatePath`.
- `app/(app)/history/[id]/activity-delete-form.tsx` : bouton + confirmation, ou bandeau
  « supprimée » + restauration.
- Tests actions (mocks Supabase) et composant (jsdom).

## T5 — Docs

`docs/nouveautes.md` (1.23.0), statut V1 dans `BACKLOG.md`, item E24.4 laissé en Todo.

## T6 — Gates

`pnpm lint && typecheck && test && build` ; worker `ruff`, `mypy`, `pytest`. Sonar :
`new_violations = 0`, couverture du nouveau code ≥ 90 %.
