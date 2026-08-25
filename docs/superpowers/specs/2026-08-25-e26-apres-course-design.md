# E26 — Après-course : célébration et choix du cap — design

**Date** : 2026-08-25
**EPIC** : E26 — Après-course
**Priorité** : P1
**Dépendance dure** : E27 (mode d'entraînement sans objectif) — voir « Ordre de livraison ».

## Demande owner

> « Le après-course : mettre une popup à l'utilisateur lorsque l'on détecte la course + un très
> court bravo pour la course si on détecte que tout s'est bien passé. Ensuite il faut voir ce que
> l'utilisateur veut faire : définir un nouveau goal, maintenir l'état actuel, juste s'améliorer
> sans pour autant choisir un nouveau goal. Il faut pouvoir skip cette étape et la reproposer lors
> de la prochaine connexion ou autre. »

## Problème

E23 a fait de la course un objet de première classe **jusqu'au débrief**. Ce qui vient après
n'existe pas :

- rien ne dit un mot sur l'épreuve — il faut aller chercher `/history/race/[id]` de soi-même ;
- rien ne demande à l'athlète ce qu'il veut faire ensuite ;
- `generate_plan` renvoie `race_in_past` dès le lendemain (`planner.py:1304`) : **l'app cesse
  purement et simplement de proposer des séances**, sans le dire.

Le seul moyen de repartir est de deviner qu'il faut créer un objectif à la main. Pour un athlète
qui vient de finir sa course — et qui est précisément dans la fenêtre où il décide de la suite —
c'est le pire moment pour être laissé sans réponse.

## Choix structurants

### 1. Un état **dérivé**, pas un événement poussé

Tentation naturelle : faire écrire « prompt à poser » par le worker au moment du tag. À écarter.

Le tag arrive par **trois chemins** — `tag_races_for_user` au sync, le même en mode backfill sur
tout l'historique, et la RPC `set_activity_race` du tag manuel. Trois endroits à ne pas oublier,
et surtout : `python -m garmin_sync.coach.backfill_races` armerait une modale « Bravo ! » sur le
premier triathlon de 2024.

La question à poser se **dérive** donc d'une requête, à la volée :

> il existe un `race_goal` dont `race_date` tombe dans les **14 derniers jours**, qui porte au
> moins **une activité rattachée non exclue** (E24), dont `post_race_choice` est `NULL` et dont
> `post_race_prompt_snoozed_until` est échu ou nul.

Conséquences : le worker n'a **rien** à faire, le backfill n'a aucun effet, et le tag manuel
rétroactif d'une course récente ouvre la modale gratuitement.

### 2. L'état vit sur `race_goals`, en quatre colonnes

Pas de table `post_race_prompts` ni de table générique `user_prompts` : une course a un seul
après-course, `race_goals` est déjà scopé par RLS et déjà lu par tous les écrans concernés.

```sql
alter table public.race_goals
  add column post_race_choice text
    check (post_race_choice is null
           or post_race_choice in ('new_race', 'maintain', 'improve', 'dismissed')),
  add column post_race_answered_at timestamptz,
  add column post_race_prompt_snoozed_until date,
  add column post_race_prompt_count smallint not null default 0;
```

Pas de colonne `status` : elle serait redondante et donc désynchronisable.
`post_race_choice is not null` **est** l'état « répondu », `post_race_prompt_count` porte le
nombre de reports. Un seul fait, un seul endroit — même raisonnement que `race_goal_id is not
null` qui *est* le tag course en E23.

### 3. Le mot sur la course est calculé, jamais rédigé par un LLM

Comme `buildRaceDebrief` (E23) et `race_day.py`, le ton et la phrase sont **déterministes** :
reproductibles, testables, explicables. Nouvelle fonction pure `buildRaceSalute()` dans
`lib/coach/race-analysis.ts`, qui réutilise l'existant — `buildRaceTimeline`,
`resolveRaceElapsed`, `compareRaces`, `summarizeRaceHistory` — sans rien recalculer.

Ordre d'évaluation, du plus discriminant au plus général :

| Rang | Condition | Ton | Exemple |
|---|---|---|---|
| 1 | Distance couverte < 85 % de l'attendue (`legs`) | `tender` | « Journée difficile. On repart de là. » |
| 2 | `deltaS / targetS > 0.15` (objectif manqué largement) | `tender` | « Pas le jour. Le débrief dit où ça s'est joué. » |
| 3 | Première course de l'athlète | `cheer` | « Premier triathlon bouclé — 2h41. » |
| 4 | `deltaS <= 0` (temps visé tenu) | `cheer` | « Objectif tenu : 2h41, 4 min sous ta cible. » |
| 5 | Meilleure que la précédente de même format | `cheer` | « 2h41 — 4 min de mieux qu'à Vichy. » |
| 6 | Défaut | `neutral` | « Course bouclée en 2h41. » |

Trois règles de rédaction : **une phrase**, **un chiffre**, jamais de faux enthousiasme. Le
détail vit déjà dans le débrief, la modale y renvoie par un lien.

**Limite connue, assumée** : un abandon franc n'ouvrira pas la modale du tout. `race_tagging`
exige **60 %** de la distance attendue pour rattacher une activité (`_is_plausible_volume`) — le
garde-fou qui évite de taguer le footing de décrassage écarte aussi l'abandon à 30 %. Le ton
`tender` ne se déclenche donc que sur la bande 60–85 % ou après un tag manuel. Abaisser ce seuil
le jour même de la course (et demander « tu as abandonné ? ») est une suite possible, pas une
V1 : mieux vaut ne rien dire que féliciter quelqu'un qui a abandonné.

### 4. Le choix écrit le cap **dans la même transaction**

`answer_post_race_prompt(p_race_goal_id uuid, p_choice text)`, `security definer`, propriété
vérifiée explicitement, `revoke execute … from public, anon` (piège SEC-2) :

- écrit `post_race_choice` + `post_race_answered_at` ;
- `maintain` / `improve` → écrit `athlete_profiles.training_mode` (E27.2) **dans le même appel** :
  sans ça, un échec entre les deux écritures laisse un choix enregistré sans effet sur le plan ;
- `new_race` → ne bascule rien : le formulaire de course s'en charge, et c'est lui qui pose
  `training_mode = 'race'` et bascule l'ancienne course en `is_primary = false` ;
- `dismissed` → l'athlète refuse de choisir ; le défaut E26.6 s'applique.

`snooze_post_race_prompt(p_race_goal_id uuid)` incrémente `post_race_prompt_count` et pose
`post_race_prompt_snoozed_until` = J+2 au premier report, J+5 au second. La cadence est **dans la
RPC**, pas dans le client : le client ne doit pas pouvoir décider quand on le relance.

### 5. Trois interruptions au maximum, puis une bannière

- report 1 → modale à **J+2** ;
- report 2 → modale à **J+5** ;
- report 3 (`post_race_prompt_count >= 2`) → **plus aucune modale**. Une bannière discrète et
  permanente sur `/today` (« Et maintenant ? Choisir la suite ») prend le relais jusqu'au choix.

Reproposer à chaque connexion — la lettre de la demande owner — serait le comportement le plus
agaçant possible, précisément pendant la coupure post-course où l'athlète ouvre l'app tous les
jours sans vouloir décider. La dégressivité tient la promesse (« on ne lâche pas le sujet »)
sans transformer l'ouverture de l'app en interrogatoire.

### 6. Le défaut n'est jamais le vide

Sans réponse, à J+7 après la course : **semaine de récupération** (E27.1) puis bascule
automatique en **maintien** (`training_mode = 'maintain'`), sans écrire `post_race_choice` — la
question reste ouverte, mais l'app continue de proposer des séances. C'est le trou actuel qu'on
ferme : aujourd'hui, ne rien faire produit un plan vide et silencieux.

### 7. Chargement isolé, jamais bloquant

`app/(app)/layout.tsx` fait déjà quatre requêtes dans un `Promise.all` avant de rendre quoi que
ce soit. La requête du prompt **n'y entre pas** : composant serveur async isolé
`<PostRacePrompt />` monté dans le layout sous `<Suspense>`, qui ne rend rien tant qu'il n'a pas
sa réponse. Une modale qui met le rendu de toute l'app en attente serait un contresens.

## Écrans

- **Modale** — `Sheet` bas d'écran (cohérent avec la cloche E21, meilleur en PWA mobile) plutôt
  qu'un `Dialog` centré. Contenu : le mot (une phrase, un chiffre), un lien « Voir le débrief »
  vers `/history/race/[id]`, trois boutons de cap, un lien discret « Plus tard ».
  « Définir un nouvel objectif » **ferme la modale et navigue** vers le formulaire de course :
  pas de wizard imbriqué dans un tiroir.
- **Bannière `/today`** — après deux reports, une ligne discrète au-dessus de la séance du jour,
  avec les trois mêmes choix.
- **Profil** — le cap courant est affiché et modifiable à tout moment. Le choix post-course n'est
  pas un one-shot : un athlète qui a dit « maintien » en juillet doit pouvoir viser une course en
  septembre sans attendre la prochaine épreuve.

## Ordre de livraison

E26 **suppose** que `maintain` et `improve` produisent quelque chose. Tant qu'E27 n'est pas
livré, ces deux boutons enregistrent une intention sans effet : l'app reste vide, avec en plus
la promesse explicite d'un plan. C'est pire que le statu quo.

D'où : **E27.1 + E27.2 + E27.3 + E27.4 d'abord**, E26 ensuite. Le découpage en deux EPICs reste
justifié (worker/moteur d'un côté, front/interaction de l'autre), mais l'ordre n'est pas libre.
La colonne `athlete_profiles.training_mode` est créée par E27.2, pas par E26.

## Tests

- `buildRaceSalute()` — un cas par rang de la table de décision, plus les cas dégradés : pas de
  temps cible, pas de course précédente, distance inconnue.
- Dérivation du prompt — course hors fenêtre de 14 jours, course sans activité rattachée, course
  dont la seule activité est exclue (E24), course déjà répondue, snooze non échu.
- Cadence — deux reports produisent J+2 puis J+5 ; le troisième passage n'ouvre plus la modale.
- RPC — propriété vérifiée (course d'un autre utilisateur refusée), `EXECUTE` révoqué de `public`
  et `anon`, `maintain` écrit bien `training_mode` dans le même appel.
- E2E — parcours complet : course détectée → modale → report → modale à J+2 → choix → plan.

## Hors périmètre V1

- Notification push ou e-mail à la détection de la course (l'app n'a pas de canal push).
- Récit de course partageable — c'est E23.6 complet, pas E26.
- Question post-course pour une épreuve d'un autre athlète (comparaison entre amis) — E9/beta.
