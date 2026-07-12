-- 20260708010000_e18_admin_table.sql
-- E18 — admin gate: dedicated table (never a column on athlete_profiles, which
-- already has user-editable RLS policies; never a hardcoded email in SQL).

create table public.admins (
  user_id    uuid primary key references auth.users(id) on delete cascade,
  note       text,
  created_at timestamptz not null default now()
);

alter table public.admins enable row level security;
-- Pas de policies : RLS deny-all. Accès uniquement via RPCs security definer.

-- Seed : l'owner devient admin au déploiement de la migration.
insert into public.admins (user_id, note)
select id, 'owner'
from auth.users
where lower(email) = 'pdmtc.bellet@gmail.com'
on conflict (user_id) do nothing;

create or replace function public.is_admin_caller()
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from public.admins where user_id = auth.uid())
$$;

grant execute on function public.is_admin_caller() to authenticated;
