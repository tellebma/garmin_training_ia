-- Fix : la table athlete_profiles n'avait que des policies SELECT et UPDATE.
-- supabase.from(...).upsert(..., { onConflict: 'user_id' }) déclenche un
-- INSERT ... ON CONFLICT DO UPDATE côté PostgreSQL — qui nécessite la policy
-- INSERT pour passer, même si la row existe déjà (via le trigger handle_new_user).
-- Sans cette policy, l'upsert échouait silencieusement avec une erreur RLS.

create policy "users insert own profile"
  on public.athlete_profiles for insert
  with check (auth.uid() = user_id);
