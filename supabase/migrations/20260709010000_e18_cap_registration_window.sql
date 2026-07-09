-- 20260709010000_e18_cap_registration_window.sql
-- Cap public_registration_enabled's expiry window at 7 days, matching the
-- longest option already offered by the admin UI's duration picker — a
-- typo'd p_expires_at (e.g. +10 years) must not silently leave public
-- registration open indefinitely.
create or replace function public.admin_set_feature_flag(
  p_key text,
  p_enabled boolean,
  p_expires_at timestamptz
)
returns public.feature_flags
language plpgsql
security definer
set search_path = ''
as $$
declare
  updated public.feature_flags;
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  if p_key = 'public_registration_enabled' and p_enabled then
    if p_expires_at is null then
      raise exception 'public_registration_enabled requires an expiration when enabled';
    end if;
    if p_expires_at > now() + interval '7 days' then
      raise exception 'public_registration_enabled window cannot exceed 7 days';
    end if;
  end if;

  update public.feature_flags
  set enabled = p_enabled,
      expires_at = p_expires_at,
      updated_at = now(),
      updated_by = auth.uid()
  where key = p_key
  returning * into updated;

  if updated.key is null then
    raise exception 'unknown feature flag: %', p_key;
  end if;
  return updated;
end;
$$;

grant execute on function public.admin_set_feature_flag(text, boolean, timestamptz) to authenticated;
