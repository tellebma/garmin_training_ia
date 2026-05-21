-- Add ON DELETE CASCADE on planned_sessions.plan_id so that deleting a
-- training_plan also removes its planned_sessions. Prevents the orphan-rows
-- bug that caused duplicate sessions on /today when a plan is regenerated.

ALTER TABLE planned_sessions
  DROP CONSTRAINT IF EXISTS planned_sessions_plan_id_fkey;

ALTER TABLE planned_sessions
  ADD CONSTRAINT planned_sessions_plan_id_fkey
  FOREIGN KEY (plan_id) REFERENCES training_plans(id) ON DELETE CASCADE;
