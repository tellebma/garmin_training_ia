-- 20260519000000_eauth_password_set_allowlist.sql
-- E-Auth refactor : passage magic-link → email/password

-- =========================================
-- Table: allowed_emails (M5 — lowercase only)
-- =========================================
create table if not exists public.allowed_emails (
  email text primary key,
  invited_by uuid references auth.users(id) on delete set null,
  note text,
  created_at timestamptz not null default now(),
  constraint allowed_emails_lowercase check (email = lower(email))
);

create index if not exists allowed_emails_created_at_idx
  on public.allowed_emails (created_at desc);

alter table public.allowed_emails enable row level security;
-- Pas de policies : RLS deny-all. Accès uniquement via RPCs security definer.

-- =========================================
-- Alter: athlete_profiles.password_set (moved up — email_needs_signup depends on it)
-- =========================================
alter table public.athlete_profiles
  add column if not exists password_set boolean not null default false;

comment on column public.athlete_profiles.password_set is
  'True after the user has chosen a password via /auth/set-password. False = magic-link-only user (legacy or freshly registered).';

-- =========================================
-- RPC: is_email_allowed (case-insensitive)
-- =========================================
create or replace function public.is_email_allowed(p_email text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from public.allowed_emails where email = lower(p_email))
$$;

grant execute on function public.is_email_allowed(text) to anon, authenticated;

-- =========================================
-- RPC: email_needs_signup (I3 — anti-spam OTP)
-- =========================================
create or replace function public.email_needs_signup(p_email text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  with allowed as (
    select 1 from public.allowed_emails where email = lower(p_email)
  ),
  active_user as (
    select 1
    from auth.users u
    join public.athlete_profiles p on p.user_id = u.id
    where lower(u.email) = lower(p_email)
      and p.password_set = true
  )
  select exists (select 1 from allowed) and not exists (select 1 from active_user)
$$;

grant execute on function public.email_needs_signup(text) to anon, authenticated;

-- =========================================
-- Table: auth_rate_limits (I1)
-- =========================================
create table if not exists public.auth_rate_limits (
  id bigserial primary key,
  ip text not null,
  action text not null,
  created_at timestamptz not null default now()
);

create index if not exists auth_rate_limits_ip_action_created_idx
  on public.auth_rate_limits (ip, action, created_at desc);

alter table public.auth_rate_limits enable row level security;

-- =========================================
-- RPC: check_and_log_auth_rate_limit (I1)
-- =========================================
create or replace function public.check_and_log_auth_rate_limit(
  p_ip text,
  p_action text,
  p_max_count integer,
  p_window_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count integer;
  v_daily_count integer;
begin
  select count(*) into v_daily_count
  from public.auth_rate_limits
  where ip = p_ip and created_at > now() - interval '24 hours';
  if v_daily_count >= 1000 then
    return false;
  end if;

  select count(*) into v_count
  from public.auth_rate_limits
  where ip = p_ip
    and action = p_action
    and created_at > now() - make_interval(secs => p_window_seconds);

  if v_count >= p_max_count then
    return false;
  end if;

  insert into public.auth_rate_limits (ip, action) values (p_ip, p_action);

  if random() < 0.01 then
    delete from public.auth_rate_limits where created_at < now() - interval '7 days';
  end if;

  return true;
end
$$;

grant execute on function public.check_and_log_auth_rate_limit(text, text, integer, integer)
  to anon, authenticated;

-- =========================================
-- Table: auth_events (I5 — audit log)
-- =========================================
create table if not exists public.auth_events (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null check (event_type in (
    'register_initiated',
    'password_set',
    'password_reset_requested',
    'password_reset_completed',
    'login_success',
    'login_failure'
  )),
  ip text,
  user_agent text,
  email text,
  created_at timestamptz not null default now()
);

create index if not exists auth_events_user_created_idx
  on public.auth_events (user_id, created_at desc);
create index if not exists auth_events_event_created_idx
  on public.auth_events (event_type, created_at desc);

alter table public.auth_events enable row level security;

-- =========================================
-- RPC: log_auth_event (I5)
-- =========================================
create or replace function public.log_auth_event(
  p_user_id uuid,
  p_event_type text,
  p_ip text,
  p_user_agent text,
  p_email text
)
returns void
language sql
security definer
set search_path = public
as $$
  insert into public.auth_events (user_id, event_type, ip, user_agent, email)
  values (p_user_id, p_event_type, p_ip, p_user_agent, lower(p_email))
$$;

grant execute on function public.log_auth_event(uuid, text, text, text, text)
  to anon, authenticated;

-- =========================================
-- Seed: owner dans allowed_emails
-- =========================================
insert into public.allowed_emails (email, note)
values ('pdmtc.bellet@gmail.com', 'owner — legacy magic-link user')
on conflict (email) do nothing;
