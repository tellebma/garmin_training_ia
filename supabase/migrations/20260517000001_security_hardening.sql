-- Security hardening — fixes Supabase advisor warnings raised after initial_schema:
--   - touch_updated_at had a mutable search_path (lint 0011)
--   - handle_new_user (SECURITY DEFINER) was callable by anon/authenticated via
--     /rest/v1/rpc/handle_new_user (lints 0028, 0029). It must only run via the
--     auth.users insert trigger, never from the REST API.

-- 1. Lock search_path on touch_updated_at
alter function public.touch_updated_at()
  set search_path = public;

-- 2. Revoke EXECUTE on handle_new_user from all REST roles
revoke execute on function public.handle_new_user() from public;
revoke execute on function public.handle_new_user() from anon;
revoke execute on function public.handle_new_user() from authenticated;
