# E26 — Après-course : célébration et choix du cap — plan d'implémentation

**Spec** : `docs/superpowers/specs/2026-08-25-e26-apres-course-design.md`
**Branche** : `feat/e26-apres-course` (worktree dédié)
**Périmètre** : E26.1 → E26.7

**Ordre imposé** : E27 (T1 à T6 au moins) doit être livré avant. Sans lui, « maintenir » et
« progresser » enregistrent une intention sans effet — une promesse explicite non tenue, pire
que le statu quo.

## T1 — Migration : état du prompt

`supabase/migrations/2026082613XXXX_e26_post_race_prompt.sql` (additive) :

- sur `race_goals` : `post_race_choice` (`new_race` | `maintain` | `improve` | `dismissed`,
  contraint), `post_race_answered_at`, `post_race_prompt_snoozed_until`,
  `post_race_prompt_count smallint not null default 0` ;
- **pas** de colonne `status` : `post_race_choice is not null` *est* l'état « répondu »
  (même principe que `race_goal_id is not null` qui *est* le tag course en E23) ;
- RPC `answer_post_race_prompt(p_race_goal_id uuid, p_choice text)` en `security definer`,
  `search_path` figé, propriété vérifiée explicitement, qui écrit le choix **et**
  `athlete_profiles.training_mode` dans le même appel pour `maintain` / `improve` ;
- RPC `snooze_post_race_prompt(p_race_goal_id uuid)` : incrémente le compteur et pose
  `snoozed_until` (J+2 au premier report, J+5 au second). **La cadence vit dans la RPC**, pas
  dans le client — sinon le client décide quand on le relance ;
- `revoke execute … from public, anon` puis `grant execute … to authenticated` sur les deux
  (piège SEC-2 : `grant to authenticated` seul ne restreint rien).

Vérifier l'horodatage du fichier : postérieur à la dernière ligne de `schema_migrations`, et
sans collision avec la migration E27.

## T2 — Logique pure : le mot sur la course

`lib/coach/race-analysis.ts`, à côté de `buildRaceDebrief` (même module, mêmes entrées) :

```ts
export type RaceSaluteTone = 'cheer' | 'neutral' | 'tender'
export interface RaceSalute { tone: RaceSaluteTone; headline: string; figure: string }
export function buildRaceSalute({ race, timeline, elapsed, previous, isFirstRace }): RaceSalute
```

Ordre d'évaluation strict de la table de décision de la spec (§3) : distance courte → objectif
manqué largement → première course → objectif tenu → meilleure que la précédente → défaut.
Réutilise `buildRaceTimeline`, `resolveRaceElapsed`, `compareRaces`, `summarizeRaceHistory` :
aucun recalcul, aucune nouvelle source de vérité.

Tests `lib/coach/race-analysis.test.ts` : un cas par rang, plus les dégradés — pas de temps
cible, pas de course précédente, distance inconnue. Vérifier qu'aucun cas ne produit un
« Bravo » quand `tone === 'tender'` : c'est la règle qui compte le plus dans ce module.

## T3 — Dérivation du prompt (aucune écriture worker)

`lib/coach/post-race-prompt.ts` — une seule fonction, une seule requête :

> course dont `race_date` ∈ [today − 14 j, today], portant ≥ 1 activité rattachée **non
> exclue** (`countedActivities`, E24), `post_race_choice is null`, `snoozed_until` échu ou nul.

Le worker n'est **pas** modifié : ni `race_tagging.py`, ni `sync.py`, ni `backfill_races.py`.
C'est le choix structurant §1 de la spec — trois chemins de tag, un seul lecteur.

Tests : hors fenêtre, sans activité rattachée, seule activité exclue, déjà répondue, snooze non
échu, et le cas qui doit marcher — tag manuel rétroactif d'une course d'il y a 3 jours.

## T4 — Modale

- `components/coach/post-race-sheet.tsx` (client) : `Sheet` bas d'écran, le mot, un lien
  « Voir le débrief » → `/history/race/[id]`, trois boutons de cap, lien discret « Plus tard ».
  « Définir un nouvel objectif » **ferme et navigue** vers le formulaire de course : pas de
  wizard imbriqué dans un tiroir.
- `app/(app)/_components/post-race-prompt.tsx` (serveur, async) monté dans
  `app/(app)/layout.tsx` sous `<Suspense fallback={null}>`. **Ne pas** l'ajouter au
  `Promise.all` du layout : une modale ne doit jamais retarder le rendu de l'app.
- `app/actions/post-race.ts` : `answerPostRacePrompt` / `snoozePostRacePrompt`, validation zod,
  appel RPC, `revalidatePath` — même forme que `app/actions/race.ts`.

## T5 — Bannière et cap modifiable

- `/today` : après deux reports (`post_race_prompt_count >= 2`), une ligne discrète au-dessus de
  la séance du jour, avec les trois mêmes choix. Plus jamais de modale pour cette course.
- Profil : le cap courant est affiché et modifiable à tout moment — le choix post-course n'est
  pas un one-shot (recoupe T7 d'E27, à ne pas implémenter deux fois).

## T6 — Le défaut n'est jamais le vide

Vérifier de bout en bout le cas « l'athlète ne répond jamais » : à J+7, récupération (E27.1)
puis `training_mode = 'maintain'` **sans** écrire `post_race_choice`. Ce comportement vit dans
le planner (E27, T5) ; ici on teste seulement que la question reste posée et que la bannière
reste affichée.

## T7 — E2E et qualité

- Playwright : course détectée → modale → report → modale à J+2 → choix « maintenir » → plan
  non vide. La partie « à J+2 » se joue en manipulant `snoozed_until`, pas l'horloge.
- `pnpm lint && pnpm typecheck && pnpm test && pnpm test:e2e && pnpm build`.
- Sonar `new_violations = 0`.

## T8 — Changelog utilisateur

`docs/nouveautes.md` — c'est une feature visible, deux puces suffisent :

> - Après une course, l'app te dit un mot sur ta performance et te demande la suite.
> - Nouveau cap possible sans viser de course : maintenir ta forme, ou progresser tranquillement.
