# E-Auth Refactor — Design

**Date** : 2026-05-19
**Statut** : Validated (brainstorm + 3-section design review with owner)
**EPIC** : E-Auth — passage magic-link → email/password avec allowlist
**Dépendances entrantes** : E1 (auth Supabase magic link déjà en place) ✅
**Dépendances sortantes** : aucune EPIC ne dépend de ce refactor (E3/E4/etc. consomment juste `auth.users` + `athlete_profiles`, indifféremment du moyen d'auth)
**Effort estimé** : 2-2.5 jours

---

## 1. Objectif

Remplacer le flow d'authentification magic-link-only (E1) par un flow standard email+mot de passe, avec une porte d'entrée allowlist pour rester en MVP fermé.

**Pourquoi maintenant** : magic-link demande un email à chaque login (friction), pas adapté au usage quotidien que veut l'owner pour suivre son plan d'entraînement. Email+mdp est l'attendu UX d'un produit fitness.

## 2. Critères d'acceptation

- Page `/register` publique : un visiteur peut entrer son email. Si l'email est dans la table `allowed_emails`, Supabase envoie un lien d'activation. Sinon, message générique d'erreur (pas de leak).
- Premier clic du lien d'activation : l'user atterrit sur `/auth/set-password` (et pas sur `/today`) car son flag `password_set` est false. Il choisit son mdp puis est redirigé vers `/onboarding` (E3).
- Page `/login` simple : email + mdp + lien "Mot de passe oublié ?". Erreur générique en cas d'échec (pas de leak d'enum d'emails).
- Page `/forgot-password` : entre email → toujours répondre succès (sécurité) → email Supabase envoyé si l'email existe → lien renvoie vers `/auth/reset-password`.
- Page `/auth/reset-password` : nouveau mdp + confirm, met à jour le mdp Supabase, redirige vers `/today`.
- L'owner actuel (`pdmtc.bellet@gmail.com`, créé via magic link, `password_set=false` après migration) peut se reloguer en utilisant le flow "Mot de passe oublié" pour set son mdp initial.
- Aucune surface UI ne montre encore le magic link.

## 3. Choix structurants (issus du brainstorm)

| Sujet | Choix retenu | Alternatives écartées |
|---|---|---|
| Accès register | Self-service + allowlist DB | Public ouvert ; invite-only via admin |
| Login surface | Email + mdp uniquement | Email + mdp + magic-link en alternative |
| Mot de passe oublié | `supabase.auth.resetPasswordForEmail` standard | Lien custom signé / OTP code |
| Flow technique register | Magic link + redirect set-password (Approche A) | `signUp(email, password)` ; `admin.inviteUserByEmail` |
| Migration owner | Réutilisation du flow "Mot de passe oublié" | Script de migration / email blast |
| Politique mdp | Min 8 caractères, pas de complexité forcée | Min 6 (Supabase default) ; Min 12 + mix |
| Captcha | Hors scope MVP — `TODO post-MVP` dans CLAUDE.md | Activer maintenant |

YAGNI (volontairement hors scope E-Auth, à revoir post-MVP) :

- Captcha sur `/register`, `/login`, `/forgot-password` (CLAUDE.md TODO).
- 2FA / OAuth providers (Google, Apple, etc.).
- HIBP (leaked password check) — Pro plan only.

**Promu en MVP suite audit cyber** :
- Audit log `auth_events` (table insert-only, RLS deny-all, RPC insert). Sans ça, l'owner ne peut pas détecter ni investiguer un compromis.

### 3.1 Gestion `allowed_emails` (MVP vs post-MVP)

**MVP** : édition manuelle via **Supabase Studio** (Table Editor → `allowed_emails` → "+ Insert row"). L'owner est seul admin, ~30 secondes par invitation, pas besoin de UI dédiée.

**Post-MVP** : page admin `/admin/allowed-emails` quand l'owner aura besoin de déléguer ou que la liste dépasse une vingtaine d'entrées. Cette page nécessitera un système de rôles (`athlete_profiles.is_admin boolean` ou `auth.users.app_metadata.role`) — hors scope E-Auth.

## 4. Data model

### 4.1 Nouvelle table `allowed_emails`

```sql
create table if not exists public.allowed_emails (
  email text primary key,
  invited_by uuid references auth.users(id) on delete set null,
  note text,
  created_at timestamptz not null default now(),
  -- Force lowercase storage (M5 — évite mismatch case-sensitive)
  constraint allowed_emails_lowercase check (email = lower(email))
);

alter table public.allowed_emails enable row level security;
-- Pas de policies : RLS bloque tout pour anon/authenticated.
-- Le check se fait via une fonction RPC security definer (ci-dessous).

-- Trigger de notification (M6) : email owner sur tout insert (à activer une fois SMTP custom configuré).
-- MVP : on accepte le risque de leak Studio creds, on ajoute juste un index sur created_at pour faciliter l'audit manuel.
create index if not exists allowed_emails_created_at_idx on public.allowed_emails (created_at desc);
```

### 4.1bis Fonction RPC `is_email_allowed`

Évite d'exposer la service-role key au frontend Next.js — un simple `supabase.rpc('is_email_allowed', { p_email })` suffit côté Server Action.

```sql
create or replace function public.is_email_allowed(p_email text)
returns boolean
language sql
security definer
set search_path = public
stable
as $$
  -- M5 : case-insensitive
  select exists (select 1 from public.allowed_emails where email = lower(p_email))
$$;

grant execute on function public.is_email_allowed(text) to anon, authenticated;
```

La fonction `security definer` exécute en tant que propriétaire (postgres) et passe au-dessus de RLS. Elle retourne uniquement un booléen — l'appelant ne voit jamais la liste entière. Pas de fuite d'enum d'emails.

### 4.1bis-2 Fonction RPC `email_needs_signup` (anti-spam audit I3)

`is_email_allowed` ne suffit pas pour `/register` : si un email est allowlisté ET déjà inscrit avec mdp set, un attaquant peut spammer un magic-link de re-connexion vers la boîte de cet user (DoS + phishing vector). On veut envoyer un OTP **uniquement** quand l'email est allowlisté ET pas encore inscrit (ou inscrit sans mdp).

```sql
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
```

Server Action `/register` appelle d'abord `is_email_allowed` (pour le message d'erreur "pas autorisé") puis `email_needs_signup` (pour décider d'envoyer ou non l'OTP). Si allowlisté mais déjà inscrit avec mdp → réponse générique "Lien envoyé" sans envoi (anti-leak + anti-spam).

