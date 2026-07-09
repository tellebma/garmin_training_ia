-- 20260709000000_e18_harden_search_path.sql
-- Harden E18's SECURITY DEFINER functions: search_path = '' instead of 'public'.
-- All object references in these functions are already fully qualified
-- (public.admins, auth.uid(), auth.users, etc.), so this is defense-in-depth
-- against search_path hijacking, not a behavior change.

alter function public.is_admin_caller() set search_path = '';
alter function public.admin_overview() set search_path = '';
alter function public.is_feature_flag_active(text) set search_path = '';
alter function public.admin_list_feature_flags() set search_path = '';
alter function public.admin_set_feature_flag(text, boolean, timestamptz) set search_path = '';
alter function public.is_email_allowed(text) set search_path = '';
alter function public.admin_list_allowed_emails() set search_path = '';
alter function public.admin_add_allowed_email(text, text) set search_path = '';
alter function public.admin_remove_allowed_email(text) set search_path = '';
