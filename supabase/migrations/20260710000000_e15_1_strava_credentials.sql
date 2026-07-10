-- E15.1 — Strava OAuth credentials, one row per user (mirrors garmin_credentials)
create table public.athlete_strava_credentials (
  user_id uuid primary key references auth.users(id) on delete cascade,
  strava_athlete_id bigint not null unique,
  oauth_tokens_encrypted text not null,
  last_sync_at timestamptz,
  last_sync_status text,
  initial_sync_completed_at timestamptz,
  token_refresh_failed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

alter table public.athlete_strava_credentials enable row level security;

create policy "users read own strava credentials"
  on public.athlete_strava_credentials for select
  using (auth.uid() = user_id);

-- SEC-1 hardening, applied up-front (see 20260702000000_security_db_hardening.sql
-- for the garmin_credentials precedent this mirrors): oauth_tokens_encrypted must
-- never be readable via the Data API. RLS restricts rows, not columns, and
-- Supabase's default privileges grant table-level SELECT/INSERT/UPDATE/DELETE to
-- anon/authenticated on every new public table. Table-level grants must be
-- revoked first — a table-level SELECT grant makes column-level GRANT SELECT
-- (col, ...) moot (Postgres checks table-level privileges first).
revoke all on public.athlete_strava_credentials from anon;
revoke all on public.athlete_strava_credentials from authenticated;

-- Re-grant SELECT to authenticated, column-by-column, excluding
-- oauth_tokens_encrypted. RLS ("users read own strava credentials", kept above)
-- still restricts this to the owner's row.
grant select (
  user_id,
  strava_athlete_id,
  last_sync_at,
  last_sync_status,
  initial_sync_completed_at,
  token_refresh_failed_at,
  created_at,
  updated_at
) on public.athlete_strava_credentials to authenticated;

-- No re-grant to anon: this table always requires an authenticated session.

-- All writes (connect + disconnect) go through the worker via service_role,
-- which bypasses RLS/grants entirely — see strava_connect.py and the
-- /strava/connect and /strava/disconnect endpoints in main.py. The frontend
-- only ever does a read-only select on status columns. INSERT/UPDATE/DELETE
-- policies would be dead code once the table-level grants above are revoked,
-- so they are never created.

create trigger trg_athlete_strava_credentials_updated_at
  before update on public.athlete_strava_credentials
  for each row execute procedure public.touch_updated_at();
