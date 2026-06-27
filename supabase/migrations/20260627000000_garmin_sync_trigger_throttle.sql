-- 20260627000000_garmin_sync_trigger_throttle.sql
-- E15.3: garde-fou anti-spam pour la sync on-demand.
-- Une colonne timestamp + un claim atomique (check + set en une requête).

alter table public.garmin_credentials
  add column if not exists last_sync_trigger_at timestamptz;

comment on column public.garmin_credentials.last_sync_trigger_at is
  'Dernière tentative de sync on-demand (claim). Sert au cooldown E15.3.';

-- RPC: try_claim_garmin_sync
-- Réserve atomiquement un créneau de sync. Renvoie un jsonb tri-état :
--   {"outcome":"claimed"}                                  -> créneau réservé
--   {"outcome":"cooldown","retry_after_seconds":N}         -> trop tôt
--   {"outcome":"no_credentials"}                           -> pas de ligne credentials
create or replace function public.try_claim_garmin_sync(
  p_user_id uuid,
  p_window_seconds integer
)
returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
  v_claimed timestamptz;
  v_last timestamptz;
begin
  -- Claim atomique : ne matche que si jamais déclenché ou hors fenêtre.
  update public.garmin_credentials
  set last_sync_trigger_at = now()
  where user_id = p_user_id
    and (last_sync_trigger_at is null
         or last_sync_trigger_at < now() - make_interval(secs => p_window_seconds))
  returning last_sync_trigger_at into v_claimed;

  if v_claimed is not null then
    return jsonb_build_object('outcome', 'claimed');
  end if;

  -- Pas de claim : distinguer cooldown vs absence de credentials.
  select last_sync_trigger_at into v_last
  from public.garmin_credentials
  where user_id = p_user_id;

  if not found then
    return jsonb_build_object('outcome', 'no_credentials');
  end if;

  return jsonb_build_object(
    'outcome', 'cooldown',
    'retry_after_seconds',
    greatest(0, p_window_seconds - floor(extract(epoch from (now() - v_last)))::integer)
  );
end;
$$;

-- Service-role uniquement (le worker). Pas d'exposition anon/authenticated
-- (évite un nouvel avertissement SECURITY DEFINER côté advisors).
revoke execute on function public.try_claim_garmin_sync(uuid, integer) from public;
revoke execute on function public.try_claim_garmin_sync(uuid, integer) from anon;
revoke execute on function public.try_claim_garmin_sync(uuid, integer) from authenticated;
grant execute on function public.try_claim_garmin_sync(uuid, integer) to service_role;

comment on function public.try_claim_garmin_sync is
  'Claim atomique anti-spam pour la sync on-demand E15.3. Service-role only.';
