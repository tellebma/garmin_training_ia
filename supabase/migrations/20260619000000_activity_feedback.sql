-- Ressenti subjectif post-seance, complementaire aux metriques Garmin.
-- Le session-RPE est calcule a la lecture avec la duree de l'activite.

create table if not exists public.activity_feedback (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  activity_id uuid not null references public.activities(id) on delete cascade,
  rpe smallint not null check (rpe between 1 and 10),
  fatigue smallint check (fatigue is null or fatigue between 1 and 5),
  soreness smallint check (soreness is null or soreness between 1 and 5),
  pain smallint check (pain is null or pain between 0 and 5),
  mood smallint check (mood is null or mood between 1 and 5),
  perceived_difficulty text check (
    perceived_difficulty is null
    or perceived_difficulty in ('easier', 'as_expected', 'harder')
  ),
  pain_area text check (pain_area is null or char_length(pain_area) <= 120),
  comment text check (comment is null or char_length(comment) <= 500),
  schema_version smallint not null default 1,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  constraint activity_feedback_user_activity_unique unique (user_id, activity_id)
);

create index if not exists activity_feedback_user_updated_idx
  on public.activity_feedback (user_id, updated_at desc);

alter table public.activity_feedback enable row level security;

create policy "users read own activity feedback"
  on public.activity_feedback for select
  using (auth.uid() = user_id);

create policy "users insert own activity feedback"
  on public.activity_feedback for insert
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.activities
      where activities.id = activity_feedback.activity_id
        and activities.user_id = auth.uid()
    )
  );

create policy "users update own activity feedback"
  on public.activity_feedback for update
  using (auth.uid() = user_id)
  with check (
    auth.uid() = user_id
    and exists (
      select 1
      from public.activities
      where activities.id = activity_feedback.activity_id
        and activities.user_id = auth.uid()
    )
  );

create policy "users delete own activity feedback"
  on public.activity_feedback for delete
  using (auth.uid() = user_id);

drop trigger if exists trg_activity_feedback_updated_at on public.activity_feedback;
create trigger trg_activity_feedback_updated_at
  before update on public.activity_feedback
  for each row execute procedure public.touch_updated_at();

comment on table public.activity_feedback is
  'Ressenti post-seance saisi par l athlete pour completer la charge Garmin.';
comment on column public.activity_feedback.rpe is
  'Effort global percu sur une echelle CR10 simplifiee de 1 a 10.';
comment on column public.activity_feedback.perceived_difficulty is
  'Difficulte ressentie par rapport a la seance prevue.';
