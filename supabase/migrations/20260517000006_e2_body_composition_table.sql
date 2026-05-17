-- E2 — body composition — one row per (user, date)
create table public.body_composition (
  user_id uuid not null references auth.users(id) on delete cascade,
  date date not null,
  weight_kg numeric(5,2) check (weight_kg is null or weight_kg between 20 and 300),
  body_fat_pct numeric(4,1) check (body_fat_pct is null or body_fat_pct between 1 and 70),
  muscle_mass_kg numeric(5,2),
  bone_mass_kg numeric(4,2),
  body_water_pct numeric(4,1),
  visceral_fat numeric(4,1),
  bmi numeric(4,1),
  raw jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  primary key (user_id, date)
);

create index body_composition_user_date_idx on public.body_composition (user_id, date desc);

alter table public.body_composition enable row level security;

create policy "users read own body_composition"
  on public.body_composition for select
  using (auth.uid() = user_id);
