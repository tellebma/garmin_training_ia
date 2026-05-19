# E-Auth Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer le flow magic-link-only par email/password + allowlist + rate-limit IP + audit log, en intégrant toutes les findings Critical/Important/Minor de l'audit Red/Blue Team du spec.

**Architecture:** 3 tables Supabase (`allowed_emails`, `auth_rate_limits`, `auth_events`) + 4 RPCs `security definer` (anti-leak via grant minimal). 5 Server Actions Next.js avec rate limit IP, audit log et anti-timing 800ms intégrés par défaut. Callback `next` whitelist (anti open-redirect). UI : 5 pages (`/login` refactor, `/register`, `/forgot-password`, `/auth/set-password`, `/auth/reset-password`).

**Tech Stack:**
- Frontend : Next.js 15 (App Router), TypeScript strict++, Zod, supabase-js, sonner
- DB : Supabase Postgres + RLS, migrations dans `supabase/migrations/`
- Tests : Vitest avec mocks Supabase (frontend unit + Server Actions)
- Email : templates FR HTML dans `supabase/email-templates/` (config manuelle via Studio post-merge)

**Spec source :** [`docs/superpowers/specs/2026-05-19-eauth-refactor-design.md`](../specs/2026-05-19-eauth-refactor-design.md)

---

## Pré-requis avant de démarrer

- Branche dédiée : `git checkout main && git pull && git checkout -b feat/eauth-refactor`
- Worker actuel intouché (l'auth n'impacte pas Python worker)
- Frontend en local : `pnpm dev` → http://localhost:3000
- Variables d'env locales `.env.local` : clés Supabase déjà OK depuis E1
- Supabase MCP utilisable pour migrations + verif

**⚠️ Étape Owner Pre-Deploy (C3) — à faire MANUELLEMENT après Task 1 (migration DB) et AVANT de toucher le code frontend** :

1. Aller sur Supabase Studio → Authentication → Users → cliquer sur l'owner `pdmtc.bellet@gmail.com` → "Send password recovery"
2. Recevoir l'email magic-link sur sa boîte
3. Cliquer le lien → arriver sur `/auth/callback` (existant) → être logué via magic-link legacy
4. Maintenant via Supabase Studio → SQL Editor, exécuter :
   ```sql
   update public.athlete_profiles
   set password_set = true
   where user_id = (select id from auth.users where email = 'pdmtc.bellet@gmail.com');
   ```
5. Vérifier que `select password_set from public.athlete_profiles where user_id = ...` retourne `true`.

