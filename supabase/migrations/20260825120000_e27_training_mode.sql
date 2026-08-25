-- E27 — Mode d'entraînement : l'app continue de proposer un plan sans course à venir.
--
-- Tout le moteur de plan dérivait d'une `race_date` : sans course future,
-- `_load_plan_inputs` renvoyait `no_race_goal` ou `race_in_past` et RIEN n'était généré.
-- Un athlète entre deux objectifs — l'état par défaut le lendemain de chaque course —
-- n'avait donc aucun plan.
--
-- `training_mode` est la SOURCE DE VÉRITÉ UNIQUE du cap courant. Le risque évident serait
-- deux vérités (la colonne d'un côté, l'existence d'un race_goal primaire futur de l'autre) :
-- la règle est donc que créer un objectif écrit `training_mode = 'race'` dans la même
-- transaction. `generate_plan` lit cette colonne, et elle seule, pour choisir sa branche.
--
-- Additif uniquement (colonnes nullable ou avec défaut) : contrat expand/contract respecté.

alter table public.athlete_profiles
  add column if not exists training_mode text not null default 'race'
    check (training_mode in ('race', 'maintain', 'improve')),
  add column if not exists training_mode_since date;

comment on column public.athlete_profiles.training_mode is
  'Cap d''entraînement courant (E27) : race = préparation d''une épreuve datée, '
  'maintain = tenir la forme actuelle, improve = progresser sans objectif daté. '
  'Source de vérité unique : créer un objectif de course écrit ''race'' ici même.';

comment on column public.athlete_profiles.training_mode_since is
  'ANCRE DE CYCLE (E27), pas un updated_at : la semaine de décharge se calcule en '
  'nombre de semaines écoulées depuis cette date. Elle ne bouge QU''AU CHANGEMENT DE MODE. '
  'La rafraîchir à chaque écriture repousserait le deload indéfiniment.';

-- Profils existants : le mode par défaut ('race') est déjà le bon, il ne manque que l'ancre.
update public.athlete_profiles
   set training_mode_since = current_date
 where training_mode_since is null;

-- =========================================
-- Un plan peut désormais n'être rattaché à aucune course
-- =========================================

-- `race_goal_id not null` était la traduction en base de « un plan prépare une épreuve ».
-- Un plan de maintien ou de progression continue n'en prépare aucune.
alter table public.training_plans
  alter column race_goal_id drop not null;

comment on column public.training_plans.race_goal_id is
  'Course préparée par ce plan. NULL = plan sans objectif daté (E27, mode maintain/improve).';

-- L'unicité du plan actif reposait sur (user_id, race_goal_id) : avec un race_goal_id NULL,
-- Postgres considère chaque ligne comme distincte et l'index ne garantit plus rien — deux
-- plans actifs sans course pourraient coexister, et `/today` afficherait deux séances par
-- jour (bug déjà vécu avec les plans orphelins). D'où un second index, pour ce cas précis.
create unique index if not exists training_plans_active_without_race_per_user
  on public.training_plans (user_id)
  where status = 'active' and race_goal_id is null;
