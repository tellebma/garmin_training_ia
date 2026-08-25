# E24 — Exclure une activité de son historique — design

**Date** : 2026-08-24
**EPIC** : E24 — Exclure une activité
**Priorité** : P1

## Demande owner

> « Il faudrait également un bouton supprimer une activité. Le jour de ma course je voulais avoir
> mon compteur GPS sur le vélo et pour qu'il m'affiche bien les métriques je l'ai lancé en mode
> activité, donc j'ai 2 activités le jour de la course. Cela doit fausser les métriques. »

## Problème

Une activité enregistrée deux fois (montre + compteur vélo) est comptée deux fois **partout** :
TSS du jour, CTL/ATL/TSB, volume hebdomadaire, revue d'activités du coach, niveau par discipline,
et — depuis E23 — la vue course, qui additionne deux fois la partie vélo de l'épreuve.

L'athlète n'a aujourd'hui aucun moyen de dire « celle-là ne compte pas ».

## Choix structurant : exclure, pas supprimer

Une suppression physique (`delete from activities`) serait **annulée au sync suivant** :
l'activité existe toujours chez Garmin, et `_sync_activities` la ré-upserte. Il faudrait de toute
façon garder une trace de « celle-ci, ne la reprends pas » — c'est-à-dire exactement un
soft-delete.

D'où :

```sql
alter table public.activities
  add column excluded_at timestamptz,
  add column excluded_reason text;
```

`excluded_at is not null` = l'activité ne compte plus. La colonne n'apparaît dans aucun row
produit par les transformers : l'upsert du sync ne la réécrit donc jamais (`ON CONFLICT DO UPDATE
SET` ne touche que les colonnes fournies). L'exclusion survit à toutes les resynchronisations.

Côté UI le bouton s'appelle **Supprimer** — c'est le mot de l'athlète — mais la conséquence est
annoncée : l'activité disparaît de l'historique et des statistiques, et reste **restaurable**
depuis un filtre dédié. Une erreur de manipulation ne doit jamais être définitive.

## L'exclusion vaut partout, et ne doit pas s'oublier

Le risque de cette feature n'est pas d'écrire le flag : c'est d'oublier un des ~20 endroits qui
lisent `activities`. Deux helpers uniques, greppables, portent le filtre :

| Côté | Helper | Usage |
|---|---|---|
| Worker | `garmin_sync.activities_scope.counted(query)` | `counted(db.table("activities").select(...))` |
| Front | `lib/activities/scope.ts` → `countedActivities(query)` | idem sur le client Supabase |

**Filtrent** (l'activité ne compte pas) : Banister/`state.py`, `planner.py`, `discipline_level.py`,
`briefing.py`, `sessions.py` (revue), `chat/handlers.py`, `col_matching.py`, `home_location.py`,
`race_tagging.py`, et côté front `/history`, `/today`, `/stats` (cockpit, volumes, courses),
`/history/race/[id]`.

**Ne filtrent pas**, volontairement :

- `sync.py` — l'ingestion, les samples, le GPS et la décomposition multisport continuent de
  tourner sur une activité exclue : la ré-exclure ne doit pas dépendre du fait qu'elle soit
  complète, et une restauration doit retrouver une activité intacte ;
- `dedup.py` — la règle Garmin-gagne compare les sources ; une activité exclue reste une preuve
  que l'effort existe déjà côté Garmin ;
- `/history/[id]` — on doit pouvoir ouvrir une activité exclue pour la restaurer ;
- `backfill_tss.py` — recalculer le TSS d'une ligne exclue est sans effet sur les agrégats et
  garde la donnée juste en cas de restauration.

## Écriture : RPC, comme le tag course

La RLS d'`activities` n'autorise que la lecture côté client. L'exclusion passe donc par une RPC
`security definer` — `set_activity_excluded(p_activity_id uuid, p_excluded boolean, p_reason text)`
— avec vérification de propriété explicite et `revoke execute … from public, anon`.

## Écrans

- `/history/[id]` : bouton **Supprimer cette activité** (avec confirmation et conséquence
  annoncée). Sur une activité déjà exclue, bandeau « Activité supprimée » + bouton **Restaurer**.
- `/history` : filtre **Supprimées** qui liste les activités exclues et permet de les restaurer.

## Hors périmètre (E24.4, reste en Todo)

Détection automatique des doublons (deux activités du même sport qui se chevauchent) et
proposition d'exclusion. La V1 laisse l'athlète décider ; la détection viendra ensuite, en
réutilisant la fenêtre de recouvrement de `dedup.py`.
