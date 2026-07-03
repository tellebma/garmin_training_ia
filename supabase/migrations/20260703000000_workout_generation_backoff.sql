-- Backoff anti-spam sur la génération LLM des séances :
-- une session dont la génération vient d'échouer est différée (6h côté worker)
-- au lieu d'être retentée à chaque appel d'ensure_sessions.
alter table public.planned_sessions
  add column if not exists workout_generation_failed_at timestamptz;

comment on column public.planned_sessions.workout_generation_failed_at is
  'Dernier échec de génération LLM du workout ; NULL si jamais échoué ou succès depuis. Le worker diffère la régénération pendant 6h après un échec.';
