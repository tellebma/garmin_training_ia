# Garmin Training Coach

Plan d'entraînement triathlon personnalisé basé sur les données Garmin Connect.

> Statut : MVP en cours de développement (E1 Foundations livré).

## Stack

- **Frontend** : Next.js 15 (App Router, TypeScript), Tailwind CSS 4, shadcn/ui
- **Auth** : Supabase Auth (magic link)
- **DB** : Supabase Postgres + RLS
- **Worker** : Python sur Fly.io (sync Garmin) — voir EPIC E2
- **Hosting** : Vercel (front), Supabase (BDD), Fly.io (worker)
- **CI/CD** : GitHub Actions + SonarQube self-hosted

## Démarrage local

Prérequis : Node 22+, pnpm 11+, un projet Supabase.

```bash
pnpm install
cp .env.local.example .env.local
# Renseigner NEXT_PUBLIC_SUPABASE_URL et NEXT_PUBLIC_SUPABASE_ANON_KEY
pnpm dev
```

App disponible sur http://localhost:3000.

### Migrations DB

Les migrations sont dans `supabase/migrations/`. Application manuelle pour le MVP :

1. Ouvrir https://supabase.com/dashboard → projet Garmin → SQL Editor
2. Coller le contenu de `supabase/migrations/20260517000000_initial_schema.sql`
3. Run

Pour automatiser : installer Supabase CLI et `supabase db push`.

### Tests

```bash
pnpm test          # unit (Vitest)
pnpm test:coverage # avec coverage
pnpm test:e2e      # E2E (Playwright)
pnpm typecheck     # tsc
pnpm lint          # ESLint
pnpm build         # Build prod
```

## Documentation

- `docs/superpowers/specs/` — specs validées (architecture, EPICs)
- `docs/superpowers/plans/` — plans d'implémentation par EPIC
- `QUALITY_GATES.md` — politique qualité (gates, seuils, outils)

## Quality Gates

Voir `QUALITY_GATES.md` pour la politique complète.

**TL;DR développeur** :

```bash
pnpm lint          # ESLint
pnpm typecheck     # TypeScript
pnpm test          # Vitest
pnpm test:coverage # avec coverage
pnpm test:e2e      # Playwright (installé en E1.T2)
pnpm format        # Prettier auto-fix
pnpm build         # Build prod
```

Tous ces gates tournent automatiquement :
- Sur `git commit` (Prettier + ESLint + tsc + gitleaks + commitlint)
- Sur `git push` (typecheck + tests + build)
- Sur PR GitHub (tous les jobs CI + Lighthouse + SonarQube self-hosted)

Pour contourner un gate (cas rare et justifié), ajouter un commentaire avec justification au-dessus du code et utiliser `// eslint-disable-next-line <rule> -- <raison>`.

### SonarQube self-hosted

Le projet utilise une instance SonarQube auto-hébergée à https://sonarqube.tellebma.fr/. La Quality Gate est configurée pour exiger :

- **Coverage on New Code ≥ 95%**
- Duplicated Lines on New Code ≤ 3%
- Maintainability / Reliability / Security Ratings on New Code: A

Les secrets GitHub Actions requis pour le job SonarQube :
- `SONAR_TOKEN` — User Token généré dans SonarQube → User → Security
- `SONAR_HOST_URL` — `https://sonarqube.tellebma.fr/`
