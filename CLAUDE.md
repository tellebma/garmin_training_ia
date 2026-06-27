# Garmin Training Coach — Claude project guide

Web app (Next.js PWA + Supabase + Python worker) qui synchronise Garmin Connect
et générera un plan triathlon périodisé. MVP pour le owner + 5-10 amis triathlètes
avant course **août-septembre 2026**.

## Statut actuel (2026-05-18)

| EPIC | État |
|---|---|
| **E1 — Foundations & Auth** | ✅ Livré (magic link, RLS, PWA, Vercel) |
| **E2 — Garmin Sync Worker** | ✅ Livré (sync activities/sleep/HRV/body, profile pull) |
| **E3 — Profile & Onboarding** | ✅ Livré (4-step wizard + profile edit forms) |
| **E-Auth refactor** | ✅ Livré (magic-link → email/password + allowlist) |
| **Race profile v2** | ✅ Livré (multi-leg + dénivelé par segment) |
| **E4 — Engine planning (algo Banister)** | ✅ Livré (TSS, CTL/ATL/TSB, phases, endpoint, cron) |
| **E5 — Génération séances (LLM)** | ✅ Livré (OpenAI GPT-4o-mini, JSONB workout, FR markdown) |
| E6 — Briefing quotidien + ajustement | À planifier |
| **E7 — Dashboard frontend** | ✅ Livré (5 pages + Banister chart + history/stats) |
| E8 — Parcours géolocalisés | À planifier |
| E9 — Beta privée (invits + monitoring) | À planifier |
| **E-Q — SonarQube Quality Gate** | ✅ Livré (97% coverage, gate enforced) |
| **E17 — Déploiement auto migrations Supabase** | ✅ Livré (CI db push auto-apply sur main) |

## Stack

```
Frontend (Vercel)               Worker (UNRAID self-hosted)
  Next.js 15 (App Router)         Python 3.12
  TypeScript strict++             FastAPI + uvicorn
  Tailwind 4 + shadcn/ui dark     python-garminconnect 0.3.x
  PWA (next-pwa, manifest, icons)  cryptography (Fernet)
  Supabase JS                     supabase-py (service role)
                                  systemd timer (cron daily 05:00 UTC)

Data (Supabase Postgres + RLS)
  auth.users (Supabase managé)
  athlete_profiles, garmin_credentials
  activities, daily_metrics, sleep, hrv, body_composition

CI/CD                           Auth
  GitHub Actions                  Supabase magic link (FR branded)
  SonarQube self-hosted           JWKS ES256 (ECC P-256)
  Docker Hub (tellebma/garmin-sync) Worker shared token (cron)
  Vercel auto-deploy
```

## URLs / Resources

- **Repo** : https://github.com/tellebma/garmin_training_ia
- **App prod** : https://garmin-training-ia.vercel.app
- **Worker prod** : https://garmin-sync.tellebma.fr (`/health` retourne `{"status":"ok","env":"prod"}`)
- **Supabase** : project `peiyrqplymdlmlpsbqzu` (`garmin-training-dev`, eu-west-3)
  - Dashboard : https://supabase.com/dashboard/project/peiyrqplymdlmlpsbqzu
- **SonarQube** : https://sonarqube.tellebma.fr/dashboard?id=garmin_training_ia
- **Docker Hub** : https://hub.docker.com/r/tellebma/garmin-sync

## Architecture

```
[Vercel Next.js]  ─── Server Action ───▶  [Worker FastAPI]  ─── auth ───▶  [Garmin Connect API]
       │                                       │
       │ supabase-js (anon)                    │ supabase-py (service role)
       ▼                                       ▼
                       [Supabase Postgres + RLS]
                              (athlete_profiles,
                               garmin_credentials,
                               activities, daily_metrics,
                               sleep, hrv, body_composition)
```