Cette étape ferme la fenêtre de race condition (C3 de l'audit) avant que la nouvelle UI ne soit déployée.

---

## Task 1 — Migration DB : 3 tables + 4 RPCs + alter + seed

**Files:**
- Create: `supabase/migrations/20260519000000_eauth_password_set_allowlist.sql`

- [ ] **Step 1: Créer le fichier migration**

```sql
-- 20260519000000_eauth_password_set_allowlist.sql
-- E-Auth refactor : passage magic-link → email/password
-- 3 tables (allowed_emails, auth_rate_limits, auth_events)
-- 4 RPCs security definer (is_email_allowed, email_needs_signup,
--                          check_and_log_auth_rate_limit, log_auth_event)
-- 1 alter athlete_profiles (password_set)
-- Seed owner email

-- =========================================
-- Table: allowed_emails (M5 — lowercase only)
-- =========================================
create table if not exists public.allowed_emails (
  email text primary key,
  invited_by uuid references auth.users(id) on delete set null,
  note text,
  created_at timestamptz not null default now(),
  constraint allowed_emails_lowercase check (email = lower(email))
);

create index if not exists allowed_emails_created_at_idx
  on public.allowed_emails (created_at desc);

alter table public.allowed_emails enable row level security;
-- Pas de policies : RLS deny-all. Accès uniquement via RPCs security definer.

-- =========================================
-- RPC: is_email_allowed (case-insensitive)
-- =========================================
create or replace function public.is_email_allowed(p_email text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  select exists (select 1 from public.allowed_emails where email = lower(p_email))
$$;

grant execute on function public.is_email_allowed(text) to anon, authenticated;

-- =========================================
-- RPC: email_needs_signup (I3 — anti-spam OTP)
-- Retourne true ssi : allowlisté ET (pas encore inscrit OU inscrit sans mdp)
-- =========================================
create or replace function public.email_needs_signup(p_email text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  with allowed as (
    select 1 from public.allowed_emails where email = lower(p_email)
  ),
  active_user as (
    select 1
    from auth.users u
    join public.athlete_profiles p on p.user_id = u.id
    where lower(u.email) = lower(p_email)
      and p.password_set = true
  )
  select exists (select 1 from allowed) and not exists (select 1 from active_user)
$$;

grant execute on function public.email_needs_signup(text) to anon, authenticated;

-- =========================================
-- Table: auth_rate_limits (I1)
-- =========================================
create table if not exists public.auth_rate_limits (
  id bigserial primary key,
  ip text not null,
  action text not null,
  created_at timestamptz not null default now()
);

create index if not exists auth_rate_limits_ip_action_created_idx
  on public.auth_rate_limits (ip, action, created_at desc);

alter table public.auth_rate_limits enable row level security;
-- Pas de policies : seul le RPC security definer y accède.

-- =========================================
-- RPC: check_and_log_auth_rate_limit (I1 + cleanup probabiliste)
-- =========================================
create or replace function public.check_and_log_auth_rate_limit(
  p_ip text,
  p_action text,
  p_max_count integer,
  p_window_seconds integer
)
returns boolean
language plpgsql
security definer
set search_path = public
as $$
declare
  v_count integer;
  v_daily_count integer;
begin
  -- I1 : hard cap par IP/24h (anti-DoS table elle-même)
  select count(*) into v_daily_count
  from public.auth_rate_limits
  where ip = p_ip and created_at > now() - interval '24 hours';
  if v_daily_count >= 1000 then
    return false;
  end if;

  -- Count attempts dans la fenêtre demandée
  select count(*) into v_count
  from public.auth_rate_limits
  where ip = p_ip
    and action = p_action
    and created_at > now() - make_interval(secs => p_window_seconds);

  if v_count >= p_max_count then
    return false;
  end if;

  -- Log this attempt
  insert into public.auth_rate_limits (ip, action) values (p_ip, p_action);

  -- I1 : cleanup probabiliste (1 % des calls)
  if random() < 0.01 then
    delete from public.auth_rate_limits where created_at < now() - interval '7 days';
  end if;

  return true;
end
$$;

grant execute on function public.check_and_log_auth_rate_limit(text, text, integer, integer)
  to anon, authenticated;

-- =========================================
-- Table: auth_events (I5 — audit log)
-- =========================================
create table if not exists public.auth_events (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null check (event_type in (
    'register_initiated',
    'password_set',
    'password_reset_requested',
    'password_reset_completed',
    'login_success',
    'login_failure'
  )),
  ip text,
  user_agent text,
  email text,
  created_at timestamptz not null default now()
);

create index if not exists auth_events_user_created_idx
  on public.auth_events (user_id, created_at desc);
create index if not exists auth_events_event_created_idx
  on public.auth_events (event_type, created_at desc);

alter table public.auth_events enable row level security;
-- Pas de policies : RLS deny-all, insertion via RPC.

-- =========================================
-- RPC: log_auth_event (I5)
-- =========================================
create or replace function public.log_auth_event(
  p_user_id uuid,
  p_event_type text,
  p_ip text,
  p_user_agent text,
  p_email text
)
returns void
language sql
security definer
set search_path = public
as $$
  insert into public.auth_events (user_id, event_type, ip, user_agent, email)
  values (p_user_id, p_event_type, p_ip, p_user_agent, lower(p_email))
$$;

grant execute on function public.log_auth_event(uuid, text, text, text, text)
  to anon, authenticated;

-- =========================================
-- Alter: athlete_profiles.password_set
-- =========================================
alter table public.athlete_profiles
  add column if not exists password_set boolean not null default false;

comment on column public.athlete_profiles.password_set is
  'True after the user has chosen a password via /auth/set-password. False = magic-link-only user (legacy or freshly registered).';

-- =========================================
-- Seed: owner dans allowed_emails
-- =========================================
insert into public.allowed_emails (email, note)
values ('pdmtc.bellet@gmail.com', 'owner — legacy magic-link user')
on conflict (email) do nothing;
```

- [ ] **Step 2: Appliquer la migration via Supabase MCP**

Via `mcp__supabase__apply_migration` :
- `project_id` : `peiyrqplymdlmlpsbqzu`
- `name` : `20260519000000_eauth_password_set_allowlist`
- `query` : contenu SQL ci-dessus complet

- [ ] **Step 3: Vérifier création des tables + RLS**

Via `mcp__supabase__execute_sql` :

```sql
select table_name from information_schema.tables
where table_schema = 'public'
  and table_name in ('allowed_emails', 'auth_rate_limits', 'auth_events')
order by table_name;
```
Expected: 3 rows.

```sql
select tablename, rowsecurity from pg_tables
where schemaname = 'public'
  and tablename in ('allowed_emails', 'auth_rate_limits', 'auth_events');
```
Expected: 3 rows, tous `rowsecurity = true`.

```sql
select policyname from pg_policies
where tablename in ('allowed_emails', 'auth_rate_limits', 'auth_events');
```
Expected: 0 rows (RLS deny-all sans policies = aucun accès anon/authenticated).

- [ ] **Step 4: Vérifier les 4 RPCs**

```sql
select proname, prosecdef
from pg_proc
where pronamespace = 'public'::regnamespace
  and proname in (
    'is_email_allowed', 'email_needs_signup',
    'check_and_log_auth_rate_limit', 'log_auth_event'
  )
order by proname;
```
Expected: 4 rows, tous `prosecdef = true` (security definer).

- [ ] **Step 5: Vérifier alter athlete_profiles + seed**

```sql
select column_name, data_type
from information_schema.columns
where table_schema = 'public'
  and table_name = 'athlete_profiles'
  and column_name = 'password_set';
```
Expected: 1 row.

```sql
select email, note from public.allowed_emails where email = 'pdmtc.bellet@gmail.com';
```
Expected: 1 row avec note 'owner — legacy magic-link user'.

- [ ] **Step 6: Test fonctionnel des RPCs**

```sql
select public.is_email_allowed('pdmtc.bellet@gmail.com');   -- expected: true
select public.is_email_allowed('PDMTC.Bellet@GMAIL.com');   -- expected: true (case-insensitive M5)
select public.is_email_allowed('hacker@evil.com');           -- expected: false
```

```sql
select public.email_needs_signup('hacker@evil.com');         -- expected: false (pas allowlisté)
-- (test sur owner se fait après owner pre-deploy step)
```

```sql
select public.check_and_log_auth_rate_limit('1.2.3.4', 'register', 3, 3600);  -- true, true, true, FALSE
```

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations/20260519000000_eauth_password_set_allowlist.sql
git commit -m "feat(db): add eauth tables + RPCs + password_set + allowlist seed"
```

---

## Task 2 — Owner pre-deploy (manuel, à exécuter une fois Task 1 OK)

**Files:**
- (aucun) — étape opérationnelle manuelle

- [ ] **Step 1: Send password recovery à l'owner via Supabase Studio**

1. Ouvrir https://supabase.com/dashboard/project/peiyrqplymdlmlpsbqzu
2. Authentication → Users → cliquer sur `pdmtc.bellet@gmail.com`
3. Cliquer "Send password recovery" → l'email arrive sur la boîte de l'owner

- [ ] **Step 2: Owner clique le lien → log magic-link legacy**

L'owner reçoit l'email, clique le lien, est authentifié via le flow magic-link existant `/auth/callback`. Session établie.

- [ ] **Step 3: Force `password_set = true` via SQL**

Via `mcp__supabase__execute_sql` (project `peiyrqplymdlmlpsbqzu`) :

```sql
update public.athlete_profiles
set password_set = true
where user_id = (select id from auth.users where email = 'pdmtc.bellet@gmail.com');
```

- [ ] **Step 4: Vérification**

```sql
select p.user_id, u.email, p.password_set
from public.athlete_profiles p
join auth.users u on u.id = p.user_id
where u.email = 'pdmtc.bellet@gmail.com';
```
Expected: 1 row avec `password_set = true`.

**Aucun commit nécessaire — purement opérationnel.**

---

## Task 3 — Utilitaires `lib/auth/` : `clientIp`, `sleepUntil`, `ipGuard`

**Files:**
- Create: `lib/auth/client-ip.ts`
- Create: `lib/auth/timing.ts`

- [ ] **Step 1: Créer `lib/auth/client-ip.ts`**

```typescript
// lib/auth/client-ip.ts
import { headers } from 'next/headers'

/**
 * Resolve client IP from request headers, Vercel-aware.
 * Order: x-vercel-forwarded-for > x-real-ip > x-forwarded-for > 'unknown'.
 *
 * Vercel normalizes x-vercel-forwarded-for at the edge (un-spoofable when behind Vercel).
 * x-forwarded-for left-most is the standard but spoofable outside Vercel.
 *
 * In production, callers must refuse 'unknown' (failure-closed — see ipGuard).
 */
export async function clientIp(): Promise<string> {
  const h = await headers()
  const vercel = h.get('x-vercel-forwarded-for')
  if (vercel) return vercel.split(',')[0].trim()
  const real = h.get('x-real-ip')
  if (real) return real
  const fwd = h.get('x-forwarded-for')
  if (fwd) return fwd.split(',')[0].trim()
  return 'unknown'
}

/**
 * Returns true if the IP can be trusted for rate limiting.
 * In production, 'unknown' is refused (failure-closed).
 */
export function ipIsTrusted(ip: string): boolean {
  if (ip === 'unknown' && process.env.NODE_ENV === 'production') return false
  return true
}
```

- [ ] **Step 2: Créer `lib/auth/timing.ts`**

```typescript
// lib/auth/timing.ts

/**
 * Sleep until Date.now() reaches `targetMs`. No-op if already past target.
 * Used to enforce a constant-floor execution time on auth Server Actions,
 * defeating timing-based account enumeration (audit C2).
 */
export async function sleepUntil(targetMs: number): Promise<void> {
  const remaining = targetMs - Date.now()
  if (remaining > 0) {
    await new Promise((resolve) => setTimeout(resolve, remaining))
  }
}

/** Minimum execution time (ms) for any auth-sensitive Server Action. */
export const AUTH_MIN_DURATION_MS = 800
```

- [ ] **Step 3: Verify typecheck**

```bash
pnpm typecheck
```
Expected: clean (les fichiers sont autonomes).

- [ ] **Step 4: Commit**

```bash
git add lib/auth/client-ip.ts lib/auth/timing.ts
git commit -m "feat(auth): add clientIp + timing helpers for IP-aware rate limit + anti-timing"
```

---

## Task 4 — Zod schemas + Vitest

**Files:**
- Create: `lib/auth/schemas.ts`
- Create: `lib/auth/common-passwords.ts`
- Create: `tests/unit/auth/schemas.test.ts`

- [ ] **Step 1: Créer `lib/auth/common-passwords.ts`**

Liste des 100 mots de passe les plus communs (sourcée NCSC + SecLists). Une seule constante exportée.

```typescript
// lib/auth/common-passwords.ts
// Top-100 most common passwords (NCSC 2019 + SecLists top-1k snapshot).
// Blocked at signup time — defense-in-depth contre credential stuffing.
export const COMMON_PASSWORDS: ReadonlySet<string> = new Set([
  '123456', '123456789', 'qwerty', 'password', '12345', 'qwerty123',
  '1q2w3e', '12345678', '111111', '1234567890', '1234567', 'abc123',
  'iloveyou', 'monkey', '654321', '!@#$%^&*', 'charlie', 'aa123456',
  'donald', 'password1', 'qwerty1', '123123', 'dragon', '123321',
  'azerty', 'azerty123', 'admin', 'admin123', 'welcome', 'welcome1',
  'login', 'starwars', 'master', 'hello', 'freedom', 'whatever',
  'qazwsx', 'trustno1', 'jordan23', 'harley', 'password123', 'asdf1234',
  'qwertyuiop', 'football', 'baseball', 'superman', 'batman', 'soccer',
  'jennifer', 'thomas', 'bailey', 'jessica', 'sophie', 'oliver',
  '123qwe', 'pokemon', 'chocolate', 'liverpool', 'arsenal', 'chelsea',
  'sunshine', 'princess', 'qwer1234', 'asdfghjkl', 'zxcvbnm', '111222',
  '696969', '7777777', 'amanda', 'andrea', 'matrix', 'shadow',
  'killer', 'master123', 'pass123', 'pass1234', 'test1234', 'test123',
  'demo1234', 'guest1234', '0987654321', '1qaz2wsx', 'asd123', 'qaz123',
  'mustang', 'access', 'biteme', 'cheese', 'tigger', 'computer',
  'maverick', 'minecraft', 'thunder', 'taylor', 'matthew', 'lovely',
  'butterfly', 'samsung', 'qweasd', 'q1w2e3', 'q1w2e3r4', '1q2w3e4r',
])
```

- [ ] **Step 2: Créer `lib/auth/schemas.ts`**

```typescript
// lib/auth/schemas.ts
import { z } from 'zod'
import { COMMON_PASSWORDS } from './common-passwords'

export const emailSchema = z
  .email('Email invalide')
  .transform((s) => s.toLowerCase().trim())

/**
 * Password used at registration / reset (min 10 chars + not in top-100 blocklist).
 * Login uses a looser variant (just non-empty + max 72).
 */
export const passwordSchema = z
  .string()
  .min(10, 'Au moins 10 caractères')
  .max(72, 'Maximum 72 caractères') // bcrypt limit côté Supabase
  .refine((p) => !COMMON_PASSWORDS.has(p.toLowerCase()), {
    message: 'Mot de passe trop courant — choisis-en un autre',
  })

export const registerSchema = z.object({
  email: emailSchema,
})

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, 'Requis').max(72),
})

export const forgotPasswordSchema = z.object({
  email: emailSchema,
})

export const setPasswordSchema = z
  .object({
    password: passwordSchema,
    confirm: z.string(),
  })
  .refine((d) => d.password === d.confirm, {
    path: ['confirm'],
    message: 'Les mots de passe ne correspondent pas',
  })

export type RegisterInput = z.infer<typeof registerSchema>
export type LoginInput = z.infer<typeof loginSchema>
export type ForgotPasswordInput = z.infer<typeof forgotPasswordSchema>
export type SetPasswordInput = z.infer<typeof setPasswordSchema>
```

- [ ] **Step 3: Écrire les tests Vitest**

`tests/unit/auth/schemas.test.ts` :

```typescript
import { describe, expect, it } from 'vitest'
import {
  emailSchema,
  passwordSchema,
  registerSchema,
  loginSchema,
  forgotPasswordSchema,
  setPasswordSchema,
} from '@/lib/auth/schemas'

