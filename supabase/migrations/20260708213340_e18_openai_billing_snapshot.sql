-- 20260708030000_e18_openai_billing_snapshot.sql
create table public.openai_billing_snapshot (
  billing_date date primary key,
  cost_usd     numeric(10,6) not null check (cost_usd >= 0),
  fetched_at   timestamptz not null default now()
);

alter table public.openai_billing_snapshot enable row level security;
-- Pas de policies : RLS deny-all. Lecture uniquement via admin_overview() (Task 8).
