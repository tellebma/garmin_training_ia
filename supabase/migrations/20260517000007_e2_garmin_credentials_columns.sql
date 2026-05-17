-- E2 — extend garmin_credentials with first-sync flag and error state
alter table public.garmin_credentials
  add column if not exists initial_sync_completed_at timestamptz,
  add column if not exists token_refresh_failed_at timestamptz;

comment on column public.garmin_credentials.initial_sync_completed_at is
  'When the 90-day backfill finished. Null = not yet, or auth lost.';
comment on column public.garmin_credentials.token_refresh_failed_at is
  'Last time Garmin auth refresh failed; user must reconnect when set.';
