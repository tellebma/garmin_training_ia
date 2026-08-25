-- E24 — Exclure une activité de l'historique et des statistiques.
--
-- Cas vécu : compteur GPS du vélo lancé en mode activité EN PLUS de la montre le jour de la
-- course. Un seul effort, deux lignes `activities` : TSS compté deux fois, volume gonflé,
-- charge faussée, et la vue course qui additionne deux fois la partie vélo.
--
-- Exclusion RÉVERSIBLE, pas suppression physique : l'activité existe toujours chez Garmin,
-- un `delete` serait annulé au sync suivant par l'upsert. La colonne ci-dessous n'est produite
-- par aucun transformer, donc `ON CONFLICT DO UPDATE SET` ne la réécrit jamais : l'exclusion
-- survit à toutes les resynchronisations.

alter table public.activities
  add column if not exists excluded_at timestamptz,
  add column if not exists excluded_reason text
    check (excluded_reason is null or char_length(excluded_reason) <= 200);

comment on column public.activities.excluded_at is
  'Activité retirée de l''historique et des statistiques (soft delete réversible). '
  'NULL = activité comptée normalement.';
comment on column public.activities.excluded_reason is
  'Motif facultatif saisi par l''athlète (ex. « doublon compteur vélo »).';

-- Les lectures qui comptent filtrent toutes sur `excluded_at is null` : l'index partiel
-- garde ce chemin aussi rapide qu'avant l'ajout de la colonne.
create index if not exists activities_user_counted_idx
  on public.activities (user_id, start_time desc)
  where excluded_at is null;

-- =========================================
-- Écriture — la RLS d'`activities` n'autorise que la lecture côté client
-- =========================================

create or replace function public.set_activity_excluded(
  p_activity_id uuid,
  p_excluded boolean,
  p_reason text default null
)
returns void
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user uuid := auth.uid();
begin
  if v_user is null then
    raise exception 'not authorized';
  end if;

  update public.activities
     set excluded_at = case when p_excluded then now() else null end,
         excluded_reason = case when p_excluded then left(p_reason, 200) else null end
   where id = p_activity_id
     and user_id = v_user;

  if not found then
    raise exception 'activity not found';
  end if;
end;
$$;

-- Postgres accorde EXECUTE à PUBLIC par défaut : le `grant` seul ne restreint rien (piège SEC-2).
revoke execute on function public.set_activity_excluded(uuid, boolean, text) from public, anon;
grant execute on function public.set_activity_excluded(uuid, boolean, text) to authenticated;
