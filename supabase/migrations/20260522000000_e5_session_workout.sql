-- 20260522000000_e5_session_workout.sql
-- E5: workout JSON structure produced by LLM, plus generation timestamp.

alter table public.planned_sessions
  add column if not exists workout jsonb,
  add column if not exists workout_generated_at timestamptz;

-- Partial index for the "needs generation" hot path
create index if not exists planned_sessions_workout_pending_idx
  on public.planned_sessions (user_id, date)
  where workout is null;

comment on column public.planned_sessions.workout is
  'LLM-generated session structure (warmup, main intervals, cooldown). Schema in worker/src/garmin_sync/coach/workout_schema.py';
comment on column public.planned_sessions.workout_generated_at is
  'Timestamp of last successful workout generation. NULL means pending.';