### 4.1ter Rate limit IP-based — table `auth_rate_limits` + RPC

Supabase OTP rate limit natif est par-utilisateur, pas par-IP. Un attaquant qui itère sur 100 emails différents depuis la même IP brûle 100 envois SMTP avant que Supabase intervienne, ce qui peut nous faire ban par le provider SMTP.

**Table** :

```sql
create table if not exists public.auth_rate_limits (
  id bigserial primary key,
  ip text not null,
  action text not null,            -- 'register' | 'forgot_password' | 'login'
  created_at timestamptz not null default now()
);

create index if not exists auth_rate_limits_ip_action_created_idx
  on public.auth_rate_limits (ip, action, created_at desc);

alter table public.auth_rate_limits enable row level security;
-- Pas de policies → seul le RPC security definer y accède.
```

**Fonction RPC `check_and_log_auth_rate_limit`** (avec cleanup probabiliste + hard cap, suite audit I1) :

```sql
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
  -- I1 : Hard cap par IP/24h (anti-DoS sur la table elle-même)
  select count(*) into v_daily_count
  from public.auth_rate_limits
  where ip = p_ip and created_at > now() - interval '24 hours';
  if v_daily_count >= 1000 then
    return false;
  end if;

  -- Count recent attempts pour la fenêtre demandée
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

  -- I1 : Cleanup probabiliste (1 % des calls) → pas besoin de pg_cron
  if random() < 0.01 then
    delete from public.auth_rate_limits where created_at < now() - interval '7 days';
  end if;

  return true;
end
$$;

grant execute on function public.check_and_log_auth_rate_limit(text, text, integer, integer)
  to anon, authenticated;
```

**Limites par action (constantes côté Server Action)** :

| Action | Max | Fenêtre | Justification |
|---|---|---|---|
| `register` | 3 | 1 heure | Évite spam SMTP + ban provider |
| `forgot_password` | 3 | 1 heure | Idem |
| `login` | 10 | 15 minutes | Tolère brute-force humain (faute de frappe) sans bloquer trop vite |

**Détection IP** côté Server Action (suite audit I2) :

