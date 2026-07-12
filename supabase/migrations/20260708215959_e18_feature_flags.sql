-- 20260708050000_e18_feature_flags.sql
create table public.feature_flags (
  key         text primary key,
  enabled     boolean not null default false,
  expires_at  timestamptz,
  description text not null,
  updated_at  timestamptz not null default now(),
  updated_by  uuid references auth.users(id) on delete set null
);

alter table public.feature_flags enable row level security;
-- Pas de policies : RLS deny-all. Accès via is_feature_flag_active() (lecture ciblée,
-- large) et admin_list/set_feature_flag() (lecture/écriture complète, admin only).

insert into public.feature_flags (key, enabled, description) values
  ('llm_generation_enabled', true, 'Kill switch : coupe la génération IA (séances) si actif=false'),
  ('maintenance_mode', false, 'Bloque l''app pour tout le monde sauf les admins'),
  ('public_registration_enabled', false, 'Bypass temporaire de l''allowlist à l''inscription (expiration obligatoire)')
on conflict (key) do nothing;

create or replace function public.is_feature_flag_active(p_key text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select coalesce(
    (select enabled and (expires_at is null or expires_at > now())
     from public.feature_flags where key = p_key),
    false
  )
$$;

grant execute on function public.is_feature_flag_active(text) to authenticated;

create or replace function public.admin_list_feature_flags()
returns setof public.feature_flags
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  return query select * from public.feature_flags order by key;
end;
$$;

grant execute on function public.admin_list_feature_flags() to authenticated;

create or replace function public.admin_set_feature_flag(
  p_key text,
  p_enabled boolean,
  p_expires_at timestamptz
)
returns public.feature_flags
language plpgsql
security definer
set search_path = public
as $$
declare
  updated public.feature_flags;
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  if p_key = 'public_registration_enabled' and p_enabled and p_expires_at is null then
    raise exception 'public_registration_enabled requires an expiration when enabled';
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