Le worker tourne en container sur le serveur UNRAID de l'owner, derrière Nginx Proxy
Manager (Let's Encrypt SSL). systemd timer (User Scripts UNRAID) déclenche
`docker exec garmin-sync python -m garmin_sync.cron` chaque jour à 05:00 UTC.

## Comment travailler avec ce projet

### Setup local (frontend)

```bash
pnpm install
cp .env.local.example .env.local  # ajouter Supabase keys + WORKER_URL=http://localhost:8080
pnpm dev  # http://localhost:3000
```

### Setup local (worker)

```bash
cd worker
uv sync --all-groups
cp .env.example .env  # ajouter Supabase + FERNET_KEY + WORKER_SHARED_TOKEN
uv run uvicorn garmin_sync.main:app --reload --port 8080
```

### Tests

| Commande | Quoi |
|---|---|
| `pnpm test` | Vitest unit (frontend) |
| `pnpm test:e2e` | Playwright |
| `pnpm lint && pnpm typecheck && pnpm build` | Quality gates frontend |
| `cd worker && uv run pytest -v` | 46 tests Python |
| `cd worker && uv run ruff check . && uv run mypy src/` | Lint + types worker |

### Quality gates

Voir [`QUALITY_GATES.md`](./QUALITY_GATES.md). Les gates s'enchaînent à chaque commit
(pre-commit hook : Prettier + ESLint + tsc-files + gitleaks + commitlint) et chaque
push (pre-push : typecheck + tests + build). CI sur PR : lint + typecheck + test +
build + audit + secrets + Lighthouse + SonarQube.

### Convention de commit

Conventional Commits stricts (`feat:`, `fix:`, `docs:`, `ci:`, `build:`, `chore:`,
`style:`, `refactor:`, `perf:`, `test:`, `revert:`). Body lines ≤ 100 chars.

### Branches

- `main` — protégé, déploie auto sur Vercel
- `feat/<epic>-<short-name>` pour les EPICs (ex: `feat/e3-onboarding`)
- `fix/<short-name>` pour les hot fixes
- Toujours via PR, jamais de push direct sur main

### Suivi des tâches (GitHub Projects) — OBLIGATOIRE

Le board GitHub Projects est le **tableau de bord vivant** du projet :
**« Garmin Training Coach — Backlog » (#4)** → https://github.com/users/tellebma/projects/4
(aussi listé sous https://github.com/tellebma/garmin_training_ia/projects, le board y est lié).
`docs/superpowers/BACKLOG.md` reste la source de vérité détaillée (specs, critères, statut
« V1 livrée ») ; le Project en est la vue synthétique et navigable.

**Champs du board** :

- `Status` (workflow) : **Backlog** (idée / post-MVP non priorisé) → **Todo** (priorisé,
  prêt à prendre) → **In Progress** → **In Review** (PR ouverte) → **Done**, plus
  **Won't do** (abandonné, ex E17.2).
- `Priorité` : **P0** / **P1** / **P2**.
- `EPIC` : E9, E13, E14, E15, E16, E17, Coaching, Plateforme, Post-MVP (pour grouper/filtrer).

Convention : un item « V1 livrée » reste en *Done* ; le reste-à-faire explicite (« Suite … »
dans `BACKLOG.md`) devient un item *Todo* distinct.

**Règle** : pour **chaque tâche** travaillée, tenir le Project à jour en temps réel :

- À la **prise** d'une tâche : déplacer l'item correspondant en *In Progress* (le créer s'il
  manque, en reprenant titre + EPIC + Priorité depuis `BACKLOG.md`).
- À l'**ouverture de PR** : lier la PR à l'item et passer en *In Review*.
- Au **merge** : passer l'item en *Done*, créer un item *Todo* pour toute « Suite », et mettre
  à jour `BACKLOG.md` (« V1 livrée » + n° de PR), pour garder les deux cohérents.
- Toute **nouvelle demande** ajoutée à `BACKLOG.md` doit aussi créer un item dans le Project
  (avec Status / Priorité / EPIC).

Objectif : un suivi lisible et fiable d'un coup d'œil sur GitHub. Garder Project et
`BACKLOG.md` synchronisés ; ne jamais faire avancer une tâche sans refléter son état sur le
board.

> Note outillage : la mise à jour du Project (v2) nécessite un token GitHub avec le scope
> `project` (ou `read:project` en lecture). Si le token courant ne l'a pas
> (`gh auth refresh -s project`), basculer sur des **Issues** liées au Project en attendant.

## File map

```
.
├── app/                          # Next.js App Router routes
│   ├── (auth)/login/             # Magic link form
│   ├── (auth)/auth/callback/     # Supabase OAuth callback
│   ├── (app)/                    # Routes protégées (auth check in layout)
│   │   ├── today/                # Vue séance du jour (placeholder)
│   │   ├── profile/              # Profil user
│   │   └── profile/garmin/       # Connect/MFA Garmin
│   └── actions/garmin-auth.ts    # Server Actions → worker
├── components/
│   ├── ui/                       # shadcn-generated
│   ├── auth/                     # MagicLinkForm, SignOutButton
│   ├── garmin/                   # ConnectForm, MfaForm
│   └── nav/                      # BottomNav, SideNav
├── lib/
│   ├── env.ts                    # Public + server env (zod-validated)
│   ├── worker.ts                 # HTTP client → worker (Server Action only)
│   ├── utils.ts                  # cn() helper
│   └── supabase/                 # browser/server/middleware clients
├── worker/                       # Python worker (autonome)
│   ├── src/garmin_sync/
│   │   ├── main.py               # FastAPI entry (4 endpoints)
│   │   ├── config.py             # Pydantic settings
│   │   ├── auth.py               # JWT JWKS ES256 + shared token
│   │   ├── crypto.py             # TokenCipher (Fernet)
│   │   ├── supabase_client.py    # Cached service-role client
│   │   ├── garmin_client.py      # python-garminconnect wrapper
│   │   ├── connect.py            # Garmin connect/MFA flow
│   │   ├── sync.py               # Per-user sync orchestrator
│   │   ├── cron.py               # Daily cron entry point
│   │   └── transformers/         # 5 pure functions Garmin→DB row
│   ├── tests/                    # 46 pytest tests
│   ├── Dockerfile                # Multi-stage build, non-root user
│   ├── docker-compose.yml        # Local dev
│   ├── docker-compose.prod.yml   # UNRAID overlay
│   └── deploy/                   # Systemd units + deploy README
├── supabase/
│   ├── config.toml               # project_id (CLI link/push — projet distant only)
│   ├── migrations/               # 28 SQL files numérotés timestamp (auto-apply via CI sur main)
│   └── email-templates/          # Magic link FR + README
├── docs/superpowers/
│   ├── specs/                    # Validated specs par EPIC
│   └── plans/                    # Implementation plans par EPIC
├── local-setup/                  # GITIGNORED — bootstrap secrets UNRAID
├── .github/workflows/
│   ├── ci.yml                    # 8 jobs (lint, typecheck, test, build, audit, secrets, sonar)
│   ├── lighthouse.yml            # Lighthouse CI
│   ├── supabase-migrations.yml   # E17 — db push auto sur main (migrations Supabase)
│   ├── worker-ci.yml             # Python worker CI
│   └── worker-docker.yml         # Build + push Docker Hub
├── QUALITY_GATES.md              # Politique qualité 5 niveaux
├── CLAUDE.md                     # Ce fichier
└── README.md                     # Quick start
```

## Décisions importantes (with why)

1. **Self-hosted worker (UNRAID) au lieu de Fly.io** : Fly.io free tier a été
   supprimé fin 2024 ($5/mois min CC). L'owner a déjà un serveur (sonarqube.tellebma.fr).
   Coût marginal du worker : 0€.

2. **JWT verification via JWKS ES256 (pas HS256)** : Supabase a migré ce projet vers
   ECC P-256 signing. Le shared HS256 secret n'est plus exposé par la UI Supabase.
   `auth.py` utilise `PyJWKClient` pour fetch `{SUPABASE_URL}/auth/v1/.well-known/jwks.json`.

3. **error_id pattern pour les erreurs worker** : `{status, error_id, type}` au lieu
   de `{status, detail, traceback}` — évite de leak des détails internes au navigateur.
   Stack trace complète reste dans `docker logs garmin-sync` (greppable par error_id).

4. **Email templates versionnés dans le repo** (`supabase/email-templates/`) pour les
   faire évoluer dans un PR review. Mise à jour manuelle dans le dashboard Supabase
   pour l'instant. Auto-sync via Management API → post-MVP.

5. **Multi-tenant dès J0** : toutes les tables ont `user_id` + RLS policies. L'app
   marche pour 1 user (owner) mais le schéma est prêt pour les amis beta + futur SaaS.

6. **`vercel.json` avec `framework: nextjs` explicite** : Vercel auto-detection
   échouait silencieusement, produisant des 404 sur toutes les routes. Le fichier
   force l'utilisation du Next.js adapter.

7. **Pas de middleware Next.js** : auth guard est directement dans les pages
   (`app/(app)/layout.tsx` redirige vers `/login` si pas user). Tentative Edge
   middleware crashait (`__dirname`, path alias non bundlés, modules unsupported).
   Approche pages-only est plus simple et plus robuste.

## Pièges à éviter (vécus, à ne pas refaire)

- **`pnpm-workspace.yaml` avec `allowBuilds:` sans `packages:`** : pnpm 9 refuse
  ("packages field missing"), pnpm 10/11 accepte. Le projet utilise pnpm 11 via
  `packageManager` field dans `package.json`. Les workflows GHA utilisent la même.

- **Path aliases `@/*` dans des fichiers liés au middleware Edge** : Vercel bundle
  les Edge functions séparément et ne résout pas le tsconfig path. Utilise des
  imports relatifs (`./lib/foo`) dans `middleware.ts` et fichiers liés.

- **Supabase Site URL = localhost** : les emails Magic Link redirigent vers localhost
  même en prod, parce que Site URL est utilisée comme fallback quand `emailRedirectTo`
  ne match aucune Redirect URL whitelisted. Garder le Site URL = URL prod, ajouter
  redirect URLs pour localhost + previews séparément.

- **Garmin rate-limits agressivement** : après 3-5 tentatives de login échouées, le
  service bloque l'IP pour 1-24h. Pas de workaround simple — attendre. `garminconnect`
  0.3.x swallow les 429 silencieusement → wrap explicitement.

- **Docker workflow Hub se déclenche sur main uniquement** : tant que les changements
  worker ne sont pas sur main, l'image reste old. Pendant le dev sur branche feature,
  faire `docker build ... && docker push tellebma/garmin-sync:latest` à la main.

- **`.next/types/` cache stale** entre branches : `pnpm build` sur une branche qui
  ne contient pas certaines pages échoue. `rm -rf .next` avant `pnpm build` quand
  on swap de branche.

## Hot fixes en cours

### Bug Garmin connect (en cours, 2026-05-18)

`AttributeError: 'Garmin' object has no attribute 'garth'` dans `garmin_client.py`.
`garminconnect 0.3.x` a changé son API. Voir PR fix/garminconnect-api (en cours).

Aussi : 429 Garmin sur l'IP UNRAID (l'owner doit attendre 1-24h avant de re-tester).

## Comment continuer

### Si tu reprends le projet à froid

1. Lis ce CLAUDE.md
2. Vérifie l'état des PRs : `gh pr list --repo tellebma/garmin_training_ia`
3. Vérifie l'état des tasks en cours dans la liste partagée
4. Lis le dernier spec/plan dans `docs/superpowers/specs/` et `docs/superpowers/plans/`
5. Si l'EPIC en cours est E2 et qu'il y a des fixes en cours, vérifie les hot fixes
6. Sinon, propose de démarrer le prochain EPIC (E3 Profile & Onboarding)

### Workflow recommandé pour un nouvel EPIC

1. **Brainstorm** : `superpowers:brainstorming` skill — clarifie scope, contraintes,
   décompose en sous-tâches
2. **Écris le spec** : `docs/superpowers/specs/YYYY-MM-DD-<feature>.md`
3. **Écris le plan** : `superpowers:writing-plans` skill — `docs/superpowers/plans/`
4. **Exécute** : `superpowers:subagent-driven-development` (dispatch un sous-agent
   par tâche, 2-stage review entre chaque)
5. **PR + merge** quand CI verte

### Hooks et MCP utiles déjà configurés (global CLAUDE.md)

- **Supabase MCP** : `mcp__supabase__list_tables`, `apply_migration`, `execute_sql`,
  `get_advisors`. Project ID : `peiyrqplymdlmlpsbqzu`. Team Vercel : `team_X92DOqyhOKEDlF3j6XDkAHPk`.
- **Vercel MCP** : list_deployments, get_runtime_logs, etc.
- **Playwright MCP** : tester les UI flows en E2E, modifier des configs via UI Supabase/Vercel
- **GitHub MCP** : interactions PRs/issues
- **Wiki-Brain** : `/wiki-brain query`, ingestion sources dans
  `/mnt/c/Documents and Settings/pdmtc/Documents/Maxime/DEV/claude-brain`

## TODO post-MVP (idées notées)

Le backlog canonique vit dans `docs/superpowers/BACKLOG.md`.