```ts
import { headers } from 'next/headers'

/**
 * Resolve client IP. Vercel-aware ordering :
 *  1. x-vercel-forwarded-for : Vercel-only, normalized by their edge
 *  2. x-real-ip : fallback (proxies non-Vercel)
 *  3. x-forwarded-for : last resort, peut être spoofé hors-Vercel
 * En production, refuse si 'unknown' (failure-closed plutôt que open).
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

// Dans chaque Server Action sensible :
const ip = await clientIp()
if (ip === 'unknown' && process.env.NODE_ENV === 'production') {
  return { error: 'ip_unresolved' }   // failure-closed
}
```

**Intégration Server Action** :

```ts
const ip = await clientIp()
const { data: allowed } = await supabase.rpc('check_and_log_auth_rate_limit', {
  p_ip: ip,
  p_action: 'register',
  p_max_count: 3,
  p_window_seconds: 3600,
})
if (!allowed) return { error: 'rate_limited' }
// ... suite du flow (allowlist check, signInWithOtp, etc.)
```

**Limitations connues** :

- `x-forwarded-for` est manipulable (l'attaquant peut envoyer l'header lui-même), mais Vercel **écrase** systématiquement cet header avec l'IP réelle au niveau de l'edge. C'est fiable tant qu'on reste derrière Vercel.
- IPv6 : un attaquant peut basculer sur des IPs voisines du même /64. Acceptable pour MVP — Captcha post-MVP couvrira ce vecteur.
- Pas de différenciation user authentifié vs anon (volontaire : on protège l'envoi mail, pas la session).

### 4.1quater Audit log `auth_events` (suite audit I5)

Sans audit log, l'owner ne peut ni détecter ni investiguer un compromis. Table insert-only, queryable via Studio.

```sql
create table if not exists public.auth_events (
  id bigserial primary key,
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null check (event_type in (
    'register_initiated',         -- OTP envoyé via /register
    'password_set',               -- /auth/set-password réussi
    'password_reset_requested',   -- /forgot-password réussi (OTP envoyé)
    'password_reset_completed',   -- /auth/reset-password réussi
    'login_success',
    'login_failure'
  )),
  ip text,
  user_agent text,
  email text,                     -- l'email tenté (sur register / login failure, user_id peut être null)
  created_at timestamptz not null default now()
);

create index if not exists auth_events_user_created_idx
  on public.auth_events (user_id, created_at desc);
create index if not exists auth_events_event_created_idx
  on public.auth_events (event_type, created_at desc);

alter table public.auth_events enable row level security;
-- Pas de policies : RLS deny-all, on insère via le RPC ci-dessous (security definer).

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
  values (p_user_id, p_event_type, p_ip, p_user_agent, p_email)
$$;

grant execute on function public.log_auth_event(uuid, text, text, text, text)
  to anon, authenticated;
```

Chaque Server Action sensible appelle `log_auth_event` après son action principale (succès ou échec). Le `user_id` peut être null si l'opération est anonyme (register, login_failure sur email inconnu).

### 4.2 Alter `athlete_profiles`

```sql
alter table public.athlete_profiles
  add column if not exists password_set boolean not null default false;

comment on column public.athlete_profiles.password_set is
  'True after the user has chosen a password via /auth/set-password. False = magic-link-only user (legacy or freshly registered).';
```

### 4.3 Seed initial

```sql
insert into public.allowed_emails (email, note)
values ('pdmtc.bellet@gmail.com', 'owner — legacy magic-link user')
on conflict (email) do nothing;
```

L'owner pourra ainsi recréer un compte si besoin, et son flag `password_set` reste à `false` jusqu'à sa première utilisation du flow "Mot de passe oublié".

### 4.4 Migration

Un fichier `supabase/migrations/20260519000000_eauth_password_set_allowlist.sql` regroupant tous les changements ci-dessus :

1. Table `allowed_emails` + RLS + constraint lowercase + index
2. RPC `is_email_allowed` (4.1bis)
3. RPC `email_needs_signup` (4.1bis-2)
4. Table `auth_rate_limits` + RLS + index
5. RPC `check_and_log_auth_rate_limit` (4.1ter)
6. Table `auth_events` + RLS + index (4.1quater)
7. RPC `log_auth_event` (4.1quater)
8. Alter `athlete_profiles.password_set`
9. Seed owner dans `allowed_emails`

## 5. Architecture frontend

### 5.1 Arborescence

```
app/(auth)/
├── login/page.tsx                       # MOD : MagicLinkForm → EmailPasswordForm
├── register/page.tsx                    # NEW : Server Component (auth check) + RegisterForm
├── forgot-password/page.tsx             # NEW : ForgotPasswordForm
├── _actions/
│   └── auth.ts                          # NEW : 5 Server Actions
└── auth/
    ├── callback/route.ts                # MOD : check password_set + recovery type
    ├── set-password/page.tsx            # NEW : Server-side session guard + SetPasswordForm
    └── reset-password/page.tsx          # NEW : SetPasswordForm (réutilisé)

components/auth/
├── email-password-form.tsx              # NEW
├── register-form.tsx                    # NEW
├── set-password-form.tsx                # NEW (réutilisé en /auth/set-password et /auth/reset-password)
├── forgot-password-form.tsx             # NEW
├── magic-link-form.tsx                  # DELETE
└── sign-out-button.tsx                  # unchanged

lib/auth/
└── schemas.ts                           # NEW : Zod (email, password, register, set/reset)

supabase/email-templates/
├── magic-link.html                      # → renommé confirm-signup.html (utilisé par /register)
├── magic-link.subject.txt               # → renommé confirm-signup.subject.txt
├── reset-password.html                  # NEW (template FR pour resetPasswordForEmail)
├── reset-password.subject.txt           # NEW
└── README.md                            # MOD : documenter les 2 templates et leur usage
```

### 5.2 Flows

**Flow Register (nouveau user)** — intègre rate limit + audit + anti-timing + anti-spam (C2 / I3 / I5)

```
[/register] form email → [Server Action registerWithMagicLink(email)]
  0. t0 = Date.now()
  1. Zod parse email
  2. ip = clientIp() — refuse si 'unknown' en prod (I2)
  3. ok = await supabase.rpc('check_and_log_auth_rate_limit', { p_ip: ip, p_action: 'register', p_max_count: 3, p_window_seconds: 3600 })
  4. si !ok → log_auth_event(null, 'login_failure', ip, ua, email) — bucket erreurs ; return { error: 'rate_limited' } APRÈS pause anti-timing
  5. const { data: allowed } = await supabase.rpc('is_email_allowed', { p_email: email })
  6. si !allowed → return { error: 'email_not_allowed' } APRÈS pause anti-timing
  7. const { data: needsSignup } = await supabase.rpc('email_needs_signup', { p_email: email }) (I3)
     si false (= email allowlisté mais déjà actif) → ne PAS appeler signInWithOtp, return success générique APRÈS pause
  8. await supabase.auth.signInWithOtp({ email, options: { shouldCreateUser: true,
       emailRedirectTo: `${origin}/auth/callback?next=/auth/set-password` } })
  9. log_auth_event(null, 'register_initiated', ip, ua, email)
  10. C2 — anti-timing : await sleepUntil(t0 + 800ms) AVANT return
  11. return { success: true } (UI "Lien envoyé")

[email FR confirm-signup.html, clic lien]

[GET /auth/callback?code=...&next=/auth/set-password]
  1. C1 — Whitelist next : SAFE_NEXT = ['/auth/set-password','/auth/reset-password','/today','/onboarding']
     const next = SAFE_NEXT.includes(raw) ? raw : '/today'
  2. exchangeCodeForSession(code) → session établie
  3. profile = supabase.from('athlete_profiles').select('password_set').eq('user_id', userId).single()
  4. si !profile.password_set → redirect(next || '/auth/set-password')
  5. sinon → redirect('/today')

[/auth/set-password] form mdp + confirm → [Server Action setInitialPassword(password)]
  0. t0 = Date.now()
  1. Zod parse (min 10 chars, confirm match, pas dans top-100 common — M1)
  2. session check : si pas de user authentifié → redirect /login
  3. I4 — Guard : profile = select password_set ; si profile.password_set === true → return { error: 'already_set' }
     (anti session-theft → password-rotate lockout)
  4. supabase.auth.updateUser({ password })
  5. supabase.from('athlete_profiles').update({ password_set: true }).eq('user_id', userId)
  6. log_auth_event(userId, 'password_set', ip, ua, email)
  7. redirect('/onboarding')
```

**Flow Login (user avec mdp set)** — intègre rate limit + audit + anti-timing

```
[/login] form email + mdp → [Server Action login(email, password)]
  0. t0 = Date.now()
  1. Zod parse
  2. ip = clientIp() — refuse si 'unknown' en prod
  3. ok = check_and_log_auth_rate_limit(ip, 'login', max=10, window=900) — 10/15min
  4. si !ok → return { error: 'rate_limited' } APRÈS pause anti-timing
  5. { error } = await supabase.auth.signInWithPassword({ email, password })
  6. si error → log_auth_event(null, 'login_failure', ip, ua, email)
              → return { error: 'invalid_credentials' } APRÈS pause anti-timing
  7. log_auth_event(userId, 'login_success', ip, ua, email)
  8. await sleepUntil(t0 + 800ms)
  9. redirect('/today')  (le guard requireOnboarded ajustera si besoin)
```

**Flow Mot de passe oublié + reset** — intègre rate limit + audit + anti-timing (C2 / I5)

```
[/forgot-password] form email → [Server Action requestPasswordReset(email)]
  0. t0 = Date.now()
  1. Zod parse
  2. ip = clientIp() — refuse si 'unknown' en prod
  3. ok = check_and_log_auth_rate_limit(ip, 'forgot_password', max=3, window=3600)
  4. si !ok → return { success: true } APRÈS pause (toujours success-générique — C2)
  5. await supabase.auth.resetPasswordForEmail(email, { redirectTo: `${origin}/auth/callback?next=/auth/reset-password` })
  6. log_auth_event(null, 'password_reset_requested', ip, ua, email)
  7. await sleepUntil(t0 + 800ms)
  8. return { success: true } (toujours)

[email FR reset-password.html, clic lien]

[GET /auth/callback?code=...&next=/auth/reset-password]
  1. C1 — Whitelist next (idem flow register)
  2. exchangeCodeForSession → session établie
  3. redirect(next || '/today')

[/auth/reset-password] form nouveau mdp + confirm → [Server Action setPasswordAfterReset(password)]
  1. Zod parse (min 10 chars, confirm match, pas dans top-100 common — M1)
  2. session check : si pas de user authentifié → redirect /login
  3. supabase.auth.updateUser({ password })
  4. supabase.from('athlete_profiles').update({ password_set: true }).eq('user_id', userId)
  5. log_auth_event(userId, 'password_reset_completed', ip, ua, email)
  6. redirect('/today')
```

**Migration owner — C3 attention** : avant le déploiement public de cette EPIC, l'owner DOIT déjà avoir un mdp set. Procédure :
1. Avant le merge : ouvrir Supabase Studio → Authentication → Users → cliquer sur l'owner → "Send password recovery". Recevoir l'email, set le mdp via le lien (qui ouvre le flow legacy magic-link).
2. Une fois `password_set` flag mis en place (post-migration), passer `password_set = true` manuellement pour l'owner via SQL :
   ```sql
   update public.athlete_profiles set password_set = true
   where user_id = (select id from auth.users where email = 'pdmtc.bellet@gmail.com');
   ```
3. Vérifier que `select password_set from athlete_profiles where ...` retourne `true`.
4. **Seulement après**, faire le deploy de la nouvelle UI.

Le but : ne **jamais** laisser l'état `password_set = false` exister en prod, car une fenêtre attaquable se crée (un attaquant qui spamme `/forgot-password` sur l'email owner pourrait racer la légitime).

