-- 20260708020000_e18_llm_usage.sql
create table public.llm_usage (
  id                bigserial primary key,
  user_id           uuid references auth.users(id) on delete set null,
  created_at        timestamptz not null default now(),
  feature           text not null,        -- 'session_workout' in V1 (see spec §0.1)
  model             text not null,        -- e.g. 'gpt-4o-mini'
  prompt_tokens     integer not null check (prompt_tokens >= 0),
  completion_tokens integer not null check (completion_tokens >= 0),
  total_tokens      integer not null check (total_tokens >= 0),
  cost_usd          numeric(10,6) not null check (cost_usd >= 0)
);

create index llm_usage_created_idx on public.llm_usage (created_at desc);
create index llm_usage_feature_created_idx on public.llm_usage (feature, created_at desc);

alter table public.llm_usage enable row level security;
-- Pas de policies : RLS deny-all. Lecture uniquement via admin_overview() (Task 8).
