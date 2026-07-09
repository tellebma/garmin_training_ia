create or replace function public.is_email_allowed(p_email text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select
    exists (select 1 from public.allowed_emails where email = lower(p_email))
    or public.is_feature_flag_active('public_registration_enabled')
$$;