### 5.3 Réutilisation maximale

- `SetPasswordForm` est utilisé par `/auth/set-password` ET `/auth/reset-password` (mêmes champs, même validation). La page distincte sert à appeler la bonne Server Action (initial vs reset) et à afficher un titre/CTA approprié.
- `lib/auth/schemas.ts` partagé entre tous les forms (DRY).
- Pattern Server Action identique à `app/(app)/onboarding/actions.ts` (E3) : `'use server'`, Zod parse + Supabase + return `{ success, error?, errors? }`.

## 6. Supabase config (manuel post-merge)

**Dashboard → Auth → URL Configuration → Redirect URLs** : ajouter
- `https://garmin-training-ia.vercel.app/auth/set-password`
- `https://garmin-training-ia.vercel.app/auth/reset-password`
- `http://localhost:3000/auth/set-password` (dev)
- `http://localhost:3000/auth/reset-password` (dev)

**Dashboard → Auth → Email Templates** : remplacer
- "Magic Link" → renommé "Confirm signup" : contenu du nouveau `supabase/email-templates/confirm-signup.html`
- "Reset Password" : contenu du nouveau `supabase/email-templates/reset-password.html`

**Dashboard → Auth → Providers → Email** : s'assurer que "Enable email signup" reste ON et "Confirm email" reste ON (déjà le cas).

