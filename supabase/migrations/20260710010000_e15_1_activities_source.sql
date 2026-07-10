-- E15.1 — generalize `activities` to support multiple ingestion sources.
alter table public.activities
  add column source text not null default 'garmin' check (source in ('garmin', 'strava')),
  add column strava_activity_id bigint,
  alter column garmin_activity_id drop not null;

alter table public.activities
  drop constraint activities_user_id_garmin_activity_id_key;

-- Not partial: PostgREST's on_conflict=col1,col2 upsert param always emits a
-- plain ON CONFLICT (col1, col2) with no WHERE clause, which cannot match a
-- partial index as its arbiter. NULL <> NULL for uniqueness purposes, so a
-- plain index here still never collides across sources (garmin rows have
-- strava_activity_id null and vice versa, enforced below).
create unique index activities_user_garmin_uidx
  on public.activities (user_id, garmin_activity_id);

-- See comment above activities_user_garmin_uidx — same reasoning.
create unique index activities_user_strava_uidx
  on public.activities (user_id, strava_activity_id);

alter table public.activities
  add constraint activities_garmin_id_check
    check (source <> 'garmin' or garmin_activity_id is not null),
  add constraint activities_strava_id_check
    check (source <> 'strava' or strava_activity_id is not null);

create index activities_user_source_idx on public.activities (user_id, source);
