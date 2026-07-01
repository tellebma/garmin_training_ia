-- 20260702000000_security_db_hardening.sql
-- SEC-1 — DB hardening following the 2026-07-02 security audit (issue #78).
--
-- Two independent findings, addressed below:
--
-- 1. garmin_credentials.oauth_tokens_encrypted (Fernet ciphertext) was readable by
--    the owning user via PostgREST (`GET /rest/v1/garmin_credentials?select=oauth_tokens_encrypted`).
--    RLS restricted rows but not columns, and Supabase's default privileges grant
--    table-level SELECT/INSERT/UPDATE/DELETE to `anon`/`authenticated` on every new
--    public table. Only the worker (service_role, bypasses RLS/grants) ever needs to
--    read or write this column — see worker/src/garmin_sync/connect.py::_persist_tokens
--    and worker/src/garmin_sync/sync.py. Frontend reads only ever select status
--    columns (app/(app)/profile/page.tsx, app/(app)/today/page.tsx) and no frontend
--    code inserts/updates/deletes garmin_credentials directly (verified by grep across
--    app/, components/, lib/) — all writes go through the worker.
--
-- 2. Supabase advisors flagged log_auth_event / is_email_allowed / email_needs_signup
--    as SECURITY DEFINER functions executable by `anon`. All three must stay anon-
--    executable (pre-auth register/login/forgot-password flows depend on it — see
--    app/(auth)/_actions/auth.ts), so we don't revoke EXECUTE. Instead, log_auth_event
--    gets an internal anti-spam guard reusing the existing I1 rate-limit mechanism
--    (check_and_log_auth_rate_limit / auth_rate_limits), since a direct REST call to
--    it could otherwise flood auth_events unbounded. is_email_allowed and
--    email_needs_signup are left as-is (see SECURITY.md — Audit 2026-07-02 for the
--    accepted email-enumeration risk and rationale).

-- =========================================
-- 1. garmin_credentials — hide oauth_tokens_encrypted from the Data API
-- =========================================

-- Table-level grants must be revoked first: a table-level SELECT grant makes
-- column-level GRANT SELECT (col, ...) statements moot (Postgres checks
-- table-level privileges first). See advisors + Supabase "Securing your API" docs.
revoke all on public.garmin_credentials from anon;
revoke all on public.garmin_credentials from authenticated;

-- Re-grant SELECT to authenticated, column-by-column, excluding
-- oauth_tokens_encrypted. RLS ("users read own credentials", kept below) still
-- restricts this to the owner's row.
grant select (
  user_id,
  last_sync_at,
  last_sync_status,
  created_at,
  updated_at,
  initial_sync_completed_at,
  token_refresh_failed_at,
  last_sync_status_at,
  last_sync_error_message,
  last_sleep_sync_at,
  last_activities_sync_at,
  last_profile_sync_at,
  last_sync_trigger_at
) on public.garmin_credentials to authenticated;

-- No re-grant to anon: garmin_credentials always requires an authenticated session.

-- INSERT/UPDATE/DELETE policies are now dead code (no table-level grant left to
-- trigger them for anon/authenticated) — drop them for clarity. The SELECT policy
-- stays: it still gates which *rows* the column-restricted SELECT above can see.
drop policy if exists "users insert own credentials" on public.garmin_credentials;
drop policy if exists "users update own credentials" on public.garmin_credentials;
drop policy if exists "users delete own credentials" on public.garmin_credentials;

-- =========================================
-- 2. log_auth_event — internal anti-spam guard (advisor hardening)
-- =========================================
-- EXECUTE stays granted to anon/authenticated (unchanged) — pre-auth events
-- (register_initiated, login_failure, password_reset_requested) are logged before
-- a session exists. Rewritten from `language sql` to `language plpgsql` to add a
-- rate-limit check before the insert, reusing check_and_log_auth_rate_limit /
-- auth_rate_limits (I1). Budget is generous (30 events / 5 min per IP) since
-- legitimate flows call this at most once per user action; it only stops
-- unbounded flooding via a direct REST call bypassing the app's own flow.
create or replace function public.log_auth_event(
  p_user_id uuid,
  p_event_type text,
  p_ip text,
  p_user_agent text,
  p_email text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_allowed boolean;
begin
  v_allowed := public.check_and_log_auth_rate_limit(
    coalesce(p_ip, 'unknown'), 'log_auth_event', 30, 300
  );

  if not v_allowed then
    -- Silently drop: this is an audit log, never break the calling auth flow.
    return;
  end if;

  insert into public.auth_events (user_id, event_type, ip, user_agent, email)
  values (p_user_id, p_event_type, p_ip, p_user_agent, lower(p_email));
end;
$$;

comment on function public.log_auth_event(uuid, text, text, text, text) is
  'SEC-1: rate-limited via check_and_log_auth_rate_limit (30 events/5min per IP) '
  'to stop unbounded auth_events flooding via direct REST calls. Still anon-'
  'executable: pre-auth events have no session.';
