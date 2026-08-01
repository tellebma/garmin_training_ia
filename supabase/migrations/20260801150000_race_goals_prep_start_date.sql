-- 20260801150000_race_goals_prep_start_date.sql
-- Audit coach #123 : la périodisation était recalculée depuis `today` à chaque
-- régénération hebdo -> l'horizon rétrécissait d'une semaine chaque dimanche et
-- l'athlète restait perpétuellement en début de plan (jamais de phase peak,
-- régression build -> base à J-21 de la course).
--
-- `prep_start_date` est l'ancre IMMUABLE du début de préparation : posée par le
-- worker à la première génération de plan pour cette course, puis réutilisée
-- telle quelle par toutes les régénérations. Les phases et les week_offset sont
-- calculés depuis cette ancre, pas depuis la date du jour.

alter table public.race_goals
  add column if not exists prep_start_date date;

comment on column public.race_goals.prep_start_date is
  'Début de préparation immuable (posé à la 1re génération de plan). '
  'Ancre des phases base/build/peak/taper et des week_offset.';
