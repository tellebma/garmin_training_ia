-- Issue #170 — body_battery_high recevait bodyBatteryMostRecentValue (le niveau
-- au moment du sync, en soirée) au lieu de bodyBatteryHighestValue (le pic du
-- jour). Le mapping est corrigé côté worker ; la valeur « la plus récente »
-- reste utile pour la tuile /today, donc elle obtient sa propre colonne.
alter table public.daily_metrics
  add column if not exists body_battery_current integer
    check (body_battery_current is null or body_battery_current between 0 and 100);

comment on column public.daily_metrics.body_battery_high is
  'Pic Body Battery du jour (Garmin bodyBatteryHighestValue).';
comment on column public.daily_metrics.body_battery_current is
  'Body Battery au moment du sync (Garmin bodyBatteryMostRecentValue).';
