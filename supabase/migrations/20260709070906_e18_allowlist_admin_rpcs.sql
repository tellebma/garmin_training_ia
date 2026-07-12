-- 20260708070000_e18_allowlist_admin_rpcs.sql
create or replace function public.admin_list_allowed_emails()
returns table (
  email text,
  note text,
  invited_by uuid,
  created_at timestamptz,
  status text,
  registered_at timestamptz
)
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  return query
    select
      a.email,
      a.note,
      a.invited_by,
      a.created_at,
      case when p.password_set then 'active' else 'pending' end as status,
      case when p.password_set then p.updated_at else null end as registered_at
    from public.allowed_emails a
    left join auth.users u on lower(u.email) = a.email
    left join public.athlete_profiles p on p.user_id = u.id
    order by a.created_at desc;
end;
$$;

grant execute on function public.admin_list_allowed_emails() to authenticated;

create or replace function public.admin_add_allowed_email(p_email text, p_note text)
returns public.allowed_emails
language plpgsql
security definer
set search_path = public
as $$
declare
  inserted public.allowed_emails;
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  insert into public.allowed_emails (email, note, invited_by)
  values (lower(p_email), p_note, auth.uid())
  on conflict (email) do update set note = excluded.note
  returning * into inserted;
  return inserted;
end;
$$;

grant execute on function public.admin_add_allowed_email(text, text) to authenticated;

create or replace function public.admin_remove_allowed_email(p_email text)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  if not public.is_admin_caller() then
    raise exception 'not authorized';
  end if;
  delete from public.allowed_emails where email = lower(p_email);
end;
$$;

grant execute on function public.admin_remove_allowed_email(text) to authenticated;