Documentation à mettre à jour : `supabase/email-templates/README.md` listant les 2 templates et leur déclenchement.

## 7. Validation (Zod schemas)

`lib/auth/schemas.ts` (intègre audit M1) :

```ts
import { z } from 'zod'

export const emailSchema = z
  .email('Email invalide')
  .transform((s) => s.toLowerCase().trim())   // M5 cohérence case-insensitive

// Top-100 most common passwords — bloque les compromise rapides
// Sourcé d'une liste publique (NCSC top-100 2019 + SecLists 1k).
const COMMON_PASSWORDS = new Set([
  'password', 'password1', '12345678', '123456789', 'qwerty123',
  'azerty123', 'iloveyou', 'admin123', 'welcome1', 'monkey123',
  // … 90 autres en MVP, dans le fichier final
])

export const passwordSchema = z
  .string()
  .min(10, 'Au moins 10 caractères')          // M1 — promu de 8 à 10
  .max(72, 'Maximum 72 caractères')           // bcrypt Supabase
  .refine((p) => !COMMON_PASSWORDS.has(p.toLowerCase()), {
    message: 'Mot de passe trop courant — choisis-en un autre',
  })

export const registerSchema = z.object({
  email: emailSchema,
})

export const loginSchema = z.object({
  email: emailSchema,
  password: z.string().min(1, 'Requis').max(72), // login : pas de check complexité (l'user a déjà choisi)
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
```

