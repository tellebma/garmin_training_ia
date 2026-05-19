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
- Audit log des tentatives de connexion.

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
  created_at timestamptz not null default now()
);

alter table public.allowed_emails enable row level security;
-- Pas de policies : RLS bloque tout pour anon/authenticated.
-- Le check se fait via une fonction RPC security definer (ci-dessous).
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
  select exists (select 1 from public.allowed_emails where email = p_email)
$$;

grant execute on function public.is_email_allowed(text) to anon, authenticated;
```

La fonction `security definer` exécute en tant que propriétaire (postgres) et passe au-dessus de RLS. Elle retourne uniquement un booléen — l'appelant ne voit jamais la liste entière. Pas de fuite d'enum d'emails.

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

**Fonction RPC `check_and_log_auth_rate_limit`** :

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
begin
  -- Count recent attempts for this (ip, action) within the window
  select count(*) into v_count
  from public.auth_rate_limits
  where ip = p_ip
    and action = p_action
    and created_at > now() - make_interval(secs => p_window_seconds);

  if v_count >= p_max_count then
    return false;
  end if;

  -- Log this attempt (atomic with the check via the same connection)
  insert into public.auth_rate_limits (ip, action) values (p_ip, p_action);
  return true;
end
$$;

grant execute on function public.check_and_log_auth_rate_limit(text, text, integer, integer)
  to anon, authenticated;
```

**Cleanup périodique** : pas de `pg_cron` MVP (extension non activée par défaut sur Supabase free tier). À la place, on `delete` les vieux records au début de chaque check :

```sql
-- À déclencher tous les ~100 inserts via une variante de la RPC, ou via un script cron weekly.
-- MVP : on accepte la croissance ~ <100 rows/jour, on nettoie manuellement si besoin.
delete from public.auth_rate_limits where created_at < now() - interval '7 days';
```

**Limites par action (constantes côté Server Action)** :

| Action | Max | Fenêtre | Justification |
|---|---|---|---|
| `register` | 3 | 1 heure | Évite spam SMTP + ban provider |
| `forgot_password` | 3 | 1 heure | Idem |
| `login` | 10 | 15 minutes | Tolère brute-force humain (faute de frappe) sans bloquer trop vite |

**Détection IP** côté Server Action :

```ts
import { headers } from 'next/headers'

async function clientIp(): Promise<string> {
  const h = await headers()
  // Vercel forwarde via x-forwarded-for; fallback x-real-ip; sinon 'unknown'
  const fwd = h.get('x-forwarded-for')
  if (fwd) return fwd.split(',')[0].trim()
  return h.get('x-real-ip') ?? 'unknown'
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

Un fichier `supabase/migrations/20260519000000_eauth_password_set_allowlist.sql` regroupant les six changements ci-dessus :

1. Table `allowed_emails` + RLS
2. RPC `is_email_allowed` (4.1bis)
3. Table `auth_rate_limits` + RLS + index
4. RPC `check_and_log_auth_rate_limit` (4.1ter)
5. Alter `athlete_profiles.password_set`
6. Seed owner dans `allowed_emails`

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

**Flow Register (nouveau user)**

```
[/register] form email → [Server Action registerWithMagicLink(email)]
  1. Zod parse email
  2. const { data: allowed } = await supabase.rpc('is_email_allowed', { p_email: email })
  3. si !allowed → { error: 'email_not_allowed' }
  4. supabase.auth.signInWithOtp({ email, options: { shouldCreateUser: true, emailRedirectTo: `${origin}/auth/callback?next=/auth/set-password` } })
  5. return { success: true } (UI "Lien envoyé")

[email FR confirm-signup.html, clic lien]

[GET /auth/callback?code=...&next=/auth/set-password]
  1. exchangeCodeForSession(code) → session établie
  2. profile = supabase.from('athlete_profiles').select('password_set').eq('user_id', userId).single()
  3. si !profile.password_set → redirect(next ?? '/auth/set-password')
  4. sinon → redirect('/today')

[/auth/set-password] form mdp + confirm → [Server Action setInitialPassword(password)]
  1. Zod parse (min 8, confirm match)
  2. supabase.auth.updateUser({ password })
  3. supabase.from('athlete_profiles').update({ password_set: true }).eq('user_id', userId)
  4. redirect('/onboarding')
```

**Flow Login (user avec mdp set)**

```
[/login] form email + mdp → [Server Action login(email, password)]
  1. Zod parse
  2. supabase.auth.signInWithPassword({ email, password })
  3. error → { error: 'invalid_credentials' } (UI "Email ou mot de passe incorrect")
  4. success → redirect('/today')  (le guard requireOnboarded ajustera si besoin)
```

**Flow Mot de passe oublié + reset (inclut migration legacy)**

```
[/forgot-password] form email → [Server Action requestPasswordReset(email)]
  1. Zod parse
  2. supabase.auth.resetPasswordForEmail(email, { redirectTo: `${origin}/auth/callback?next=/auth/reset-password` })
  3. ALWAYS return { success: true }

[email FR reset-password.html, clic lien]

[GET /auth/callback?code=...&next=/auth/reset-password]
  1. exchangeCodeForSession → session établie
  2. redirect(next ?? '/today')

