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
