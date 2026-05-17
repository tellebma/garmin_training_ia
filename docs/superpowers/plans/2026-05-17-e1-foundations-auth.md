# E1 — Foundations & Auth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap a Next.js 15 PWA with Supabase auth (magic link), initial DB schema, mobile-first responsive layout, and Vercel CI/CD — providing the foundation on which all other EPICs build.

**Architecture:** Next.js 15 App Router with TypeScript and Tailwind + shadcn/ui. Supabase handles auth (magic link only — no passwords), database (Postgres + RLS), and is consumed via `@supabase/ssr` for server-component-friendly session management. PWA is enabled via `@ducanh2912/next-pwa` (the maintained fork of next-pwa) producing a service worker and web manifest. Vercel hosts the front, with environment variables injected for Supabase keys. Tests use Vitest (unit) and Playwright (E2E for critical auth flow).

**Tech Stack:** Next.js 15, TypeScript 5, Tailwind CSS 4, shadcn/ui (Radix + Tailwind), Supabase JS v2 + @supabase/ssr, @ducanh2912/next-pwa, Vitest, Playwright, pnpm, Vercel.

**Spec reference:** `docs/superpowers/specs/2026-05-17-garmin-training-design.md` § 7 (E1).

---

## File Structure

```
garmin_training/
├── app/
│   ├── (auth)/
│   │   ├── login/page.tsx              ← sign-in page (magic link form)
│   │   └── auth/callback/route.ts      ← OAuth callback (Supabase email link redirect)
│   ├── (app)/
│   │   ├── layout.tsx                  ← protected layout (sidebar + bottom nav)
│   │   ├── today/page.tsx              ← landing after login (empty for E1, real in E6)
│   │   └── profile/page.tsx            ← read-only profile (full edit comes in E3)
│   ├── layout.tsx                      ← root layout (HTML, PWA meta tags)
│   ├── page.tsx                        ← marketing/landing redirect to /login or /today
│   ├── globals.css                     ← Tailwind base + shadcn variables
│   └── manifest.webmanifest            ← PWA manifest
├── components/
│   ├── ui/                             ← shadcn-generated components (button, input, etc.)
│   ├── nav/
│   │   ├── bottom-nav.tsx              ← mobile bottom navigation
│   │   └── side-nav.tsx                ← desktop sidebar
│   └── auth/
│       └── magic-link-form.tsx         ← email input + submit
├── lib/
│   ├── supabase/
│   │   ├── client.ts                   ← browser client (singleton)
│   │   ├── server.ts                   ← server component / route handler client
│   │   └── middleware.ts               ← session refresh helper
│   └── env.ts                          ← typed env var validation (zod)
├── middleware.ts                       ← Next.js middleware (route protection + session refresh)
├── supabase/
│   └── migrations/
│       └── 20260517000000_initial_schema.sql
├── public/
│   ├── icons/                          ← PWA icons (192, 512, maskable)
│   └── favicon.ico
├── tests/
│   ├── unit/
│   │   └── env.test.ts
│   └── e2e/
│       └── auth.spec.ts
├── .env.local.example
├── .gitignore
├── next.config.mjs                     ← Next config + next-pwa wrapper
├── tailwind.config.ts
├── tsconfig.json
├── package.json
├── playwright.config.ts
├── vitest.config.ts
├── components.json                     ← shadcn config
└── README.md
```

**Key boundaries:**
- `app/(auth)/*` — unauthenticated routes
- `app/(app)/*` — authenticated routes (protected by middleware)
- `lib/supabase/*` — the only place Supabase clients are instantiated
- `supabase/migrations/*` — single source of truth for the DB schema
- Tests are colocated under `tests/`, mirroring `app/` and `lib/` paths

---

## Prerequisites

Before starting, ensure:

