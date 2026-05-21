-- Track sync timestamps per category (sleep / activities / profile) so the UI
-- can show users the freshness of each data type independently. Previously
-- `last_sync_at` reflected any sync mode, which was misleading (e.g. "ok" right
-- after a sleep-only run, while activities hadn't been pulled in 24h).

ALTER TABLE garmin_credentials
  ADD COLUMN IF NOT EXISTS last_sleep_sync_at      timestamptz,
  ADD COLUMN IF NOT EXISTS last_activities_sync_at timestamptz,
  ADD COLUMN IF NOT EXISTS last_profile_sync_at    timestamptz;

COMMENT ON COLUMN garmin_credentials.last_sleep_sync_at IS
  'Timestamp of the most recent successful sleep_only sync (sleep + HRV + daily metrics).';
COMMENT ON COLUMN garmin_credentials.last_activities_sync_at IS
  'Timestamp of the most recent successful activities_only or full sync (activities + daily).';
COMMENT ON COLUMN garmin_credentials.last_profile_sync_at IS
  'Timestamp of the most recent successful profile refresh (FTP / VMA / FCmax).';