describe('emailSchema', () => {
  it('accepts valid email and lowercases it', () => {
    const r = emailSchema.safeParse('FOO@Bar.com')
    expect(r.success).toBe(true)
    if (r.success) expect(r.data).toBe('foo@bar.com')
  })

  it('rejects invalid email', () => {
    expect(emailSchema.safeParse('not-an-email').success).toBe(false)
  })

  it('trims whitespace', () => {
    const r = emailSchema.safeParse('  a@b.com  ')
    if (r.success) expect(r.data).toBe('a@b.com')
  })
})

describe('passwordSchema', () => {
  it('accepts 10+ chars non-common', () => {
    expect(passwordSchema.safeParse('M1ghty-Tr1@thlete').success).toBe(true)
  })

  it('rejects < 10 chars', () => {
    expect(passwordSchema.safeParse('Short1!').success).toBe(false)
  })

  it('rejects > 72 chars', () => {
    expect(passwordSchema.safeParse('a'.repeat(73)).success).toBe(false)
  })

  it('rejects common password "password123"', () => {
    expect(passwordSchema.safeParse('password123').success).toBe(false)
  })

  it('rejects common password "qwerty123" case-insensitive', () => {
    expect(passwordSchema.safeParse('QWERTY123').success).toBe(false)
  })
})

describe('registerSchema', () => {
  it('accepts a valid email', () => {
    expect(registerSchema.safeParse({ email: 'a@b.com' }).success).toBe(true)
  })

  it('rejects missing email', () => {
    expect(registerSchema.safeParse({}).success).toBe(false)
  })
})

describe('loginSchema', () => {
  it('accepts any non-empty password (login doesn\'t check complexity)', () => {
    expect(
      loginSchema.safeParse({ email: 'a@b.com', password: 'short' }).success
    ).toBe(true)
  })

  it('rejects empty password', () => {
    expect(
      loginSchema.safeParse({ email: 'a@b.com', password: '' }).success
    ).toBe(false)
  })
})

describe('forgotPasswordSchema', () => {
  it('accepts a valid email', () => {
    expect(forgotPasswordSchema.safeParse({ email: 'a@b.com' }).success).toBe(true)
  })
})

describe('setPasswordSchema', () => {
  const valid = { password: 'M1ghty-Tr1@thlete', confirm: 'M1ghty-Tr1@thlete' }

  it('accepts matching strong passwords', () => {
    expect(setPasswordSchema.safeParse(valid).success).toBe(true)
  })

  it('rejects mismatching passwords', () => {
    expect(
      setPasswordSchema.safeParse({ ...valid, confirm: 'Different-One99' }).success
    ).toBe(false)
  })

  it('rejects when password fails passwordSchema (< 10)', () => {
    expect(
      setPasswordSchema.safeParse({ password: 'Short1!', confirm: 'Short1!' }).success
    ).toBe(false)
  })
})
```

- [ ] **Step 4: Run tests, observe failure (modules pas encore créés si Step 1-2 ratés)**

```bash
pnpm test --run tests/unit/auth
```
Expected at this point: tests PASS (les imports résolvent les fichiers créés Steps 1-2).

- [ ] **Step 5: Quality gates**

```bash
pnpm typecheck && pnpm lint
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add lib/auth/schemas.ts lib/auth/common-passwords.ts tests/unit/auth/schemas.test.ts
git commit -m "feat(auth): add Zod schemas + top-100 password blocklist + tests"
```

---

## Task 5 — Server Action `registerWithMagicLink`

**Files:**
- Create: `app/(auth)/_actions/auth.ts`
- Create: `tests/unit/auth/register-action.test.ts`

- [ ] **Step 1: Créer `app/(auth)/_actions/auth.ts` avec `registerWithMagicLink`**

```typescript
// app/(auth)/_actions/auth.ts
'use server'

import { headers } from 'next/headers'
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { clientIp, ipIsTrusted } from '@/lib/auth/client-ip'
import { sleepUntil, AUTH_MIN_DURATION_MS } from '@/lib/auth/timing'
import {
  registerSchema,
  loginSchema,
  forgotPasswordSchema,
  setPasswordSchema,
  type RegisterInput,
  type LoginInput,
  type ForgotPasswordInput,
  type SetPasswordInput,
} from '@/lib/auth/schemas'

// =========================================
// Common types
// =========================================
export type ActionError =
  | 'rate_limited'
  | 'email_not_allowed'
  | 'invalid_credentials'
  | 'ip_unresolved'
  | 'already_set'
  | 'unauthenticated'
  | 'save_failed'

export type ActionResult<T = Record<string, never>> =
  | ({ success: true } & T)
  | { success: false; error: ActionError; errors?: Record<string, string[]> }
  | { success: false; errors: Record<string, string[]> }

// =========================================
// Helpers
// =========================================
async function userAgent(): Promise<string> {
  return (await headers()).get('user-agent') ?? ''
}

async function originFromHeaders(): Promise<string> {
  const h = await headers()
  const proto = h.get('x-forwarded-proto') ?? 'https'
  const host = h.get('host') ?? 'garmin-training-ia.vercel.app'
  return `${proto}://${host}`
}

// =========================================
// registerWithMagicLink
// =========================================
export async function registerWithMagicLink(input: RegisterInput): Promise<ActionResult> {
  const t0 = Date.now()

  // 1. Zod parse
  const parsed = registerSchema.safeParse(input)
  if (!parsed.success) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, errors: parsed.error.flatten().fieldErrors as Record<string, string[]> }
  }
  const email = parsed.data.email

  // 2. clientIp + failure-closed in prod (I2)
  const ip = await clientIp()
  if (!ipIsTrusted(ip)) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'ip_unresolved' }
  }

  const supabase = await createClient()
  const ua = await userAgent()

  // 3. Rate limit (I1)
  const { data: rateOk } = await supabase.rpc('check_and_log_auth_rate_limit', {
    p_ip: ip,
    p_action: 'register',
    p_max_count: 3,
    p_window_seconds: 3600,
  })
  if (!rateOk) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'rate_limited' }
  }

  // 4. is_email_allowed
  const { data: allowed } = await supabase.rpc('is_email_allowed', { p_email: email })
  if (!allowed) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'email_not_allowed' }
  }

  // 5. email_needs_signup (I3) — n'envoie l'OTP que si user pas déjà actif
  const { data: needsSignup } = await supabase.rpc('email_needs_signup', { p_email: email })
  if (!needsSignup) {
    // Email allowlisté mais déjà actif → réponse success-générique SANS OTP (anti-spam)
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: true }
  }

  // 6. Envoi OTP
  const origin = await originFromHeaders()
  const { error: otpError } = await supabase.auth.signInWithOtp({
    email,
    options: {
      shouldCreateUser: true,
      emailRedirectTo: `${origin}/auth/callback?next=/auth/set-password`,
    },
  })

  // 7. Audit log (I5)
  if (!otpError) {
    await supabase.rpc('log_auth_event', {
      p_user_id: null,
      p_event_type: 'register_initiated',
      p_ip: ip,
      p_user_agent: ua,
      p_email: email,
    })
  }

  // 8. Anti-timing floor (C2)
  await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
  return { success: true }
}
```

- [ ] **Step 2: Écrire les tests `tests/unit/auth/register-action.test.ts`**

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

// Mock next/headers
vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) => {
      if (k === 'x-vercel-forwarded-for') return '1.2.3.4'
      if (k === 'user-agent') return 'vitest'
      if (k === 'host') return 'localhost:3000'
      if (k === 'x-forwarded-proto') return 'http'
      return null
    },
  })),
}))

// Mock supabase client
const mockSupabase = {
  rpc: vi.fn(),
  auth: { signInWithOtp: vi.fn() },
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { registerWithMagicLink } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  vi.useFakeTimers()
  mockSupabase.rpc.mockReset()
  mockSupabase.auth.signInWithOtp.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

async function advance(ms: number) {
  await vi.advanceTimersByTimeAsync(ms)
}

describe('registerWithMagicLink', () => {
  it('takes at least 800ms even on rate_limit short-circuit (C2 anti-timing)', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false }) // rate limit blocks
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await advance(799)
    let done = false
    void p.then(() => {
      done = true
    })
    await Promise.resolve()
    expect(done).toBe(false)
    await advance(2)
    await p
  })

  it('returns rate_limited when RPC returns false', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false })
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'rate_limited' })
    expect(mockSupabase.auth.signInWithOtp).not.toHaveBeenCalled()
  })

  it('returns email_not_allowed when is_email_allowed returns false', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true })   // rate limit OK
      .mockResolvedValueOnce({ data: false })  // is_email_allowed false
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'email_not_allowed' })
    expect(mockSupabase.auth.signInWithOtp).not.toHaveBeenCalled()
  })

  it('does NOT send OTP when email_needs_signup returns false (I3 anti-spam)', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true })   // rate limit OK
      .mockResolvedValueOnce({ data: true })   // is_email_allowed true
      .mockResolvedValueOnce({ data: false })  // email_needs_signup false (déjà actif)
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })  // generic success — pas de leak
    expect(mockSupabase.auth.signInWithOtp).not.toHaveBeenCalled()
  })

  it('sends OTP + logs audit on happy path', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true })   // rate limit OK
      .mockResolvedValueOnce({ data: true })   // is_email_allowed
      .mockResolvedValueOnce({ data: true })   // email_needs_signup
      .mockResolvedValueOnce({ data: null })   // log_auth_event
    mockSupabase.auth.signInWithOtp.mockResolvedValueOnce({ error: null })
    const p = registerWithMagicLink({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.signInWithOtp).toHaveBeenCalledOnce()
    expect(mockSupabase.rpc).toHaveBeenCalledWith('log_auth_event', expect.objectContaining({
      p_event_type: 'register_initiated',
    }))
  })

  it('rejects malformed email via Zod', async () => {
    const p = registerWithMagicLink({ email: 'not-an-email' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r.success).toBe(false)
    if (!r.success && 'errors' in r) expect(r.errors).toBeDefined()
  })
})
```

