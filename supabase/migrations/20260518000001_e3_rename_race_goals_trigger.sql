-- E3 follow-up : align race_goals trigger with project convention (trg_<table>_updated_at + execute procedure)
drop trigger if exists touch_race_goals_updated_at on public.race_goals;
drop trigger if exists trg_race_goals_updated_at on public.race_goals;
create trigger trg_race_goals_updated_at before update on public.race_goals
  for each row execute procedure public.touch_updated_at();
