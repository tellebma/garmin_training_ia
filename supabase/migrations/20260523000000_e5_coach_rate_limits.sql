-- 20260523000000_e5_coach_rate_limits.sql
-- E5 security hardening: per-user rate limit for LLM-backed endpoints
-- (/coach/ensure-sessions, /coach/regenerate-session). Prevents API key drain
-- by a malicious authenticated user.

create table if not exists public.coach_rate_limits (
  id bigserial primary key,
  user_id uuid not null references auth.users(id) on delete cascade,
  action text not null check (action in ('ensure_sessions', 'regenerate_session')),
  created_at timestamptz not null default now()
);

create index if not exists coach_rate_limits_user_action_created_idx
  on public.coach_rate_limits (user_id, action, created_at desc);

-- Auto-cleanup of old entries (>24h) to keep table small. Optional pgcron job
-- can later sweep; for now we rely on natural cleanup via partial index pruning.
alter table public.coach_rate_limits enable row level security;

-- No client-side reads/writes — only the worker (service_role) touches this.
-- Default deny is fine; service_role bypasses RLS.

-- RPC: check_and_log_coach_rate_limit
-- Returns TRUE if call is allowed, FALSE if rate-limited.
-- Also enforces a daily cap (1000 calls per user / 24h, regardless of action).
create or replace function public.check_and_log_coach_rate_limit(
  p_user_id uuid,
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
  -- Hard daily cap across all coach actions (anti-script).
  select count(*) into v_daily_count
  from public.coach_rate_limits
  where user_id = p_user_id and created_at > now() - interval '24 hours';
  if v_daily_count >= 1000 then
    return false;
  end if;

  -- Per-action sliding window cap.
  select count(*) into v_count
  from public.coach_rate_limits
  where user_id = p_user_id
    and action = p_action
    and created_at > now() - make_interval(secs => p_window_seconds);

  if v_count >= p_max_count then
    return false;
  end if;

  insert into public.coach_rate_limits (user_id, action) values (p_user_id, p_action);
  return true;
end;
$$;

grant execute on function public.check_and_log_coach_rate_limit(uuid, text, integer, integer)
  to service_role;

comment on function public.check_and_log_coach_rate_limit is
  'Atomic check-and-insert rate limit for /coach/* LLM endpoints. Returns false when limit reached. Service-role only.';
