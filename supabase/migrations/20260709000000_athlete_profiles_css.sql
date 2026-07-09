-- 20260709000000_athlete_profiles_css.sql
-- Ajoute le repère physiologique de référence natation (Critical Swim Speed,
-- en secondes/100m), au même niveau que ftp_watts (vélo) / vma_kmh (course).
-- Pattern identique à la colonne d'origine (20260517000000_initial_schema.sql) :
-- nullable, saisie manuelle, contrainte CHECK bornant les valeurs réalistes.

alter table public.athlete_profiles
  add column css_per_100m_s integer
    check (css_per_100m_s is null or css_per_100m_s between 40 and 300);
