-- 20260524000000_e6_briefing_rate_limit.sql
-- E6: add 'daily_briefing' to allowed actions on coach_rate_limits.

alter table public.coach_rate_limits
  drop constraint coach_rate_limits_action_check;

alter table public.coach_rate_limits
  add constraint coach_rate_limits_action_check
  check (action in ('ensure_sessions', 'regenerate_session', 'daily_briefing'));
