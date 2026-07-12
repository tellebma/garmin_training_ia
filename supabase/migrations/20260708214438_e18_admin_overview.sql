-- 20260708040000_e18_admin_overview.sql
create or replace function public.admin_overview()
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  result jsonb;
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;

  select jsonb_build_object(
    'users', jsonb_build_object(
      'total', (select count(*) from public.athlete_profiles),
      'active_7d', (
        select count(distinct user_id) from (
          select user_id from public.activities where start_time > now() - interval '7 days'
          union
          select user_id from public.garmin_credentials where last_sync_at > now() - interval '7 days'
        ) active
      )
    ),
    'activities', jsonb_build_object(
      'total', (select count(*) from public.activities),
      'last_7d', (select count(*) from public.activities where start_time > now() - interval '7 days')
    ),
    'llm_estimated', jsonb_build_object(
      'total_tokens_7d', (
        select coalesce(sum(total_tokens), 0) from public.llm_usage
        where created_at > now() - interval '7 days'
      ),
      'cost_usd_7d', (
        select coalesce(sum(cost_usd), 0) from public.llm_usage
        where created_at > now() - interval '7 days'
      )
    ),
    'llm_billed', jsonb_build_object(
      'cost_usd_7d', (
        select coalesce(sum(cost_usd), 0) from public.openai_billing_snapshot
        where billing_date > (current_date - interval '7 days')
      )
    ),
    'sync_health', jsonb_build_object(
      'ok', (select count(*) from public.garmin_credentials where last_sync_status = 'ok'),
      'failed', (
        select count(*) from public.garmin_credentials
        where last_sync_status is not null and last_sync_status != 'ok'
      )
    ),
    'cost_per_day_7d', (
      select coalesce(jsonb_agg(jsonb_build_object('date', d.date, 'cost_usd', coalesce(u.cost_usd, 0))), '[]'::jsonb)
      from (
        select (current_date - i)::date as date from generate_series(0, 6) as i
      ) d
      left join (
        select created_at::date as date, sum(cost_usd) as cost_usd
        from public.llm_usage
        where created_at > now() - interval '7 days'
        group by created_at::date
      ) u on u.date = d.date
      order by d.date
    )
  ) into result;

  return result;
end;
$$;

grant execute on function public.admin_overview() to authenticated;
