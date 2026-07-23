-- 20260722100427_workout_generation_failure_cap.sql
-- Plafond d'échecs de génération. Le backoff de 6 h ne devenait jamais définitif :
-- une séance dont l'enveloppe est insatisfiable brûlait 3 requêtes OpenAI facturées
-- par fenêtre de backoff, indéfiniment (jusqu'à ~12 requêtes/jour/séance), et le
-- marqueur d'échec était remis à zéro à chaque régénération hebdo.
-- Le compteur permet d'abandonner une séance après N échecs au lieu de boucler.

alter table public.planned_sessions
  add column if not exists workout_generation_failures integer not null default 0
    check (workout_generation_failures >= 0);