- [ ] **Step 3: Run tests**

```bash
pnpm test --run tests/unit/auth/register-action
```
Expected: 6 tests PASS.

- [ ] **Step 4: Quality gates**

```bash
pnpm typecheck && pnpm lint
```

- [ ] **Step 5: Commit**

```bash
git add app/'(auth)'/_actions/auth.ts tests/unit/auth/register-action.test.ts
git commit -m "feat(auth): add registerWithMagicLink server action with rate-limit + audit + anti-timing"
```

---

## Task 6 — Server Action `login`

**Files:**
- Modify: `app/(auth)/_actions/auth.ts` (add login function)
- Create: `tests/unit/auth/login-action.test.ts`

- [ ] **Step 1: Ajouter `login` à `app/(auth)/_actions/auth.ts`**

À ajouter à la fin du fichier (après `registerWithMagicLink`) :

```typescript
// =========================================
// login
// =========================================
export async function login(input: LoginInput): Promise<ActionResult> {
  const t0 = Date.now()

  const parsed = loginSchema.safeParse(input)
  if (!parsed.success) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, errors: parsed.error.flatten().fieldErrors as Record<string, string[]> }
  }
  const { email, password } = parsed.data

  const ip = await clientIp()
  if (!ipIsTrusted(ip)) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'ip_unresolved' }
  }

  const supabase = await createClient()
  const ua = await userAgent()

  // Rate limit : 10/15min
  const { data: rateOk } = await supabase.rpc('check_and_log_auth_rate_limit', {
    p_ip: ip,
    p_action: 'login',
    p_max_count: 10,
    p_window_seconds: 900,
  })
  if (!rateOk) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'rate_limited' }
  }

  const { error: signInError, data: signInData } = await supabase.auth.signInWithPassword({
    email,
    password,
  })

  if (signInError) {
    await supabase.rpc('log_auth_event', {
      p_user_id: null,
      p_event_type: 'login_failure',
      p_ip: ip,
      p_user_agent: ua,
      p_email: email,
    })
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'invalid_credentials' }
  }

  await supabase.rpc('log_auth_event', {
    p_user_id: signInData.user?.id ?? null,
    p_event_type: 'login_success',
    p_ip: ip,
    p_user_agent: ua,
    p_email: email,
  })

  await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
  return { success: true }
}
```

- [ ] **Step 2: Tests `tests/unit/auth/login-action.test.ts`**

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) => {
      if (k === 'x-vercel-forwarded-for') return '1.2.3.4'
      if (k === 'user-agent') return 'vitest'
      return null
    },
  })),
}))

const mockSupabase = {
  rpc: vi.fn(),
  auth: { signInWithPassword: vi.fn() },
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { login } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  vi.useFakeTimers()
  mockSupabase.rpc.mockReset()
  mockSupabase.auth.signInWithPassword.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('login', () => {
  it('rate-limits at 10 per 15min via RPC', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false })
    const p = login({ email: 'a@b.com', password: 'whatever' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'rate_limited' })
    expect(mockSupabase.auth.signInWithPassword).not.toHaveBeenCalled()
  })

  it('returns invalid_credentials on supabase error AND logs failure', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true })   // rate limit OK
      .mockResolvedValueOnce({ data: null })   // log_auth_event
    mockSupabase.auth.signInWithPassword.mockResolvedValueOnce({
      error: { message: 'Invalid login credentials' },
      data: { user: null },
    })
    const p = login({ email: 'a@b.com', password: 'wrong' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: false, error: 'invalid_credentials' })
    expect(mockSupabase.rpc).toHaveBeenCalledWith('log_auth_event', expect.objectContaining({
      p_event_type: 'login_failure',
    }))
  })

  it('returns success and logs login_success on happy path', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true })   // rate limit
      .mockResolvedValueOnce({ data: null })   // log_auth_event
    mockSupabase.auth.signInWithPassword.mockResolvedValueOnce({
      error: null,
      data: { user: { id: 'user-123' }, session: { access_token: 'x' } },
    })
    const p = login({ email: 'a@b.com', password: 'Correct-Horse-99' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.rpc).toHaveBeenCalledWith('log_auth_event', expect.objectContaining({
      p_event_type: 'login_success',
      p_user_id: 'user-123',
    }))
  })

  it('enforces 800ms floor on invalid_credentials', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true })
      .mockResolvedValueOnce({ data: null })
    mockSupabase.auth.signInWithPassword.mockResolvedValueOnce({
      error: { message: 'X' }, data: { user: null },
    })
    const p = login({ email: 'a@b.com', password: 'wrong' })
    await vi.advanceTimersByTimeAsync(799)
    let done = false
    void p.then(() => { done = true })
    await Promise.resolve()
    expect(done).toBe(false)
    await vi.advanceTimersByTimeAsync(2)
    await p
  })
})
```

- [ ] **Step 3: Run + quality gates + commit**

```bash
pnpm test --run tests/unit/auth/login-action
pnpm typecheck && pnpm lint
git add app/'(auth)'/_actions/auth.ts tests/unit/auth/login-action.test.ts
git commit -m "feat(auth): add login server action with rate-limit + audit + anti-timing"
```

---

## Task 7 — Server Action `requestPasswordReset`

**Files:**
- Modify: `app/(auth)/_actions/auth.ts`
- Create: `tests/unit/auth/forgot-action.test.ts`

- [ ] **Step 1: Ajouter `requestPasswordReset` à `app/(auth)/_actions/auth.ts`**

```typescript
// =========================================
// requestPasswordReset (forgot password)
// Always returns success-générique (no email enum leak).
// =========================================
export async function requestPasswordReset(
  input: ForgotPasswordInput
): Promise<ActionResult> {
  const t0 = Date.now()

  const parsed = forgotPasswordSchema.safeParse(input)
  if (!parsed.success) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: true } // success-générique
  }
  const email = parsed.data.email

  const ip = await clientIp()
  if (!ipIsTrusted(ip)) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: false, error: 'ip_unresolved' }
  }

  const supabase = await createClient()
  const ua = await userAgent()

  // Rate limit : 3/h
  const { data: rateOk } = await supabase.rpc('check_and_log_auth_rate_limit', {
    p_ip: ip,
    p_action: 'forgot_password',
    p_max_count: 3,
    p_window_seconds: 3600,
  })
  if (!rateOk) {
    await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
    return { success: true } // always-success even when rate-limited (anti-leak)
  }

  const origin = await originFromHeaders()
  const { error: resetError } = await supabase.auth.resetPasswordForEmail(email, {
    redirectTo: `${origin}/auth/callback?next=/auth/reset-password`,
  })

  if (!resetError) {
    await supabase.rpc('log_auth_event', {
      p_user_id: null,
      p_event_type: 'password_reset_requested',
      p_ip: ip,
      p_user_agent: ua,
      p_email: email,
    })
  }

  await sleepUntil(t0 + AUTH_MIN_DURATION_MS)
  return { success: true }
}
```

- [ ] **Step 2: Tests `tests/unit/auth/forgot-action.test.ts`**

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) => {
      if (k === 'x-vercel-forwarded-for') return '1.2.3.4'
      if (k === 'user-agent') return 'vitest'
      if (k === 'host') return 'localhost:3000'
      if (k === 'x-forwarded-proto') return 'http'
      return null
    },
  })),
}))

const mockSupabase = {
  rpc: vi.fn(),
  auth: { resetPasswordForEmail: vi.fn() },
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { requestPasswordReset } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  vi.useFakeTimers()
  mockSupabase.rpc.mockReset()
  mockSupabase.auth.resetPasswordForEmail.mockReset()
})
afterEach(() => {
  vi.useRealTimers()
})

describe('requestPasswordReset', () => {
  it('returns generic success even when email is invalid (no leak)', async () => {
    const p = requestPasswordReset({ email: 'not-an-email' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.resetPasswordForEmail).not.toHaveBeenCalled()
  })

  it('returns generic success when rate-limited (no leak)', async () => {
    mockSupabase.rpc.mockResolvedValueOnce({ data: false })
    const p = requestPasswordReset({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p
    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.resetPasswordForEmail).not.toHaveBeenCalled()
  })

  it('happy path : calls resetPasswordForEmail + logs', async () => {
    mockSupabase.rpc
      .mockResolvedValueOnce({ data: true })  // rate limit OK
      .mockResolvedValueOnce({ data: null })  // log_auth_event
    mockSupabase.auth.resetPasswordForEmail.mockResolvedValueOnce({ error: null })

    const p = requestPasswordReset({ email: 'a@b.com' })
    await vi.advanceTimersByTimeAsync(1000)
    const r = await p

    expect(r).toEqual({ success: true })
    expect(mockSupabase.auth.resetPasswordForEmail).toHaveBeenCalledWith(
      'a@b.com',
      expect.objectContaining({ redirectTo: expect.stringContaining('/auth/callback?next=/auth/reset-password') })
    )
    expect(mockSupabase.rpc).toHaveBeenCalledWith(
      'log_auth_event',
      expect.objectContaining({ p_event_type: 'password_reset_requested' })
    )
  })

  it('enforces 800ms floor', async () => {
    const p = requestPasswordReset({ email: 'not-an-email' })
    await vi.advanceTimersByTimeAsync(799)
    let done = false
    void p.then(() => { done = true })
    await Promise.resolve()
    expect(done).toBe(false)
    await vi.advanceTimersByTimeAsync(2)
    await p
  })
})
```