[/auth/reset-password] form nouveau mdp + confirm → [Server Action setPasswordAfterReset(password)]
  1. Zod parse
  2. supabase.auth.updateUser({ password })
  3. supabase.from('athlete_profiles').update({ password_set: true }).eq('user_id', userId)
  4. redirect('/today')
```

**Migration owner** : tu visites `/login` après merge → clic "Mot de passe oublié" → reçois lien → set mdp → flag `password_set = true` → ensuite login normal. Aucune action automatisée.

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

`lib/auth/schemas.ts` :

```ts
import { z } from 'zod'

export const emailSchema = z.email('Email invalide')

export const passwordSchema = z
  .string()
  .min(8, 'Au moins 8 caractères')
  .max(72, 'Maximum 72 caractères') // bcrypt limit côté Supabase

export const registerSchema = z.object({
  email: emailSchema,
})

export const loginSchema = z.object({
  email: emailSchema,
  password: passwordSchema,
})

export const forgotPasswordSchema = z.object({
  email: emailSchema,
})

export const setPasswordSchema = z
  .object({
    password: passwordSchema,
    confirm: passwordSchema,
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

- Pas de leak d'enum d'emails (`/login`, `/forgot-password`).
- `allowed_emails` lecture uniquement via service-role (RLS bloque le reste).
- Validation Zod côté Server Action = autorité. Client = défense en profondeur.

## 9. Tests

| Couche | Outil | Cas couverts |
|---|---|---|
| **Frontend unit** | Vitest | Zod schemas — email format, password min 8/max 72, confirm match |
| **Server Action `registerWithMagicLink`** | Vitest + mock Supabase | (1) rejette email pas dans allowlist, (2) appelle signInWithOtp si présent, (3) ne révèle pas l'absence en retour |
| **Server Action `login`** | Vitest + mock | (1) success path, (2) erreur Supabase → message générique sans détail |
| **Server Action `setInitialPassword`** | Vitest + mock | (1) update user + flag password_set, (2) refuse si pas de session |
| **Server Action `setPasswordAfterReset`** | Vitest + mock | (1) update + flag, (2) refuse si pas de session |
| **Server Action `requestPasswordReset`** | Vitest + mock | (1) appelle resetPasswordForEmail, (2) retourne toujours success |
| **Callback route** | Test manuel | Couvert par smoke test post-merge (deep-link + flow complet) |
| **Migration DB** | Vérification via Supabase MCP | `allowed_emails` créé, RLS bloque pour anon, `password_set` ajouté, seed inséré |
| **E2E Playwright** | Skippé MVP (cohérence avec E3) | Follow-up |

## 10. Découpage en sous-livrables (input du plan)

1. **Migration DB** — `allowed_emails` + alter `athlete_profiles.password_set` + seed owner. Vérif MCP.
2. **Email templates FR** — `confirm-signup.html` (renommé) + `reset-password.html` (nouveau) + subjects + README update.
3. **Zod schemas auth** (`lib/auth/schemas.ts`) + tests Vitest.
4. **Server Actions** (`app/(auth)/_actions/auth.ts`) : 5 actions (`registerWithMagicLink`, `login`, `requestPasswordReset`, `setInitialPassword`, `setPasswordAfterReset`).
5. **`/login` refactor** — remplace MagicLinkForm par EmailPasswordForm + lien "Mot de passe oublié".
6. **`/register` page + RegisterForm**.
7. **`/forgot-password` page + ForgotPasswordForm**.
8. **`/auth/set-password` page + SetPasswordForm + session guard**.
9. **`/auth/reset-password` page** (réutilise SetPasswordForm).
10. **`/auth/callback/route.ts` refactor** — detect `next` query param + check `password_set`.
11. **Suppression** de `components/auth/magic-link-form.tsx` + nettoyage imports.
12. **Documentation Supabase config** (Redirect URLs + templates) dans `supabase/email-templates/README.md`.

Ordre conseillé : 1 → 2 → 3 → 4 → 5+6+7+8+9 (en parallèle, surfaces indépendantes) → 10 → 11+12.

## 11. Points de vigilance

- **Cohérence avec le flow magic-link existant** : `/auth/callback/route.ts` est déjà utilisé. Il faut ajouter la logique `password_set` sans casser la branche `next ?? '/today'` actuelle.
- **`shouldCreateUser=true` sur signInWithOtp** : envoie un magic link même si l'user existe déjà. C'est OK — le callback gère le routing selon `password_set`.
- **L'owner doit absolument être seedé dans `allowed_emails`** avant le merge pour ne pas se locker out.
- **Le template magic-link.html actuel est renommé en confirm-signup.html** : le contenu est OK mais le sujet doit être adapté ("Active ton compte" vs "Voici ton lien de connexion").
- **Supabase Auth rate limit** : 3 OTP/heure par défaut. Si on test le flow en local plusieurs fois rapidement, on hit ce limit. Pas un bug — c'est attendu.
- **Pas de service-role key requise côté frontend** : la fonction RPC `is_email_allowed` (section 4.1bis) est `security definer` et `grant execute to anon, authenticated` — le Server Action peut l'appeler avec le client Supabase anon standard. On évite ainsi d'ajouter `SUPABASE_SERVICE_ROLE_KEY` aux env vars Vercel.

---

**Fin du spec.**

Une fois ce spec validé par le user, on passe à `superpowers:writing-plans` pour générer le plan d'implémentation détaillé.