## 8. Error handling

| Source | Cas | Comportement UI |
|---|---|---|
| `/register` | Email format invalide | Zod inline |
| `/register` | Email pas dans allowlist | Toast "Cet email n'est pas autorisé à s'inscrire. Contacte l'admin." |
| `/register` | Email déjà inscrit avec mdp | `shouldCreateUser=true` est tolérant : Supabase envoie quand même un lien magic. Au callback, si `password_set === true`, on redirige direct `/today` |
| `/login` | Email inconnu OU mdp faux | Toast unique "Email ou mot de passe incorrect" |
| `/forgot-password` | Email inconnu | Toast "Si cet email existe, un lien a été envoyé" |
| `/auth/set-password` | Pas de session active (deep-link direct sans avoir cliqué le mail) | Server Component redirect `/login` |
| `/auth/set-password` | Mdp < 8 OR mdp ≠ confirm | Zod inline |
| `/auth/reset-password` | Pas de session (lien expiré) | Toast "Lien expiré, redemande un reset" + redirect `/forgot-password` |
| Supabase rate limit | Toast "Trop de tentatives, réessaie dans quelques minutes" | Supabase OTP rate limit natif (3/h) |
| Rate limit IP custom (`register` / `forgot_password`) | Toast "Trop de tentatives depuis ton IP, réessaie dans 1 heure" | Notre RPC `check_and_log_auth_rate_limit` retourne `false` |
| Rate limit IP custom (`login`) | Toast "Trop de tentatives, réessaie dans 15 minutes" | Idem |

**Sécurité — choix explicites** :