- [ ] **Step 3: Run + commit**

```bash
pnpm test --run tests/unit/auth/forgot-action
pnpm typecheck && pnpm lint
git add app/'(auth)'/_actions/auth.ts tests/unit/auth/forgot-action.test.ts
git commit -m "feat(auth): add requestPasswordReset server action (no email enum leak)"
```

---

## Task 8 — Server Action `setInitialPassword` (avec guard I4)

**Files:**
- Modify: `app/(auth)/_actions/auth.ts`
- Create: `tests/unit/auth/set-password-action.test.ts`

- [ ] **Step 1: Ajouter `setInitialPassword` à `app/(auth)/_actions/auth.ts`**

```typescript
// =========================================
// setInitialPassword
// Called from /auth/set-password (1ère connexion via magic link register).
// I4 guard : refuse if password_set === true already (anti session-theft → reset lockout).
// =========================================
export async function setInitialPassword(input: SetPasswordInput): Promise<ActionResult> {
  const parsed = setPasswordSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors as Record<string, string[]> }
  }
  const { password } = parsed.data

  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) {
    return { success: false, error: 'unauthenticated' }
  }

  // I4 — guard : refuse si password_set déjà true (cette action ne sert que pour la 1ère fois)
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('password_set')
    .eq('user_id', user.id)
    .single<{ password_set: boolean }>()

  if (profile?.password_set === true) {
    return { success: false, error: 'already_set' }
  }

  const { error: updateError } = await supabase.auth.updateUser({ password })
  if (updateError) return { success: false, error: 'save_failed' }

  const { error: flagError } = await supabase
    .from('athlete_profiles')
    .update({ password_set: true })
    .eq('user_id', user.id)
  if (flagError) return { success: false, error: 'save_failed' }

  // Audit
  const ip = await clientIp()
  const ua = await userAgent()
  await supabase.rpc('log_auth_event', {
    p_user_id: user.id,
    p_event_type: 'password_set',
    p_ip: ip,
    p_user_agent: ua,
    p_email: user.email ?? '',
  })

  redirect('/onboarding')
}
```

- [ ] **Step 2: Tests `tests/unit/auth/set-password-action.test.ts`**

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) => (k === 'user-agent' ? 'vitest' : k === 'x-vercel-forwarded-for' ? '1.2.3.4' : null),
  })),
}))

vi.mock('next/navigation', () => ({
  redirect: vi.fn((path: string) => {
    throw new Error(`__NEXT_REDIRECT__:${path}`)
  }),
}))

const mockSupabase = {
  auth: { getUser: vi.fn(), updateUser: vi.fn() },
  from: vi.fn(),
  rpc: vi.fn(),
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { setInitialPassword } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  mockSupabase.auth.getUser.mockReset()
  mockSupabase.auth.updateUser.mockReset()
  mockSupabase.from.mockReset()
  mockSupabase.rpc.mockReset()
})

describe('setInitialPassword', () => {
  const validInput = { password: 'M1ghty-Tr1@thlete', confirm: 'M1ghty-Tr1@thlete' }

  it('returns unauthenticated if no session', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({ data: { user: null } })
    const r = await setInitialPassword(validInput)
    expect(r).toEqual({ success: false, error: 'unauthenticated' })
  })

  it('I4 guard : refuses if password_set is already true', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({
      data: { user: { id: 'u1', email: 'a@b.com' } },
    })
    mockSupabase.from.mockReturnValueOnce({
      select: () => ({
        eq: () => ({
          single: async () => ({ data: { password_set: true } }),
        }),
      }),
    })
    const r = await setInitialPassword(validInput)
    expect(r).toEqual({ success: false, error: 'already_set' })
    expect(mockSupabase.auth.updateUser).not.toHaveBeenCalled()
  })

  it('happy path : updateUser + flag password_set=true + log + redirect /onboarding', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({
      data: { user: { id: 'u1', email: 'a@b.com' } },
    })
    mockSupabase.from
      .mockReturnValueOnce({
        select: () => ({
          eq: () => ({
            single: async () => ({ data: { password_set: false } }),
          }),
        }),
      })
      .mockReturnValueOnce({
        update: () => ({ eq: async () => ({ error: null }) }),
      })
    mockSupabase.auth.updateUser.mockResolvedValueOnce({ error: null })
    mockSupabase.rpc.mockResolvedValueOnce({ data: null })

    await expect(setInitialPassword(validInput)).rejects.toThrow('__NEXT_REDIRECT__:/onboarding')
    expect(mockSupabase.auth.updateUser).toHaveBeenCalledWith({ password: validInput.password })
    expect(mockSupabase.rpc).toHaveBeenCalledWith('log_auth_event', expect.objectContaining({
      p_event_type: 'password_set',
      p_user_id: 'u1',
    }))
  })

  it('returns errors when Zod fails (passwords don\'t match)', async () => {
    const r = await setInitialPassword({ password: 'M1ghty-Tr1@thlete', confirm: 'Different99-One!' })
    expect(r.success).toBe(false)
    if (!r.success && 'errors' in r) expect(r.errors).toBeDefined()
  })
})
```

- [ ] **Step 3: Run + commit**

```bash
pnpm test --run tests/unit/auth/set-password-action
pnpm typecheck && pnpm lint
git add app/'(auth)'/_actions/auth.ts tests/unit/auth/set-password-action.test.ts
git commit -m "feat(auth): add setInitialPassword with I4 already_set guard + audit"
```

---

## Task 9 — Server Action `setPasswordAfterReset`

**Files:**
- Modify: `app/(auth)/_actions/auth.ts`
- Create: `tests/unit/auth/reset-password-action.test.ts`

- [ ] **Step 1: Ajouter à `app/(auth)/_actions/auth.ts`**

```typescript
// =========================================
// setPasswordAfterReset
// Called from /auth/reset-password (after clicking the email reset link).
// Updates password + sets password_set=true (covers migration legacy users).
// =========================================
export async function setPasswordAfterReset(input: SetPasswordInput): Promise<ActionResult> {
  const parsed = setPasswordSchema.safeParse(input)
  if (!parsed.success) {
    return { success: false, errors: parsed.error.flatten().fieldErrors as Record<string, string[]> }
  }
  const { password } = parsed.data

  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) {
    return { success: false, error: 'unauthenticated' }
  }

  const { error: updateError } = await supabase.auth.updateUser({ password })
  if (updateError) return { success: false, error: 'save_failed' }

  // Idempotent : si déjà true, ne change rien
  const { error: flagError } = await supabase
    .from('athlete_profiles')
    .update({ password_set: true })
    .eq('user_id', user.id)
  if (flagError) return { success: false, error: 'save_failed' }

  const ip = await clientIp()
  const ua = await userAgent()
  await supabase.rpc('log_auth_event', {
    p_user_id: user.id,
    p_event_type: 'password_reset_completed',
    p_ip: ip,
    p_user_agent: ua,
    p_email: user.email ?? '',
  })

  redirect('/today')
}
```

- [ ] **Step 2: Tests `tests/unit/auth/reset-password-action.test.ts`**

```typescript
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('next/headers', () => ({
  headers: vi.fn(async () => ({
    get: (k: string) => (k === 'user-agent' ? 'vitest' : k === 'x-vercel-forwarded-for' ? '1.2.3.4' : null),
  })),
}))

vi.mock('next/navigation', () => ({
  redirect: vi.fn((path: string) => {
    throw new Error(`__NEXT_REDIRECT__:${path}`)
  }),
}))

const mockSupabase = {
  auth: { getUser: vi.fn(), updateUser: vi.fn() },
  from: vi.fn(),
  rpc: vi.fn(),
}
vi.mock('@/lib/supabase/server', () => ({
  createClient: async () => mockSupabase,
}))

import { setPasswordAfterReset } from '@/app/(auth)/_actions/auth'

beforeEach(() => {
  mockSupabase.auth.getUser.mockReset()
  mockSupabase.auth.updateUser.mockReset()
  mockSupabase.from.mockReset()
  mockSupabase.rpc.mockReset()
})

describe('setPasswordAfterReset', () => {
  const validInput = { password: 'New-Pass-2026!', confirm: 'New-Pass-2026!' }

  it('returns unauthenticated if no session', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({ data: { user: null } })
    const r = await setPasswordAfterReset(validInput)
    expect(r).toEqual({ success: false, error: 'unauthenticated' })
  })

  it('happy path : updateUser + flag + log + redirect /today', async () => {
    mockSupabase.auth.getUser.mockResolvedValueOnce({
      data: { user: { id: 'u1', email: 'a@b.com' } },
    })
    mockSupabase.from.mockReturnValueOnce({
      update: () => ({ eq: async () => ({ error: null }) }),
    })
    mockSupabase.auth.updateUser.mockResolvedValueOnce({ error: null })
    mockSupabase.rpc.mockResolvedValueOnce({ data: null })

    await expect(setPasswordAfterReset(validInput)).rejects.toThrow('__NEXT_REDIRECT__:/today')
    expect(mockSupabase.rpc).toHaveBeenCalledWith('log_auth_event', expect.objectContaining({
      p_event_type: 'password_reset_completed',
    }))
  })

  it('rejects Zod fail (mismatch)', async () => {
    const r = await setPasswordAfterReset({ password: 'New-Pass-99!', confirm: 'Other-Pass-99!' })
    expect(r.success).toBe(false)
  })
})
```

- [ ] **Step 3: Commit**

```bash
pnpm test --run tests/unit/auth/reset-password-action
pnpm typecheck && pnpm lint
git add app/'(auth)'/_actions/auth.ts tests/unit/auth/reset-password-action.test.ts
git commit -m "feat(auth): add setPasswordAfterReset (idempotent password_set flag)"
```

---

## Task 10 — Callback refactor : `next` whitelist + `password_set` routing

**Files:**
- Modify: `app/(auth)/auth/callback/route.ts`
- Create: `tests/unit/auth/callback.test.ts`

- [ ] **Step 1: Refactor `app/(auth)/auth/callback/route.ts`**

```typescript
// app/(auth)/auth/callback/route.ts
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

