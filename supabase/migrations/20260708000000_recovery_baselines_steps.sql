-- 20260708000000_recovery_baselines_steps.sql
-- E9.5: steps comme 6ème signal de récupération (baseline perso, poids faible dans le briefing).

alter table public.recovery_baselines
  add column if not exists steps jsonb;

comment on column public.recovery_baselines.steps is
  'E9.5 — baseline steps (médiane 28j, higher_is_better=false). Signal faible/indirect, hors scope /stats.';
