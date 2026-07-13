-- supabase/migrations/20260712100000_e21_changelog_last_seen.sql
-- E21 — Ajoute le suivi de la version applicative vue par l'utilisateur
-- pour le badge de nouvelles fonctionnalités (cloche).

alter table public.athlete_profiles
  add column if not exists last_seen_changelog_version text;

comment on column public.athlete_profiles.last_seen_changelog_version is
  'Dernière version applicative (tag semantic-release) dont l''utilisateur a vu les
   nouveautés dans docs/nouveautes.md via le badge cloche (E21). NULL = jamais vu.';