/**
 * Whitelist of safe redirect targets (C1 anti-open-redirect).
 * Any other `next` value falls back to '/today'.
 */
const SAFE_NEXT = new Set<string>([
  '/auth/set-password',
  '/auth/reset-password',
  '/today',
  '/onboarding',
  '/profile',
])

export function isSafeNext(value: string | null): string {
  if (value && SAFE_NEXT.has(value)) return value
  return '/today'
}

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const rawNext = searchParams.get('next')
  const next = isSafeNext(rawNext)

  if (!code) {
    return NextResponse.redirect(`${origin}/login?error=auth_failed`)
  }

  const supabase = await createClient()
  const { error } = await supabase.auth.exchangeCodeForSession(code)
  if (error) {
    return NextResponse.redirect(`${origin}/login?error=auth_failed`)
  }

  // Si l'user n'a pas encore set son mdp → toujours vers /auth/set-password
  // (sauf si on est explicitement sur le flow reset → /auth/reset-password)
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (user) {
    const { data: profile } = await supabase
      .from('athlete_profiles')
      .select('password_set')
      .eq('user_id', user.id)
      .single<{ password_set: boolean }>()

    if (profile?.password_set === false && next !== '/auth/reset-password') {
      return NextResponse.redirect(`${origin}/auth/set-password`)
    }
  }

  return NextResponse.redirect(`${origin}${next}`)
}
```

- [ ] **Step 2: Tests `tests/unit/auth/callback.test.ts`**

```typescript
import { describe, expect, it } from 'vitest'
import { isSafeNext } from '@/app/(auth)/auth/callback/route'

describe('isSafeNext (C1 anti-open-redirect)', () => {
  it('allows whitelisted /auth/set-password', () => {
    expect(isSafeNext('/auth/set-password')).toBe('/auth/set-password')
  })
  it('allows whitelisted /auth/reset-password', () => {
    expect(isSafeNext('/auth/reset-password')).toBe('/auth/reset-password')
  })
  it('allows whitelisted /today', () => {
    expect(isSafeNext('/today')).toBe('/today')
  })
  it('falls back to /today on null', () => {
    expect(isSafeNext(null)).toBe('/today')
  })
  it('falls back to /today on external URL (open redirect attempt)', () => {
    expect(isSafeNext('https://evil.com')).toBe('/today')
  })
  it('falls back to /today on path traversal attempt', () => {
    expect(isSafeNext('//evil.com')).toBe('/today')
  })
  it('falls back to /today on unknown internal path', () => {
    expect(isSafeNext('/random')).toBe('/today')
  })
})
```

- [ ] **Step 3: Run + commit**

```bash
pnpm test --run tests/unit/auth/callback
pnpm typecheck && pnpm lint
git add app/'(auth)'/auth/callback/route.ts tests/unit/auth/callback.test.ts
git commit -m "feat(auth): callback whitelist next + redirect to /auth/set-password when password_set=false"
```

---

## Task 11 — `/login` refactor : EmailPasswordForm

**Files:**
- Create: `components/auth/email-password-form.tsx`
- Modify: `app/(auth)/login/page.tsx`

- [ ] **Step 1: Créer `components/auth/email-password-form.tsx`**

```typescript
'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login } from '@/app/(auth)/_actions/auth'

export function EmailPasswordForm() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})

    const r = await login({ email, password })

    if (r.success) {
      router.push('/today')
      router.refresh()
      return
    }

    if ('errors' in r && r.errors) {
      setErrors(r.errors)
      setLoading(false)
      return
    }

    setLoading(false)

    if (r.error === 'rate_limited') {
      toast.error('Trop de tentatives, réessaie dans 15 minutes')
      return
    }
    if (r.error === 'ip_unresolved') {
      toast.error('Impossible de résoudre ton IP — contacte l\'admin')
      return
    }
    // 'invalid_credentials' OU unknown → message générique anti-leak
    toast.error('Email ou mot de passe incorrect')
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value) }}
          required
          disabled={loading}
        />
        {errors.email?.[0] && <p className="text-destructive text-xs">{errors.email[0]}</p>}
      </div>
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="password">Mot de passe</Label>
          <Link href="/forgot-password" className="text-muted-foreground text-xs hover:underline">
            Mot de passe oublié ?
          </Link>
        </div>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => { setPassword(e.target.value) }}
          required
          disabled={loading}
        />
        {errors.password?.[0] && <p className="text-destructive text-xs">{errors.password[0]}</p>}
      </div>
      <Button type="submit" disabled={loading || !email || !password} className="w-full">
        {loading ? 'Connexion...' : 'Se connecter'}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        Pas encore de compte ?{' '}
        <Link href="/register" className="underline">
          Créer un compte
        </Link>
      </p>
    </form>
  )
}
```

- [ ] **Step 2: Modifier `app/(auth)/login/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { EmailPasswordForm } from '@/components/auth/email-password-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function LoginPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (user) {
    redirect('/today')
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Garmin Training Coach</h1>
          <p className="text-muted-foreground text-sm">Connecte-toi pour accéder à ton plan</p>
        </header>
        <EmailPasswordForm />
      </div>
      <Toaster />
    </main>
  )
}
```

- [ ] **Step 3: Run quality gates + commit**

```bash
pnpm typecheck && pnpm lint && pnpm build
git add components/auth/email-password-form.tsx app/'(auth)'/login/page.tsx
git commit -m "feat(auth): refactor /login to email+password form"
```

---

## Task 12 — `/register` page + RegisterForm

**Files:**
- Create: `components/auth/register-form.tsx`
- Create: `app/(auth)/register/page.tsx`

- [ ] **Step 1: Créer `components/auth/register-form.tsx`**

```typescript
'use client'

import Link from 'next/link'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { registerWithMagicLink } from '@/app/(auth)/_actions/auth'

export function RegisterForm() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})

    const r = await registerWithMagicLink({ email })

    setLoading(false)

    if (r.success) {
      setSent(true)
      toast.success('Si cet email est autorisé, un lien vient d\'être envoyé. Vérifie ta boîte.')
      return
    }

    if ('errors' in r && r.errors) {
      setErrors(r.errors)
      return
    }

    if (r.error === 'rate_limited') {
      toast.error('Trop de tentatives depuis ton IP, réessaie dans 1 heure')
      return
    }
    if (r.error === 'ip_unresolved') {
      toast.error('Impossible de résoudre ton IP — contacte l\'admin')
      return
    }
    if (r.error === 'email_not_allowed') {
      // Anti-leak : message identique succès-générique (mais on le différencie un peu pour UX honnête)
      toast.error('Cet email n\'est pas autorisé à s\'inscrire. Contacte l\'admin pour demander un accès.')
      return
    }
    toast.error('Erreur inattendue, réessaie')
  }

  if (sent) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-sm">
          📬 Si <strong>{email}</strong> est dans la liste d\'attente, un email vient d\'arriver
          avec un lien à cliquer pour activer ton compte.
        </p>
        <p className="text-muted-foreground text-xs">
          Pense à vérifier ton dossier spam. Le lien expire dans 1 heure.
        </p>
        <Link href="/login" className="text-xs underline">
          ← Retour à la connexion
        </Link>
      </div>
    )
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value) }}
          required
          disabled={loading}
        />
        {errors.email?.[0] && <p className="text-destructive text-xs">{errors.email[0]}</p>}
      </div>
      <Button type="submit" disabled={loading || !email} className="w-full">
        {loading ? 'Envoi du lien...' : 'Créer mon compte'}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        Déjà un compte ?{' '}
        <Link href="/login" className="underline">
          Se connecter
        </Link>
      </p>
    </form>
  )
}
```

- [ ] **Step 2: Créer `app/(auth)/register/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { RegisterForm } from '@/components/auth/register-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function RegisterPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (user) redirect('/today')

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Créer un compte</h1>
          <p className="text-muted-foreground text-sm">
            Entre ton email — tu recevras un lien d\'activation
          </p>
        </header>
        <RegisterForm />
      </div>
      <Toaster />
    </main>
  )
}
```

- [ ] **Step 3: Commit**

```bash
pnpm typecheck && pnpm lint && pnpm build
git add components/auth/register-form.tsx app/'(auth)'/register/
git commit -m "feat(auth): add /register page with allowlist-gated email entry"
```

---

## Task 13 — `/forgot-password` page + ForgotPasswordForm

**Files:**
- Create: `components/auth/forgot-password-form.tsx`
- Create: `app/(auth)/forgot-password/page.tsx`

- [ ] **Step 1: Créer `components/auth/forgot-password-form.tsx`**

```typescript
'use client'

