-- 20260521010000_e7_garmin_sync_status.sql
-- Stocke le dernier statut de sync Garmin pour afficher des messages utilisateur
-- (ex: profil Garmin incomplet, display_name manquant)

alter table public.garmin_credentials
  add column if not exists last_sync_status text,
  add column if not exists last_sync_status_at timestamptz,
  add column if not exists last_sync_error_message text;

comment on column public.garmin_credentials.last_sync_status is
  'ok | garmin_no_display_name | auth_failed | rate_limited | unknown_error';
comment on column public.garmin_credentials.last_sync_status_at is
  'When last_sync_status was last updated.';
comment on column public.garmin_credentials.last_sync_error_message is
  'Free-text error detail from worker, displayed to user via banner.';
