-- E1 — Foundations & Auth — initial schema
-- Creates the bare-minimum tables required for the auth flow and profile bootstrap.
-- Other tables (activities, plans, etc.) are added in their respective EPICs.

-- =========================================
-- Table: athlete_profiles
-- One row per authenticated user. Created on first login.
-- =========================================
create table public.athlete_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  first_name text,
  dob date,
  sex text check (sex in ('M', 'F', 'X') or sex is null),
  city text,
  country text,
  lat numeric(9,6),
  lon numeric(9,6),
  ftp_watts integer check (ftp_watts is null or ftp_watts between 50 and 600),
  vma_kmh numeric(4,2) check (vma_kmh is null or vma_kmh between 5 and 30),
  fc_max_bpm integer check (fc_max_bpm is null or fc_max_bpm between 100 and 230),
  sports_strengths jsonb default '{}'::jsonb,
  available_days jsonb default '[]'::jsonb,
  consent_data_processing boolean not null default false,
  consent_signed_at timestamptz,
  onboarding_completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================================
-- Table: garmin_credentials
-- One row per user. Tokens stored encrypted.
-- =========================================
create table public.garmin_credentials (
  user_id uuid primary key references auth.users(id) on delete cascade,
  oauth_tokens_encrypted bytea,
  last_sync_at timestamptz,
  last_sync_status text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================================
-- Function: auto-create athlete_profile on signup
-- =========================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.athlete_profiles (user_id)
  values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- =========================================
-- Row Level Security
-- =========================================
alter table public.athlete_profiles enable row level security;
alter table public.garmin_credentials enable row level security;

-- athlete_profiles policies
create policy "users read own profile"
  on public.athlete_profiles for select
  using (auth.uid() = user_id);

create policy "users update own profile"
  on public.athlete_profiles for update
  using (auth.uid() = user_id);

-- garmin_credentials policies
create policy "users read own credentials"
  on public.garmin_credentials for select
  using (auth.uid() = user_id);

create policy "users insert own credentials"
  on public.garmin_credentials for insert
  with check (auth.uid() = user_id);

create policy "users update own credentials"
  on public.garmin_credentials for update
  using (auth.uid() = user_id);

create policy "users delete own credentials"
  on public.garmin_credentials for delete
  using (auth.uid() = user_id);

-- =========================================
-- Updated_at trigger
-- =========================================
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trg_athlete_profiles_updated_at
  before update on public.athlete_profiles
  for each row execute procedure public.touch_updated_at();

create trigger trg_garmin_credentials_updated_at
  before update on public.garmin_credentials
  for each row execute procedure public.touch_updated_at();