import Link from 'next/link'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { requestPasswordReset } from '@/app/(auth)/_actions/auth'

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)

    await requestPasswordReset({ email })

    // Always show generic success (no email enum leak)
    setLoading(false)
    setSent(true)
  }

  if (sent) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-sm">
          📬 Si <strong>{email}</strong> correspond à un compte, un email avec un lien
          de réinitialisation vient d\'être envoyé.
        </p>
        <p className="text-muted-foreground text-xs">
          Pense à vérifier ton dossier spam.
        </p>
        <Link href="/login" className="text-xs underline">
          ← Retour à la connexion
        </Link>
      </div>
    )
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => { setEmail(e.target.value) }}
          required
          disabled={loading}
        />
      </div>
      <Button type="submit" disabled={loading || !email} className="w-full">
        {loading ? 'Envoi...' : 'Envoyer le lien'}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        <Link href="/login" className="underline">
          ← Retour à la connexion
        </Link>
      </p>
    </form>
  )
}
```

- [ ] **Step 2: Créer `app/(auth)/forgot-password/page.tsx`**

```typescript
import { ForgotPasswordForm } from '@/components/auth/forgot-password-form'
import { Toaster } from '@/components/ui/sonner'

export default function ForgotPasswordPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Mot de passe oublié</h1>
          <p className="text-muted-foreground text-sm">
            Entre ton email — on t\'envoie un lien pour le réinitialiser
          </p>
        </header>
        <ForgotPasswordForm />
      </div>
      <Toaster />
    </main>
  )
}
```

- [ ] **Step 3: Commit**

```bash
pnpm typecheck && pnpm lint && pnpm build
git add components/auth/forgot-password-form.tsx app/'(auth)'/forgot-password/
git commit -m "feat(auth): add /forgot-password page (always generic success, no leak)"
```

---

## Task 14 — `/auth/set-password` page + SetPasswordForm

**Files:**
- Create: `components/auth/set-password-form.tsx`
- Create: `app/(auth)/auth/set-password/page.tsx`

- [ ] **Step 1: Créer `components/auth/set-password-form.tsx`** (réutilisé Task 15)

```typescript
'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

type SetPasswordAction = (input: { password: string; confirm: string }) => Promise<
  | { success: true }
  | { success: false; errors?: Record<string, string[]>; error?: string }
>

interface Props {
  action: SetPasswordAction
  submitLabel: string
  submitLabelLoading: string
}

export function SetPasswordForm({ action, submitLabel, submitLabelLoading }: Readonly<Props>) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    try {
      const r = await action({ password, confirm })
      if (r.success) return // server redirected
      if ('errors' in r && r.errors) {
        setErrors(r.errors)
      } else if (r.error === 'already_set') {
        toast.error('Mot de passe déjà défini — utilise "Mot de passe oublié" pour le réinitialiser')
      } else if (r.error === 'unauthenticated') {
        toast.error('Session expirée — reconnecte-toi')
      } else {
        toast.error('Erreur de sauvegarde')
      }
    } catch (err) {
      // Server Action `redirect()` throws NEXT_REDIRECT — that's success, do nothing.
      if (err instanceof Error && err.message.startsWith('NEXT_REDIRECT')) return
      toast.error('Erreur inattendue')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="password">Nouveau mot de passe</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => { setPassword(e.target.value) }}
          required
          disabled={loading}
          minLength={10}
          maxLength={72}
        />
        <p className="text-muted-foreground text-xs">Au moins 10 caractères. Évite les mots de passe courants.</p>
        {errors.password?.[0] && <p className="text-destructive text-xs">{errors.password[0]}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="confirm">Confirme</Label>
        <Input
          id="confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => { setConfirm(e.target.value) }}
          required
          disabled={loading}
        />
        {errors.confirm?.[0] && <p className="text-destructive text-xs">{errors.confirm[0]}</p>}
      </div>
      <Button type="submit" disabled={loading || !password || !confirm} className="w-full">
        {loading ? submitLabelLoading : submitLabel}
      </Button>
    </form>
  )
}
```

- [ ] **Step 2: Créer `app/(auth)/auth/set-password/page.tsx`**

```typescript
import { redirect } from 'next/navigation'
import { setInitialPassword } from '@/app/(auth)/_actions/auth'
import { SetPasswordForm } from '@/components/auth/set-password-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function SetPasswordPage() {
  // Session guard — must be logged in (just clicked the magic-link)
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Crée ton mot de passe</h1>
          <p className="text-muted-foreground text-sm">
            Choisis un mot de passe que tu utiliseras pour te connecter la prochaine fois.
          </p>
        </header>
        <SetPasswordForm
          action={setInitialPassword}
          submitLabel="Enregistrer et continuer"
          submitLabelLoading="Enregistrement..."
        />
      </div>
      <Toaster />
    </main>
  )
}
```

- [ ] **Step 3: Commit**

```bash
pnpm typecheck && pnpm lint && pnpm build
git add components/auth/set-password-form.tsx app/'(auth)'/auth/set-password/
git commit -m "feat(auth): add /auth/set-password page (1ère connexion)"
```

---

## Task 15 — `/auth/reset-password` page (réutilise SetPasswordForm)

**Files:**
- Create: `app/(auth)/auth/reset-password/page.tsx`

- [ ] **Step 1: Créer la page**

```typescript
import { redirect } from 'next/navigation'
import { setPasswordAfterReset } from '@/app/(auth)/_actions/auth'
import { SetPasswordForm } from '@/components/auth/set-password-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function ResetPasswordPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) {
    // Lien expiré ou utilisé → retour forgot
    redirect('/forgot-password?expired=1')
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Réinitialise ton mot de passe</h1>
          <p className="text-muted-foreground text-sm">
            Choisis ton nouveau mot de passe.
          </p>
        </header>
        <SetPasswordForm
          action={setPasswordAfterReset}
          submitLabel="Réinitialiser"
          submitLabelLoading="Enregistrement..."
        />
      </div>
      <Toaster />
    </main>
  )
}
```

- [ ] **Step 2: Commit**

```bash
pnpm typecheck && pnpm lint && pnpm build
git add app/'(auth)'/auth/reset-password/
git commit -m "feat(auth): add /auth/reset-password page (reuses SetPasswordForm)"
```

---

## Task 16 — Email templates FR (confirm-signup + reset-password)

**Files:**
- Rename: `supabase/email-templates/magic-link.html` → `confirm-signup.html`
- Rename: `supabase/email-templates/magic-link.subject.txt` → `confirm-signup.subject.txt`
- Modify: `confirm-signup.subject.txt` (nouveau sujet)
- Create: `supabase/email-templates/reset-password.html`
- Create: `supabase/email-templates/reset-password.subject.txt`
- Modify: `supabase/email-templates/README.md`

- [ ] **Step 1: Rename + edit confirm-signup subject**

```bash
git mv supabase/email-templates/magic-link.html supabase/email-templates/confirm-signup.html
git mv supabase/email-templates/magic-link.subject.txt supabase/email-templates/confirm-signup.subject.txt
```

Réécrire `confirm-signup.subject.txt` :
```
Active ton compte Garmin Training
```

- [ ] **Step 2: Adapter le contenu de `confirm-signup.html`**

Garder la structure HTML existante mais remplacer le wording centré sur le login par un wording d'activation. Le lien dans le template Supabase utilise `{{ .ConfirmationURL }}`. Important M3 :
- Afficher l'URL complète en dessous du bouton (pas juste l'anchor)
- Ajouter la phrase de contexte phishing-resistance

Exemple de contenu cible (à adapter au CSS existant) :

```html
<!-- supabase/email-templates/confirm-signup.html -->
<!-- ...header existant... -->
<h1>Active ton compte Garmin Training</h1>
<p>Quelqu'un (probablement toi) vient de demander la création d'un compte avec cet email.</p>
<p><strong>Clique le lien ci-dessous pour activer ton compte :</strong></p>
<p><a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:12px 24px;background:#000;color:#fff;text-decoration:none;border-radius:6px;">Activer mon compte</a></p>
<p style="font-size:12px;color:#666;">Ou copie ce lien dans ton navigateur :<br>
<code style="word-break:break-all;">{{ .ConfirmationURL }}</code></p>
<p style="font-size:12px;color:#666;">Ce lien expire dans 1 heure. Si tu n'as pas demandé d'activation, ignore cet email — aucun compte ne sera créé.</p>
<!-- ...footer existant... -->
```

- [ ] **Step 3: Créer `reset-password.html` et `reset-password.subject.txt`**

`reset-password.subject.txt` :
```
Réinitialise ton mot de passe Garmin Training
```

`reset-password.html` (structure similaire à `confirm-signup.html`, wording adapté) :
```html
<!-- ...header existant... -->
<h1>Réinitialise ton mot de passe</h1>
<p>Quelqu'un (probablement toi) vient de demander la réinitialisation du mot de passe de ce compte.</p>
<p><strong>Clique le lien ci-dessous pour choisir un nouveau mot de passe :</strong></p>
<p><a href="{{ .ConfirmationURL }}" style="display:inline-block;padding:12px 24px;background:#000;color:#fff;text-decoration:none;border-radius:6px;">Réinitialiser mon mot de passe</a></p>
<p style="font-size:12px;color:#666;">Ou copie ce lien dans ton navigateur :<br>
<code style="word-break:break-all;">{{ .ConfirmationURL }}</code></p>
<p style="font-size:12px;color:#666;">Ce lien expire dans 1 heure. Si tu n'as pas demandé cette réinitialisation, ignore cet email — ton mot de passe reste inchangé.</p>
```

- [ ] **Step 4: Mettre à jour `supabase/email-templates/README.md`**

Ajouter une section qui liste les 2 templates, leur déclenchement, et la procédure de mise en place via Supabase Studio :

```markdown
## Templates auth (E-Auth EPIC)

