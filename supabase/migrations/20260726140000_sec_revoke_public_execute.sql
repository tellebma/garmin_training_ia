-- 20260726140000_sec_revoke_public_execute.sql
-- SEC-3 — Revoke the implicit PUBLIC EXECUTE grant on SECURITY DEFINER functions
-- that were never meant to be reachable from the Data API.
--
-- Postgres grants EXECUTE on every new function to PUBLIC by default, and `anon` /
-- `authenticated` are members of PUBLIC. A migration that only says
-- `grant execute ... to service_role` (or `to authenticated`) therefore does NOT
-- restrict anything — the function stays callable via /rest/v1/rpc/<name>. Supabase
-- advisors flag this as anon_security_definer_function_executable /
-- authenticated_security_definer_function_executable.
--
-- The SEC-1 audit (20260702000000) already reviewed log_auth_event, is_email_allowed
-- and email_needs_signup and accepted them as anon-callable (the pre-auth
-- register/login/forgot-password flows in app/(auth)/_actions/auth.ts call them with
-- the anon client). They are deliberately NOT touched here. The functions below
-- landed after that audit, or were missed by it.
--
-- 1. check_and_log_coach_rate_limit — REAL cross-tenant issue, not just hygiene.
--    Its only caller is the worker with the service-role key
--    (worker/src/garmin_sync/coach/rate_limit.py) and its own comment says
--    "Service-role only", but PUBLIC EXECUTE made it callable by anyone, with an
--    attacker-chosen p_user_id. Each call INSERTs a row into coach_rate_limits for
--    that user, so an unauthenticated caller could burn another athlete's 1000/day
--    coach budget and block their plan/session generation. Revoking is safe: no
--    frontend code calls this RPC (verified by grep across app/, lib/, components/).
--
-- 2. admin_* (E18, 20260708-20260709) + is_admin_caller — defense in depth. Each one
--    already starts with `if not public.is_admin_caller() then raise ...`, and
--    is_admin_caller() resolves auth.uid() = null for anon, so they are not
--    exploitable today. But nothing here should be reachable without a session at
--    all: the guard should be the second line of defense, not the only one. The
--    `authenticated` grant is kept — an admin is an authenticated user.
--
-- 3. is_feature_flag_active stays executable by authenticated (read-only flag check),
--    with PUBLIC revoked so anon cannot enumerate flags.

-- =========================================
-- 1. Coach rate limit — service_role only, for real this time
-- =========================================

revoke execute on function
  public.check_and_log_coach_rate_limit(uuid, text, integer, integer)
  from public, anon, authenticated;

-- =========================================
-- 2. E18 admin RPCs — authenticated only (guard stays the second line of defense)
-- =========================================

revoke execute on function public.is_admin_caller() from public, anon;
revoke execute on function public.admin_overview() from public, anon;
revoke execute on function public.admin_list_allowed_emails() from public, anon;
revoke execute on function public.admin_add_allowed_email(text, text) from public, anon;
revoke execute on function public.admin_remove_allowed_email(text) from public, anon;
revoke execute on function public.admin_list_feature_flags() from public, anon;
revoke execute on function public.admin_set_feature_flag(text, boolean, timestamptz)
  from public, anon;

-- =========================================
-- 3. Feature flag read — authenticated only
-- =========================================

revoke execute on function public.is_feature_flag_active(text) from public, anon;

-- Re-assert the intended grants. `revoke ... from public` does not remove a direct
-- `grant ... to authenticated`, but it does remove the privilege for any role that
-- only held it through PUBLIC — so spelling the end state out here makes this
-- migration self-describing and safe to re-run. All idempotent.
grant execute on function public.is_admin_caller() to authenticated;
grant execute on function public.admin_overview() to authenticated;
grant execute on function public.admin_list_allowed_emails() to authenticated;
grant execute on function public.admin_add_allowed_email(text, text) to authenticated;
grant execute on function public.admin_remove_allowed_email(text) to authenticated;
grant execute on function public.admin_list_feature_flags() to authenticated;
grant execute on function public.admin_set_feature_flag(text, boolean, timestamptz)
  to authenticated;
grant execute on function public.is_feature_flag_active(text) to authenticated;
grant execute on function
  public.check_and_log_coach_rate_limit(uuid, text, integer, integer)
  to service_role;