- [ ] Node.js 20+ installed (`node -v` → v20.x or v22.x)
- [ ] pnpm installed (`pnpm -v` → 9.x). If not: `npm i -g pnpm`
- [ ] A Supabase account (https://supabase.com) — free tier
- [ ] A Vercel account (https://vercel.com) — free tier
- [ ] Git configured locally

---

## Task 1: Initialize Next.js project

**Files:**
- Create: `package.json`, `tsconfig.json`, `next.config.mjs`, `app/layout.tsx`, `app/page.tsx`, `app/globals.css`, `.gitignore`

- [ ] **Step 1.1: Scaffold the Next.js app**

Run from `/home/tellebma/DEV/garmin_training`:

```bash
pnpm create next-app@latest . --typescript --tailwind --app --no-src-dir --import-alias "@/*" --use-pnpm --no-eslint
```

When prompted, accept overwriting if it asks (the directory currently only has `.git/` and `docs/`).

Expected output: scaffolded project with `app/`, `package.json`, `tailwind.config.ts`, `next.config.mjs`.

- [ ] **Step 1.2: Verify dev server starts**

```bash
pnpm dev
```

Expected: dev server on http://localhost:3000, "Next.js" welcome page renders. Kill with Ctrl+C.

- [ ] **Step 1.3: Pin Next.js to 15.x**

Check `package.json` shows `"next": "^15.x"`. If lower, update:

```bash
pnpm add next@latest react@latest react-dom@latest
```

- [ ] **Step 1.4: Commit**

```bash
git add .
git commit -m "chore: scaffold Next.js 15 with TypeScript and Tailwind"
```

---

## Task 2: Add tooling — Vitest, Playwright, zod, env validation

**Files:**
- Create: `vitest.config.ts`, `playwright.config.ts`, `lib/env.ts`, `tests/unit/env.test.ts`, `.env.local.example`
- Modify: `package.json` (add scripts)

- [ ] **Step 2.1: Install test and validation deps**

```bash
pnpm add -D vitest @vitejs/plugin-react @playwright/test
pnpm add zod
pnpm exec playwright install chromium
```

Expected: `vitest`, `@playwright/test`, `zod` added.

- [ ] **Step 2.2: Create `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts'],
    globals: false,
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, '.') },
  },
})
```

- [ ] **Step 2.3: Create `playwright.config.ts`**

```ts
import { defineConfig, devices } from '@playwright/test'

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  fullyParallel: true,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:3000',
    trace: 'on-first-retry',
  },
  webServer: {
    command: 'pnpm dev',
    url: 'http://localhost:3000',
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
  projects: [
    { name: 'chromium', use: { ...devices['Desktop Chrome'] } },
  ],
})
```

- [ ] **Step 2.4: Add scripts to `package.json`**

In `package.json`, add to `scripts`:

```json
"test": "vitest run",
"test:watch": "vitest",
"test:e2e": "playwright test",
"typecheck": "tsc --noEmit"
```

- [ ] **Step 2.5: Write the failing test for env validation**

Create `tests/unit/env.test.ts`:

```ts
import { describe, it, expect } from 'vitest'

describe('env', () => {
  it('throws when NEXT_PUBLIC_SUPABASE_URL is missing', async () => {
    const original = process.env.NEXT_PUBLIC_SUPABASE_URL
    delete process.env.NEXT_PUBLIC_SUPABASE_URL
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
    await expect(import('@/lib/env?missing-url')).rejects.toThrow(/NEXT_PUBLIC_SUPABASE_URL/)
    process.env.NEXT_PUBLIC_SUPABASE_URL = original
  })

  it('parses valid env vars', async () => {
    process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
    process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
    const { env } = await import('@/lib/env')
    expect(env.NEXT_PUBLIC_SUPABASE_URL).toBe('https://example.supabase.co')
  })
})
```

- [ ] **Step 2.6: Run test to verify it fails**

```bash
pnpm test
```

Expected: FAIL — module `@/lib/env` not found.

- [ ] **Step 2.7: Implement `lib/env.ts`**

```ts
import { z } from 'zod'

const envSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().url(),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string().min(1),
})

const parsed = envSchema.safeParse({
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
})

if (!parsed.success) {
  const issues = parsed.error.issues
    .map((i) => `- ${i.path.join('.')}: ${i.message}`)
    .join('\n')
  throw new Error(`Invalid environment variables:\n${issues}`)
}

export const env = parsed.data
```

- [ ] **Step 2.8: Run test to verify it passes**

```bash
pnpm test
```

Expected: PASS, 2 tests.

- [ ] **Step 2.9: Create `.env.local.example`**

```bash
# Supabase project URL (from https://supabase.com/dashboard/project/<id>/settings/api)
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co

# Supabase anon (public) key — safe to expose to the browser
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
```

- [ ] **Step 2.10: Update `.gitignore`**

Append to `.gitignore`:

```
.env.local
.env*.local
test-results/
playwright-report/
.next/
```

- [ ] **Step 2.11: Commit**

```bash
git add -A
git commit -m "chore: add Vitest, Playwright, zod env validation"
```

---

## Task 3: Create Supabase project and run initial migration

**Files:**
- Create: `supabase/migrations/20260517000000_initial_schema.sql`

This task involves manual setup in the Supabase UI plus running the migration.

- [ ] **Step 3.1: Create Supabase project**

Manual action by the engineer:

1. Go to https://supabase.com/dashboard
2. Click "New project"
3. Name: `garmin-training-dev`
4. Region: `Europe (Frankfurt)` (eu-central-1)
5. Database password: generate strong, save in password manager
6. Wait ~2 minutes for provisioning

Once ready, copy from "Project Settings → API":
- `Project URL` → goes in `NEXT_PUBLIC_SUPABASE_URL`
- `anon public` key → goes in `NEXT_PUBLIC_SUPABASE_ANON_KEY`

- [ ] **Step 3.2: Create `.env.local`**

Copy `.env.local.example` to `.env.local` and fill in the real values from Step 3.1.

```bash
cp .env.local.example .env.local
# Then edit .env.local with real values
```

- [ ] **Step 3.3: Write the initial migration**

Create `supabase/migrations/20260517000000_initial_schema.sql`:

```sql
-- E1 — Foundations & Auth — initial schema
-- Creates the bare-minimum tables required for the auth flow and profile bootstrap.
-- Other tables (activities, plans, etc.) are added in their respective EPICs.

-- =========================================
-- Table: athlete_profiles
-- One row per authenticated user. Created on first login.
-- =========================================
create table public.athlete_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  first_name text,
  dob date,
  sex text check (sex in ('M', 'F', 'X') or sex is null),
  city text,
  country text,
  lat numeric(9,6),
  lon numeric(9,6),
  ftp_watts integer check (ftp_watts is null or ftp_watts between 50 and 600),
  vma_kmh numeric(4,2) check (vma_kmh is null or vma_kmh between 5 and 30),
  fc_max_bpm integer check (fc_max_bpm is null or fc_max_bpm between 100 and 230),
  sports_strengths jsonb default '{}'::jsonb,
  available_days jsonb default '[]'::jsonb,
  consent_data_processing boolean not null default false,
  consent_signed_at timestamptz,
  onboarding_completed_at timestamptz,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================================
-- Table: garmin_credentials
-- One row per user. Tokens stored encrypted.
-- =========================================
create table public.garmin_credentials (
  user_id uuid primary key references auth.users(id) on delete cascade,
  oauth_tokens_encrypted bytea,
  last_sync_at timestamptz,
  last_sync_status text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- =========================================
-- Function: auto-create athlete_profile on signup
-- =========================================
create or replace function public.handle_new_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
  insert into public.athlete_profiles (user_id)
  values (new.id);
  return new;
end;
$$;

create trigger on_auth_user_created
  after insert on auth.users
  for each row execute procedure public.handle_new_user();

-- =========================================
-- Row Level Security
-- =========================================
alter table public.athlete_profiles enable row level security;
alter table public.garmin_credentials enable row level security;

-- athlete_profiles policies
create policy "users read own profile"
  on public.athlete_profiles for select
  using (auth.uid() = user_id);

create policy "users update own profile"
  on public.athlete_profiles for update
  using (auth.uid() = user_id);

-- garmin_credentials policies
create policy "users read own credentials"
  on public.garmin_credentials for select
  using (auth.uid() = user_id);

create policy "users insert own credentials"
  on public.garmin_credentials for insert
  with check (auth.uid() = user_id);

create policy "users update own credentials"
  on public.garmin_credentials for update
  using (auth.uid() = user_id);

create policy "users delete own credentials"
  on public.garmin_credentials for delete
  using (auth.uid() = user_id);

-- =========================================
-- Updated_at trigger
-- =========================================
create or replace function public.touch_updated_at()
returns trigger language plpgsql as $$
begin
  new.updated_at = now();
  return new;
end;
$$;

create trigger trg_athlete_profiles_updated_at
  before update on public.athlete_profiles
  for each row execute procedure public.touch_updated_at();

create trigger trg_garmin_credentials_updated_at
  before update on public.garmin_credentials
  for each row execute procedure public.touch_updated_at();
```

- [ ] **Step 3.4: Apply the migration via Supabase Dashboard**

Manual action:

1. In Supabase dashboard → "SQL Editor"
2. New query
3. Paste the entire content of `supabase/migrations/20260517000000_initial_schema.sql`
4. Click "Run"

Expected: green "Success. No rows returned" message. No errors.

- [ ] **Step 3.5: Verify the schema**

In Supabase SQL Editor, run:

```sql
select table_name
from information_schema.tables
where table_schema = 'public'
order by table_name;
```

Expected output:
```
athlete_profiles
garmin_credentials
```

Also verify RLS:

```sql
select tablename, rowsecurity
from pg_tables
where schemaname = 'public';
```

Expected: both tables show `rowsecurity = true`.

- [ ] **Step 3.6: Commit**

```bash
git add supabase/
git commit -m "feat(db): initial schema with athlete_profiles and garmin_credentials + RLS"
```

---

## Task 4: Supabase client setup

**Files:**
- Create: `lib/supabase/client.ts`, `lib/supabase/server.ts`, `lib/supabase/middleware.ts`

- [ ] **Step 4.1: Install Supabase SDK**

```bash
pnpm add @supabase/supabase-js @supabase/ssr
```

- [ ] **Step 4.2: Create browser client**

Create `lib/supabase/client.ts`:

```ts
import { createBrowserClient } from '@supabase/ssr'
import { env } from '@/lib/env'

export function createClient() {
  return createBrowserClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY
  )
}
```

- [ ] **Step 4.3: Create server client**

Create `lib/supabase/server.ts`:

```ts
import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'
import { env } from '@/lib/env'

export async function createClient() {
  const cookieStore = await cookies()
  return createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return cookieStore.getAll()
        },
        setAll(cookiesToSet) {
          try {
            cookiesToSet.forEach(({ name, value, options }) =>
              cookieStore.set(name, value, options)
            )
          } catch {
            // Called from a server component — cookies cannot be set there,
            // ignore safely (middleware handles refresh).
          }
        },
      },
    }
  )
}
```

- [ ] **Step 4.4: Create middleware session helper**

Create `lib/supabase/middleware.ts`:

```ts
import { createServerClient } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'
import { env } from '@/lib/env'

export async function updateSession(request: NextRequest) {
  let response = NextResponse.next({ request })

  const supabase = createServerClient(
    env.NEXT_PUBLIC_SUPABASE_URL,
    env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
    {
      cookies: {
        getAll() {
          return request.cookies.getAll()
        },
        setAll(cookiesToSet) {
          cookiesToSet.forEach(({ name, value }) =>
            request.cookies.set(name, value)
          )
          response = NextResponse.next({ request })
          cookiesToSet.forEach(({ name, value, options }) =>
            response.cookies.set(name, value, options)
          )
        },
      },
    }
  )

  const { data: { user } } = await supabase.auth.getUser()

  const url = new URL(request.url)
  const isAuthRoute =
    url.pathname.startsWith('/login') || url.pathname.startsWith('/auth')
  const isPublicAsset =
    url.pathname.startsWith('/_next') ||
    url.pathname.startsWith('/icons') ||
    url.pathname === '/manifest.webmanifest' ||
    url.pathname === '/favicon.ico'

  if (!user && !isAuthRoute && !isPublicAsset && url.pathname !== '/') {
    const redirectUrl = new URL('/login', request.url)
    return NextResponse.redirect(redirectUrl)
  }

  if (user && isAuthRoute) {
    return NextResponse.redirect(new URL('/today', request.url))
  }

  return response
}
```

- [ ] **Step 4.5: Create root middleware**

Create `middleware.ts` (at project root, not in `lib/`):

```ts
import { type NextRequest } from 'next/server'
import { updateSession } from '@/lib/supabase/middleware'

export async function middleware(request: NextRequest) {
  return await updateSession(request)
}

export const config = {
  matcher: [
    '/((?!_next/static|_next/image|favicon.ico|.*\\.(?:svg|png|jpg|jpeg|gif|webp|ico)$).*)',
  ],
}
```

- [ ] **Step 4.6: Verify typecheck**

```bash
pnpm typecheck
```

Expected: no errors.

- [ ] **Step 4.7: Commit**

```bash
git add lib/ middleware.ts package.json pnpm-lock.yaml
git commit -m "feat(auth): Supabase client (browser + server) and session middleware"
```

---

## Task 5: Install shadcn/ui

**Files:**
- Create: `components.json`, `components/ui/button.tsx`, `components/ui/input.tsx`, `components/ui/label.tsx`, `components/ui/sonner.tsx`
- Modify: `app/globals.css`, `tailwind.config.ts`

- [ ] **Step 5.1: Initialize shadcn**

```bash
pnpm dlx shadcn@latest init
```

When prompted:
- Style: `Default`
- Base color: `Slate`
- CSS variables: `Yes`

Expected: `components.json` created, `app/globals.css` updated with theme variables, `lib/utils.ts` created with `cn` helper.

- [ ] **Step 5.2: Add core components**

```bash
pnpm dlx shadcn@latest add button input label sonner card
```

Expected: `components/ui/button.tsx`, `input.tsx`, `label.tsx`, `sonner.tsx`, `card.tsx` created.

- [ ] **Step 5.3: Force dark mode by default in `app/layout.tsx`**

Open `app/layout.tsx` and set `className="dark"` on the `<html>` tag:

```tsx
import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Garmin Training Coach',
  description: 'Plan triathlon personnalisé basé sur tes données Garmin',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="fr" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  )
}
```

- [ ] **Step 5.4: Verify the dev server still renders**

```bash
pnpm dev
```

Visit http://localhost:3000 — should render dark background. Kill with Ctrl+C.

- [ ] **Step 5.5: Commit**

```bash
git add -A
git commit -m "feat(ui): install shadcn/ui with dark mode default"
```

---

## Task 6: Magic link sign-in page

**Files:**
- Create: `app/(auth)/login/page.tsx`, `app/(auth)/auth/callback/route.ts`, `components/auth/magic-link-form.tsx`

- [ ] **Step 6.1: Create the magic link form component**

Create `components/auth/magic-link-form.tsx`:

```tsx
'use client'

import { useState } from 'react'
import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'

export function MagicLinkForm() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  async function handleSubmit(e: React.FormEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)

    const supabase = createClient()
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    })

    setLoading(false)

    if (error) {
      toast.error(`Erreur: ${error.message}`)
      return
    }

    setSent(true)
  }

  if (sent) {
    return (
      <div className="text-center space-y-2">
        <h2 className="text-xl font-semibold">Vérifie tes emails</h2>
        <p className="text-sm text-muted-foreground">
          Un lien de connexion a été envoyé à <strong>{email}</strong>.
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-4 w-full max-w-sm">
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          placeholder="toi@exemple.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
          disabled={loading}
        />
      </div>
      <Button type="submit" disabled={loading || !email} className="w-full">
        {loading ? 'Envoi...' : 'Recevoir le lien de connexion'}
      </Button>
    </form>
  )
}
```

- [ ] **Step 6.2: Create the login page**

Create `app/(auth)/login/page.tsx`:

```tsx
import { MagicLinkForm } from '@/components/auth/magic-link-form'
import { Toaster } from '@/components/ui/sonner'

export default function LoginPage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="text-center space-y-2">
          <h1 className="text-2xl font-semibold">Garmin Training Coach</h1>
          <p className="text-sm text-muted-foreground">
            Connecte-toi pour accéder à ton plan
          </p>
        </header>
        <MagicLinkForm />
      </div>
      <Toaster />
    </main>
  )
}
```

- [ ] **Step 6.3: Create the auth callback route**

Create `app/(auth)/auth/callback/route.ts`:

```ts
import { NextResponse } from 'next/server'
import { createClient } from '@/lib/supabase/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = searchParams.get('next') ?? '/today'

  if (code) {
    const supabase = await createClient()
    const { error } = await supabase.auth.exchangeCodeForSession(code)
    if (!error) {
      return NextResponse.redirect(`${origin}${next}`)
    }
  }

  return NextResponse.redirect(`${origin}/login?error=auth_failed`)
}
```

- [ ] **Step 6.4: Configure Supabase email template**

Manual action in Supabase dashboard:

1. Go to "Authentication → Email Templates"
2. Select "Magic Link"
3. Verify the link uses `{{ .ConfirmationURL }}` — should already be set by default
4. (Optional) Customize subject/body in French

In "Authentication → URL Configuration":
- Site URL: `http://localhost:3000` (for dev)
- Redirect URLs (add): `http://localhost:3000/auth/callback`

- [ ] **Step 6.5: Manual smoke test**

```bash
pnpm dev
```

1. Open http://localhost:3000 → should redirect to `/login`
2. Enter your real email, click "Recevoir le lien"
3. Toast confirms email sent
4. Check inbox → click link → redirected to `/today` (404 expected — page doesn't exist yet, that's fine)

Kill server.

- [ ] **Step 6.6: Commit**

```bash
git add -A
git commit -m "feat(auth): magic link login page and callback route"
```

---

## Task 7: Protected layout and minimal pages

**Files:**
- Create: `app/(app)/layout.tsx`, `app/(app)/today/page.tsx`, `app/(app)/profile/page.tsx`, `app/page.tsx`

- [ ] **Step 7.1: Replace the default root `app/page.tsx`**

Overwrite `app/page.tsx`:

```tsx
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'

export default async function Home() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  redirect(user ? '/today' : '/login')
}
```

- [ ] **Step 7.2: Create the protected app layout**

Create `app/(app)/layout.tsx`:

```tsx
import { redirect } from 'next/navigation'
import { createClient } from '@/lib/supabase/server'
import { BottomNav } from '@/components/nav/bottom-nav'
import { SideNav } from '@/components/nav/side-nav'

export default async function AppLayout({
  children,
}: {
  children: React.ReactNode
}) {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  return (
    <div className="min-h-screen flex">
      <SideNav />
      <main className="flex-1 pb-20 md:pb-0 md:pl-64">
        <div className="container mx-auto max-w-3xl px-4 py-6">
          {children}
        </div>
      </main>
      <BottomNav />
    </div>
  )
}
```

- [ ] **Step 7.3: Create the bottom nav (mobile)**

Create `components/nav/bottom-nav.tsx`:

```tsx
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

const items = [
  { href: '/today', label: 'Aujourd’hui' },
  { href: '/plan', label: 'Plan' },
  { href: '/stats', label: 'Stats' },
  { href: '/profile', label: 'Profil' },
]

export function BottomNav() {
  const pathname = usePathname()
  return (
    <nav className="md:hidden fixed bottom-0 inset-x-0 border-t bg-background z-10">
      <ul className="grid grid-cols-4">
        {items.map((item) => {
          const active = pathname === item.href
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  'flex items-center justify-center h-16 text-xs',
                  active ? 'text-foreground font-medium' : 'text-muted-foreground'
                )}
              >
                {item.label}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
```

- [ ] **Step 7.4: Create the side nav (desktop)**

Create `components/nav/side-nav.tsx`:

```tsx
'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

const items = [
  { href: '/today', label: 'Aujourd’hui' },
  { href: '/plan', label: 'Plan' },
  { href: '/stats', label: 'Stats' },
  { href: '/profile', label: 'Profil' },
]

export function SideNav() {
  const pathname = usePathname()
  return (
    <aside className="hidden md:flex fixed inset-y-0 left-0 w-64 border-r flex-col">
      <div className="px-6 py-6">
        <h1 className="text-lg font-semibold">Garmin Coach</h1>
      </div>
      <nav className="flex-1 px-3">
        <ul className="space-y-1">
          {items.map((item) => {
            const active = pathname === item.href
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    'block px-3 py-2 rounded-md text-sm',
                    active
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent/50'
                  )}
                >
                  {item.label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}
```

- [ ] **Step 7.5: Create the today page (placeholder)**

Create `app/(app)/today/page.tsx`:

```tsx
import { createClient } from '@/lib/supabase/server'

export default async function TodayPage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Aujourd&rsquo;hui</h1>
        <p className="text-sm text-muted-foreground">
          Connecté en tant que {user?.email}
        </p>
      </header>
      <section className="border rounded-lg p-6">
        <p className="text-muted-foreground">
          Ta séance du jour s&rsquo;affichera ici une fois ton profil complété
          et tes données Garmin synchronisées.
        </p>
      </section>
    </div>
  )
}
```

- [ ] **Step 7.6: Create the profile page (read-only)**

Create `app/(app)/profile/page.tsx`:

```tsx
import { createClient } from '@/lib/supabase/server'

export default async function ProfilePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('*')
    .eq('user_id', user!.id)
    .single()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Profil</h1>
        <p className="text-sm text-muted-foreground">{user?.email}</p>
      </header>
      <section className="border rounded-lg p-6 space-y-2 text-sm">
        <div>
          <strong>Prénom :</strong>{' '}
          {profile?.first_name ?? <em className="text-muted-foreground">non renseigné</em>}
        </div>
        <div>
          <strong>Ville :</strong>{' '}
          {profile?.city ?? <em className="text-muted-foreground">non renseigné</em>}
        </div>
        <div>
          <strong>Onboarding complété :</strong>{' '}
          {profile?.onboarding_completed_at ? 'oui' : 'non — sera fait en E3'}
        </div>
      </section>
    </div>
  )
}
```

- [ ] **Step 7.7: Add a sign-out button to the profile page**

Append before the closing `</div>` in `app/(app)/profile/page.tsx`:

Replace the file with:

```tsx
import { createClient } from '@/lib/supabase/server'
import { SignOutButton } from '@/components/auth/sign-out-button'

export default async function ProfilePage() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('*')
    .eq('user_id', user!.id)
    .single()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Profil</h1>
        <p className="text-sm text-muted-foreground">{user?.email}</p>
      </header>
      <section className="border rounded-lg p-6 space-y-2 text-sm">
        <div>
          <strong>Prénom :</strong>{' '}
          {profile?.first_name ?? <em className="text-muted-foreground">non renseigné</em>}
        </div>
        <div>
          <strong>Ville :</strong>{' '}
          {profile?.city ?? <em className="text-muted-foreground">non renseigné</em>}
        </div>
        <div>
          <strong>Onboarding complété :</strong>{' '}
          {profile?.onboarding_completed_at ? 'oui' : 'non — sera fait en E3'}
        </div>
      </section>
      <SignOutButton />
    </div>
  )
}
```

Create `components/auth/sign-out-button.tsx`:

```tsx
'use client'

import { createClient } from '@/lib/supabase/client'
import { Button } from '@/components/ui/button'
import { useRouter } from 'next/navigation'

export function SignOutButton() {
  const router = useRouter()

  async function handleSignOut() {
    const supabase = createClient()
    await supabase.auth.signOut()
    router.push('/login')
    router.refresh()
  }

  return (
    <Button variant="outline" onClick={handleSignOut}>
      Se déconnecter
    </Button>
  )
}
```

- [ ] **Step 7.8: Manual smoke test**

```bash
pnpm dev
```

1. Open http://localhost:3000 (not signed in) → redirected to `/login`
2. Sign in via magic link
3. Land on `/today` showing your email
4. Navigate to `/profile` via nav → see profile (mostly empty fields, that's expected)
5. Click "Se déconnecter" → back to `/login`

Kill server.

- [ ] **Step 7.9: Commit**

```bash
git add -A
git commit -m "feat(app): protected layout, today page, profile page, sign-out"
```

---

## Task 8: PWA configuration

**Files:**
- Create: `public/manifest.webmanifest`, `public/icons/icon-192.png`, `public/icons/icon-512.png`, `public/icons/icon-maskable-512.png`
- Modify: `next.config.mjs`, `app/layout.tsx`

- [ ] **Step 8.1: Install next-pwa**

```bash
pnpm add -D @ducanh2912/next-pwa
```

- [ ] **Step 8.2: Wrap next config with PWA**

Replace `next.config.mjs`:

```js
import withPWAInit from '@ducanh2912/next-pwa'

const withPWA = withPWAInit({
  dest: 'public',
  disable: process.env.NODE_ENV === 'development',
  register: true,
  workboxOptions: {
    skipWaiting: true,
  },
})

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
}

export default withPWA(nextConfig)
```

- [ ] **Step 8.3: Create the manifest**

Create `public/manifest.webmanifest` (served as a static asset — simpler and more reliable than the dynamic `app/manifest.ts` route handler approach for our use case):

```json
{
  "name": "Garmin Training Coach",
  "short_name": "Garmin Coach",
  "description": "Plan triathlon personnalisé basé sur tes données Garmin",
  "start_url": "/today",
  "display": "standalone",
  "background_color": "#0a0a0a",
  "theme_color": "#0a0a0a",
  "orientation": "portrait",
  "lang": "fr",
  "icons": [
    {
      "src": "/icons/icon-192.png",
      "sizes": "192x192",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "any"
    },
    {
      "src": "/icons/icon-maskable-512.png",
      "sizes": "512x512",
      "type": "image/png",
      "purpose": "maskable"
    }
  ]
}
```

- [ ] **Step 8.4: Generate placeholder icons**

For the MVP, use simple placeholder PNGs. Run from project root:

```bash
mkdir -p public/icons
```

Then create three solid-color icons via ImageMagick (install if missing: `sudo apt-get install imagemagick`):

```bash
convert -size 192x192 xc:'#0a0a0a' -fill white -gravity center -pointsize 80 -annotate 0 'GC' public/icons/icon-192.png
convert -size 512x512 xc:'#0a0a0a' -fill white -gravity center -pointsize 200 -annotate 0 'GC' public/icons/icon-512.png
convert -size 512x512 xc:'#0a0a0a' -fill white -gravity center -pointsize 160 -annotate 0 'GC' public/icons/icon-maskable-512.png
```

Expected: three PNG files in `public/icons/`.

If ImageMagick is unavailable, ask a designer for proper icons later; for the MVP a solid placeholder is acceptable.

- [ ] **Step 8.5: Add manifest link + theme color in root layout**

Update `app/layout.tsx`:

```tsx
import type { Metadata, Viewport } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Garmin Training Coach',
  description: 'Plan triathlon personnalisé basé sur tes données Garmin',
  manifest: '/manifest.webmanifest',
  appleWebApp: {
    capable: true,
    title: 'Garmin Coach',
    statusBarStyle: 'black-translucent',
  },
  icons: {
    icon: '/icons/icon-192.png',
    apple: '/icons/icon-192.png',
  },
}

export const viewport: Viewport = {
  themeColor: '#0a0a0a',
  width: 'device-width',
  initialScale: 1,
  maximumScale: 1,
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="fr" className="dark">
      <body className="min-h-screen bg-background text-foreground antialiased">
        {children}
      </body>
    </html>
  )
}
```

- [ ] **Step 8.6: Build and verify PWA**

```bash
pnpm build
pnpm start
```

In another terminal, run Lighthouse:

```bash
pnpm dlx lighthouse http://localhost:3000/login --only-categories=pwa --quiet --chrome-flags="--headless"
```

Expected: PWA score ≥ 90. The output should mention "Installable" criterion passed.

Kill `pnpm start`.

- [ ] **Step 8.7: Commit**

```bash
git add -A
git commit -m "feat(pwa): manifest, icons, service worker via next-pwa"
```

---

## Task 9: Playwright E2E test for auth flow

**Files:**
- Create: `tests/e2e/auth.spec.ts`

This test covers the unauthenticated → login redirect, not the full magic link (which requires reading email). The full flow is covered by the manual smoke test in Task 6.

- [ ] **Step 9.1: Write the failing E2E test**

Create `tests/e2e/auth.spec.ts`:

```ts
import { test, expect } from '@playwright/test'

test('unauthenticated user is redirected to /login from root', async ({ page }) => {
  await page.goto('/')
  await page.waitForURL('**/login')
  await expect(page.getByRole('heading', { name: 'Garmin Training Coach' })).toBeVisible()
})

test('login page shows the magic link form', async ({ page }) => {
  await page.goto('/login')
  await expect(page.getByLabel('Email')).toBeVisible()
  await expect(page.getByRole('button', { name: /Recevoir le lien/ })).toBeVisible()
})

test('protected route /today redirects unauthenticated to /login', async ({ page }) => {
  await page.goto('/today')
  await page.waitForURL('**/login')
})
```

- [ ] **Step 9.2: Run E2E tests**

```bash
pnpm test:e2e
```

Expected: 3 tests pass.

- [ ] **Step 9.3: Commit**

```bash
git add tests/e2e/
git commit -m "test: E2E auth redirects via Playwright"
```

---

## Task 10: Vercel deployment

**Files:** — (no files, this is configuration)

- [ ] **Step 10.1: Push to GitHub**

Manual action by the engineer:

1. Create a new private repo on GitHub: `garmin-training`
2. Add remote:

```bash
git remote add origin git@github.com:<your-username>/garmin-training.git
git push -u origin master
```

- [ ] **Step 10.2: Create Vercel project**

Manual action:

1. Go to https://vercel.com/new
2. Import the `garmin-training` repo
3. Framework preset: Next.js (auto-detected)
4. Root directory: `./`
5. Environment variables — add:
   - `NEXT_PUBLIC_SUPABASE_URL` = (same as `.env.local`)
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = (same as `.env.local`)
6. Click "Deploy"

Wait ~2 minutes.

- [ ] **Step 10.3: Update Supabase Site URL for production**

In Supabase dashboard → "Authentication → URL Configuration":

- Add to "Redirect URLs": `https://<your-vercel-domain>.vercel.app/auth/callback`
- Keep Site URL as localhost for dev convenience, but ensure both prod and dev redirect URLs are listed.

- [ ] **Step 10.4: Smoke test production**

1. Open `https://<your-vercel-domain>.vercel.app`
2. Verify redirect to `/login`
3. Sign in via magic link
4. Land on `/today`
5. On mobile (real iPhone/Android): open in browser → "Add to Home Screen" → app installs with icon

- [ ] **Step 10.5: Commit deployment notes**

Create `README.md` at project root:

```markdown
# Garmin Training Coach

Plan d'entraînement triathlon personnalisé basé sur les données Garmin Connect.

## Stack

- Next.js 15 (App Router, TypeScript)
- Tailwind CSS + shadcn/ui
- Supabase (Postgres + Auth + RLS)
- Vercel (hosting)
- Worker Python sur Fly.io (sync Garmin) — voir EPIC E2

## Démarrage local

```bash
pnpm install
cp .env.local.example .env.local
# Renseigner NEXT_PUBLIC_SUPABASE_URL et NEXT_PUBLIC_SUPABASE_ANON_KEY
pnpm dev
```

App disponible sur http://localhost:3000.

## Migrations DB

Les migrations sont dans `supabase/migrations/`. Pour la dev MVP, elles sont appliquées manuellement via le SQL Editor du dashboard Supabase. Pour automatiser plus tard : installer Supabase CLI et `supabase db push`.

## Tests

```bash
pnpm test       # unit (Vitest)
pnpm test:e2e   # E2E (Playwright)
pnpm typecheck  # tsc
```

## Plans d'implémentation

Voir `docs/superpowers/plans/` et `docs/superpowers/specs/`.
```

```bash
git add README.md
git commit -m "docs: README with setup instructions"
git push
```

---

## Definition of Done (E1)

Before declaring E1 complete, verify each item:

- [ ] `pnpm typecheck` passes without errors
- [ ] `pnpm test` passes (env validation tests)
- [ ] `pnpm test:e2e` passes (3 auth redirect tests)
- [ ] Manual smoke test on local: signup via magic link → land on `/today`
- [ ] Manual smoke test on Vercel prod: same flow works
- [ ] Lighthouse PWA score ≥ 90 on `/login`
- [ ] App installs as PWA on iPhone Safari (Add to Home Screen)
- [ ] App installs as PWA on Android Chrome (Install prompt)
- [ ] Supabase `athlete_profiles` row is auto-created on signup (verify in Supabase dashboard Table Editor)
- [ ] RLS verified: signed-in user can only `select` their own `athlete_profiles` row (test via SQL: `select * from athlete_profiles;` as authenticated user should return 1 row, not all rows)
- [ ] `.env.local` is git-ignored
- [ ] All commits pushed to GitHub
- [ ] No `console.log` debug statements left in code

---

## Notes for the engineer

- **Why magic link only?** Removes password storage and reset flows. Friction is acceptable for a beta of 10 users.
- **Why `@supabase/ssr` and not the legacy auth helpers?** Auth helpers are deprecated as of mid-2024. `@supabase/ssr` is the current recommended package for Next.js App Router.
- **Why `@ducanh2912/next-pwa` and not `next-pwa`?** The original `next-pwa` package is unmaintained. The `@ducanh2912/next-pwa` fork is actively maintained and supports Next.js 15.
- **The `garmin_credentials` table is empty in E1.** It will be populated in E2 (sync worker) when the user connects their Garmin account.
- **The `athlete_profiles` row is created empty.** Fields are filled in E3 (onboarding wizard).
- **Sign-out on mobile PWA** can be flaky if the service worker caches aggressively. If you hit this, add `Cache-Control: no-store` to auth routes or invalidate the cache on logout. Defer if not observed.