| Fichier | Déclenché par | Sujet Studio |
|---|---|---|
| `confirm-signup.html` + `.subject.txt` | `supabase.auth.signInWithOtp({ shouldCreateUser: true })` (depuis `/register`) | "Active ton compte Garmin Training" |
| `reset-password.html` + `.subject.txt` | `supabase.auth.resetPasswordForEmail` (depuis `/forgot-password`) | "Réinitialise ton mot de passe Garmin Training" |

### Setup Supabase Studio post-merge

1. Dashboard → Authentication → Email Templates
2. **Magic Link** (template Supabase pour signInWithOtp) → coller le contenu de `confirm-signup.html` + ajuster le sujet à `confirm-signup.subject.txt`
3. **Reset Password** (template Supabase pour resetPasswordForEmail) → coller le contenu de `reset-password.html` + ajuster le sujet
4. **URL Configuration** → Redirect URLs : ajouter
   - `https://garmin-training-ia.vercel.app/auth/set-password`
   - `https://garmin-training-ia.vercel.app/auth/reset-password`
   - `http://localhost:3000/auth/set-password`
   - `http://localhost:3000/auth/reset-password`

### Phishing-resistance (M3)

Chaque template doit :
- Afficher l'URL complète sous le bouton (pas seulement un anchor cliquable)
- Mentionner l'expiration du lien
- Mentionner "ignore cet email si tu n'as pas demandé"

### Cookies (M2 vérification post-deploy)

Après mise en prod, vérifier dans DevTools (Application → Cookies) que les cookies Supabase ont :
- `Secure = true`
- `HttpOnly = true`
- `SameSite = Lax`

Si ce n'est pas le cas, revoir la config Supabase Auth.
```

- [ ] **Step 5: Commit**

```bash
git add supabase/email-templates/
git commit -m "docs(email-templates): rename magic-link → confirm-signup + add reset-password + README"
```

---

## Task 17 — Suppression MagicLinkForm + nettoyage

**Files:**
- Delete: `components/auth/magic-link-form.tsx`

- [ ] **Step 1: Vérifier qu'aucune autre référence n'existe**

```bash
grep -rn "MagicLinkForm\|magic-link-form" --include='*.ts' --include='*.tsx' .
```
Expected: aucune référence ; sinon corriger les imports.

- [ ] **Step 2: Supprimer**

```bash
git rm components/auth/magic-link-form.tsx
```

- [ ] **Step 3: Full quality gates**

```bash
cd /home/tellebma/DEV/garmin_training
pnpm test --run
pnpm typecheck && pnpm lint && pnpm build
```
Expected: tous verts.

- [ ] **Step 4: Commit**

```bash
git commit -m "chore(auth): remove MagicLinkForm — replaced by EmailPasswordForm"
```

---

## Task 18 — Push branch + open PR

- [ ] **Step 1: Run full quality gates locally**

```bash
cd /home/tellebma/DEV/garmin_training
pnpm test --run
pnpm typecheck && pnpm lint && pnpm build
```
Expected: tous verts (~30+ nouveaux tests auth + build clean).

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/eauth-refactor
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --base main --head feat/eauth-refactor \
  --title "feat(eauth): email+password auth + allowlist + rate-limit + audit log" \
  --body "$(cat <<'EOF'
## Contexte

Implémentation complète de l'EPIC E-Auth — passage du flow magic-link only vers email/password avec allowlist, rate-limit IP, audit log et anti-timing.

- **Spec** : [`docs/superpowers/specs/2026-05-19-eauth-refactor-design.md`](https://github.com/tellebma/garmin_training_ia/blob/main/docs/superpowers/specs/2026-05-19-eauth-refactor-design.md)
- **Plan** : [`docs/superpowers/plans/2026-05-19-eauth-refactor.md`](https://github.com/tellebma/garmin_training_ia/blob/main/docs/superpowers/plans/2026-05-19-eauth-refactor.md)
- **Findings audit Red/Blue Team intégrés** : 3 Critical (C1/C2/C3), 5 Important (I1-I5), 6 Minor (M1-M6)

## Changements

### Database
- 3 tables : `allowed_emails`, `auth_rate_limits`, `auth_events` (toutes RLS deny-all)
- 4 RPCs `security definer` : `is_email_allowed`, `email_needs_signup`, `check_and_log_auth_rate_limit`, `log_auth_event`
- Alter `athlete_profiles` : `password_set boolean default false`
- Seed owner dans `allowed_emails`

### Frontend
- 5 Server Actions avec rate-limit + audit + 800ms timing floor : `registerWithMagicLink`, `login`, `requestPasswordReset`, `setInitialPassword`, `setPasswordAfterReset`
- 5 pages : `/login` (refactor), `/register`, `/forgot-password`, `/auth/set-password`, `/auth/reset-password`
- `/auth/callback/route.ts` refactor avec `next` whitelist (C1) + check `password_set`
- Zod schemas avec blocklist top-100 + min 10 chars (M1)
- Helpers `lib/auth/client-ip.ts` (Vercel-aware) + `lib/auth/timing.ts`
- Email templates FR : `confirm-signup.html` + `reset-password.html` phishing-resistance

### Tests
- 7 fichiers de tests Vitest, ~35 tests : Zod schemas, 5 Server Actions, callback isSafeNext, anti-timing avec fake timers

## Pré-déploiement OBLIGATOIRE (C3)

Avant le merge :
1. Supabase Studio → Auth → Users → owner → "Send password recovery"
2. Owner clique le lien legacy magic-link, se logue
3. SQL : `update athlete_profiles set password_set = true where user_id = (select id from auth.users where email = 'pdmtc.bellet@gmail.com')`

**Sans cette étape, fenêtre de race condition exploitable sur le compte owner.**

## Setup Supabase Studio post-merge

Voir `supabase/email-templates/README.md` section "Setup Supabase Studio post-merge" :
1. Email Templates : coller `confirm-signup.html` et `reset-password.html`
2. URL Configuration : ajouter les 4 redirect URLs (`/auth/set-password` + `/auth/reset-password` × prod/local)
3. Vérifier 2FA activé sur le dashboard Supabase (M6)

## Test plan post-merge

- [x] `pnpm test --run` → tous verts (35+ tests auth)
- [x] `pnpm typecheck && pnpm lint && pnpm build` → clean
- [ ] **Manuel** : depuis un email externe non-owner, aller sur `/register` → "email pas autorisé"
- [ ] **Manuel** : owner essaie /login avec mauvais mdp → "Email ou mot de passe incorrect" (timing > 800ms)
- [ ] **Manuel** : /forgot-password → reçoit email → clique → /auth/reset-password → set mdp → /today
- [ ] **Manuel** : tenter `/auth/callback?next=https://evil.com&code=fake` → redirect /today (C1 plug)
- [ ] **Manuel** : tenter 4 registers consécutifs depuis la même IP → 4ème bloqué "rate_limited"
EOF
)"
```

- [ ] **Step 4: Verify CI passes, ping user**

```bash
gh pr checks
```

---

## Quality gates de référence (toutes tasks)

| Couche | Commande | Doit retourner |
|---|---|---|
| Frontend lint | `pnpm lint` | 0 errors |
| Frontend types | `pnpm typecheck` | 0 errors |
| Frontend tests | `pnpm test --run` | All passed |
| Frontend build | `pnpm build` | Compiled successfully |

---

## Cas d'erreur fréquents (anticipés)

| Symptôme | Cause probable | Fix |
|---|---|---|
| Tests Zod failed sur passwordSchema accept | Top-100 blocklist a un mot que tu utilises en test | Choisir un mdp test non-courant (ex: "M1ghty-Tr1@thlete") |
| Mock Supabase RPC `mockResolvedValueOnce` consommé trop tôt | Server Action enchaîne plus de RPC qu'attendu (rate_limit OK → is_email_allowed → email_needs_signup → log_auth_event) | Compter les RPC calls dans le mock, queue dans l'ordre |
| `mock next/navigation redirect` ne throw pas dans le test | Mock incomplet, faute d'implementation | Suivre exactement le pattern Task 8 step 2 (throw `__NEXT_REDIRECT__:${path}`) |
| `pnpm build` échoue sur prerender de /register/login | Server Component qui appelle createClient sans request context | Wrap avec `'use client'` ou utiliser dynamic rendering (déjà géré par next/headers usage) |
| Anti-timing test fixture `vi.useFakeTimers` ne marche pas | `vi.advanceTimersByTimeAsync` non-await | Tous les advance doivent être `await` |
| Supabase callback expire prematurément en local | Le redirect URL n'est pas dans la liste Supabase | Vérifier `Dashboard → Auth → URL Configuration → Redirect URLs` |
| Owner ne reçoit pas l'email d'activation | Supabase OTP rate-limit hit (3/h) ou template mal configuré | Attendre 1h ou test en incognito avec autre email allowlisté |

---

## Récap pour le user post-merge

| Action | Statut attendu |
|---|---|
| 1. Pré-deploy : Owner set password via Studio + SQL `password_set=true` | Manuel — voir Task 2 |
| 2. CI green sur la PR | Auto |
| 3. Merge PR | Manuel |
| 4. Setup Supabase Studio (templates + redirect URLs) | Manuel post-merge — voir Task 16 step 4 README |
| 5. Smoke test prod (owner se relogue avec mdp set lors du pré-deploy) | Manuel |
