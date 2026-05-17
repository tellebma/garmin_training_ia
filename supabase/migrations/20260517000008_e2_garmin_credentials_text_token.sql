-- Convert oauth_tokens_encrypted to text. Fernet output is already
-- URL-safe base64 (ASCII), so bytea was an unnecessary complication
-- and triggered encoding bugs at the supabase-py boundary.
alter table public.garmin_credentials
  alter column oauth_tokens_encrypted type text
  using convert_from(oauth_tokens_encrypted, 'UTF8');