- Pas de leak d'enum d'emails (`/login`, `/forgot-password`, `/register` retournent toujours success-générique).
- `allowed_emails` lecture uniquement via RPC `security definer` (RLS bloque l'accès direct).
- Validation Zod côté Server Action = autorité. Client = défense en profondeur.
- **C2 — Anti-timing** : chaque Server Action auth-sensible (`registerWithMagicLink`, `login`, `requestPasswordReset`) garantit un **minimum 800ms** de temps d'exécution avant return, quel que soit le résultat. Helper utilitaire :

  ```ts
  export async function sleepUntil(targetMs: number): Promise<void> {
    const remaining = targetMs - Date.now()
    if (remaining > 0) await new Promise((r) => setTimeout(r, remaining))
  }
  ```

  Sans ça, un attaquant peut différentier `email_not_allowed` (~5ms RPC) vs `signInWithOtp` (~200-800ms SMTP) par mesure de latence et enum la liste.

- **M2 — Cookies Supabase Auth** : Supabase met `Secure=true`, `HttpOnly=true`, `SameSite=Lax` par défaut. À vérifier post-deploy via devtools navigateur et documenter dans `supabase/email-templates/README.md`.

- **M4 — CSRF** : toutes les mutations d'auth passent par des Next.js Server Actions (POST avec `Origin` header verifié par le framework). Pas de protection custom additionnelle nécessaire.

- **M3 — Email phishing-resistance** : les templates FR (`confirm-signup.html` et `reset-password.html`) DOIVENT :
  - Afficher l'URL complète du lien (pas seulement un anchor "Cliquer ici")
  - Inclure une phrase de contexte vérifiable par l'user : "Ce lien a été demandé depuis l'IP {ip} le {datetime}" (substitution via Supabase template vars)
  - Mentionner le domaine d'envoi attendu (`noreply@<supabase-domain>` ou domaine custom une fois SMTP custom configuré)
  - Avertir explicitement : "Si tu n'as pas demandé ce lien, ignore cet email — aucune action ne sera prise."

## 9. Tests

| Couche | Outil | Cas couverts |
|---|---|---|
| **Frontend unit** | Vitest | Zod schemas — email format, password min 8/max 72, confirm match |
| **Server Action `registerWithMagicLink`** | Vitest + mock Supabase | (1) rejette email pas dans allowlist, (2) appelle signInWithOtp si présent, (3) ne révèle pas l'absence en retour |
| **Server Action `login`** | Vitest + mock | (1) success path, (2) erreur Supabase → message générique sans détail |
| **Server Action `setInitialPassword`** | Vitest + mock | (1) update user + flag password_set, (2) refuse si pas de session |
| **Server Action `setPasswordAfterReset`** | Vitest + mock | (1) update + flag, (2) refuse si pas de session |
| **Server Action `requestPasswordReset`** | Vitest + mock | (1) appelle resetPasswordForEmail, (2) retourne toujours success |
| **Anti-timing** (C2) | Vitest + fake timers | Chaque action `registerWithMagicLink` / `login` / `requestPasswordReset` prend min 800ms même si elle "échoue" tôt (rate limit ou email not allowed) |
| **Rate limit IP** (I1/I2) | Vitest + mock RPC | (1) Premier appel passe, 4ème dans la même fenêtre bloque (register max=3), (2) IP `unknown` en prod refuse, (3) hard cap 1000/24h respecté |
| **Anti-spam I3** | Vitest + mock | Register sur email allowlisté + active → réponse success-générique SANS appel à signInWithOtp |
| **Set-password guard I4** | Vitest + mock | setInitialPassword refuse si `password_set=true` déjà |
| **Audit log I5** | Vitest + mock | Chaque action logue l'event approprié dans `auth_events` |
| **Open redirect C1** | Vitest sur callback handler | `next=https://evil.com` → fallback `/today` ; `next=/auth/set-password` → autorisé |
| **Callback route** | Test manuel | Couvert par smoke test post-merge (deep-link + flow complet) |
| **Migration DB** | Vérification via Supabase MCP | Tables + RPCs + RLS + indexes créés, `password_set` ajouté, seed inséré, contrainte lowercase active |
| **E2E Playwright** | Skippé MVP (cohérence avec E3) | Follow-up |

## 10. Découpage en sous-livrables (input du plan)

1. **Migration DB** — `allowed_emails` (+ constraint lowercase, index), `auth_rate_limits` (+ index), `auth_events` (+ indexes), 4 RPCs (`is_email_allowed`, `email_needs_signup`, `check_and_log_auth_rate_limit`, `log_auth_event`), alter `athlete_profiles.password_set`, seed owner. Vérif MCP.
2. **Pré-déploiement owner** — Supabase Studio "Send password recovery" sur l'owner + force `password_set=true` via SQL. **CRITIQUE — à faire avant tout deploy UI.**
3. **Email templates FR** — `confirm-signup.html` (renommé + phishing-resistance M3) + `reset-password.html` (nouveau, idem) + subjects + README update.
4. **Zod schemas auth** (`lib/auth/schemas.ts`) + blocklist top-100 + tests Vitest.
5. **Utilitaires auth** (`lib/auth/`) : `clientIp.ts` (Vercel-aware), `timing.ts` (sleepUntil 800ms helper), `ip-guard.ts` (refuse 'unknown' en prod).
6. **Server Actions** (`app/(auth)/_actions/auth.ts`) : 5 actions intégrant rate limit + audit log + anti-timing :
   - `registerWithMagicLink` (rate limit + is_email_allowed + email_needs_signup + signInWithOtp + log)
   - `login` (rate limit + signInWithPassword + log success/failure)
   - `requestPasswordReset` (rate limit + resetPasswordForEmail + log)
   - `setInitialPassword` (session guard + I4 guard password_set=false required + updateUser + flag + log)
   - `setPasswordAfterReset` (session guard + updateUser + flag + log)
7. **`/login` refactor** — remplace MagicLinkForm par EmailPasswordForm + lien "Mot de passe oublié".
8. **`/register` page + RegisterForm**.
9. **`/forgot-password` page + ForgotPasswordForm**.
10. **`/auth/set-password` page + SetPasswordForm + session guard**.
11. **`/auth/reset-password` page** (réutilise SetPasswordForm).
12. **`/auth/callback/route.ts` refactor** — whitelist `next` (C1) + check `password_set`.
13. **Suppression** de `components/auth/magic-link-form.tsx` + nettoyage imports.
14. **Documentation Supabase config** (Redirect URLs + 2FA admin + templates) dans `supabase/email-templates/README.md`.

Ordre conseillé : 1 → 2 (manuel, owner) → 3 → 4 → 5 → 6 → 7+8+9+10+11 (parallèles) → 12 → 13+14.

## 11. Points de vigilance (audit cyber Red/Blue Team intégré)

### Pré-requis avant deploy (checklist obligatoire)

- [ ] **C3 — Owner password pré-set** : avant la mise en prod, l'owner a un mdp set via Supabase Studio → Authentication → "Send password recovery". Le flag `password_set = true` est forcé manuellement dans `athlete_profiles` pour l'owner. Aucun user en `password_set=false` ne doit exister en prod (sinon fenêtre attaquable).
- [ ] **Allowlist seedée** : l'owner est dans `allowed_emails` (script de migration le fait, vérifier post-apply).
- [ ] **Supabase Dashboard 2FA activé** (M6) : protège la surface critique d'admin (édition Studio = ajout d'emails à l'allowlist).
- [ ] **Redirect URLs** dans Auth → URL Configuration : `/auth/set-password` et `/auth/reset-password` ajoutés (prod + previews + localhost).
- [ ] **Email templates FR** importés via Studio (`confirm-signup.html` renommé du magic-link, `reset-password.html` nouveau).

### Risques résiduels acceptés (à revoir post-MVP)

- **Pas de Captcha** : OK tant que la surface est privée (allowlist + rate limit IP). À ajouter dès qu'on ouvre publiquement.
- **Pas de 2FA app** : `auth_events` permet de détecter rétroactivement une compromission. Pas de protection préventive.
- **IPv6 /64 rotation** : un attaquant déterminé peut bypasser le rate limit IP en utilisant des IPs voisines. Acceptable car Captcha post-MVP couvre ce cas.
- **`shouldCreateUser=true` sur `signInWithOtp`** : on filtre maintenant en amont via `email_needs_signup` (I3), donc on n'envoie pas d'OTP à un user déjà actif. Pas de spam SMTP possible sur les comptes existants.
- **Pas de service-role key requise côté frontend** : RPC `security definer` partout. Surface d'exposition minimale.

### Points opérationnels

- **Cohérence avec le flow magic-link existant** : `/auth/callback/route.ts` est refactor pour gérer `next` whitelisté + check `password_set`. Tester le flow legacy magic-link continue de fonctionner pendant la transition (avant le merge UI register).
- **Le template magic-link.html actuel est renommé en confirm-signup.html** : contenu adapté pour le sujet ("Active ton compte" au lieu de "Voici ton lien de connexion") + phrase de contexte phishing-resistant (M3).
- **Supabase Auth rate limit natif** : 3 OTP/heure par utilisateur. Notre rate limit IP-based ajoute une couche par IP. Les deux se complètent.
- **Audit log queryable** : l'owner peut investiguer un incident via `select * from auth_events where event_type = 'login_failure' order by created_at desc limit 100` dans Studio.

---

**Fin du spec.**

Une fois ce spec validé par le user, on passe à `superpowers:writing-plans` pour générer le plan d'implémentation détaillé.
