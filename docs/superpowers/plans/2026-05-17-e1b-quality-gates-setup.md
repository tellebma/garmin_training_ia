# E1b — Quality Gates Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Install and configure all quality gates (Niveau 1 à 4 de `QUALITY_GATES.md`) sur le projet Next.js scaffolded en E1 Task 1, AVANT de continuer le reste de E1. Garantit que tout le code écrit ensuite passe par les gates.

**Architecture:** husky + lint-staged pour pre-commit, hooks de pre-push, ESLint 9 (flat config) avec plugins SonarJS/Unicorn/Tailwind/TypeScript, Prettier 3, commitlint, gitleaks, GitHub Actions CI avec jobs parallèles, Codecov pour coverage diff, Lighthouse CI pour les pages clés.

**Tech Stack:** husky 9, lint-staged 15, ESLint 9 (flat), eslint-plugin-sonarjs, eslint-plugin-unicorn, eslint-plugin-tailwindcss, @typescript-eslint, Prettier 3, commitlint + @commitlint/config-conventional, gitleaks (binary), Codecov GitHub Action, Lighthouse CI, Supabase CLI.

**Spec reference:** `QUALITY_GATES.md` (politique projet).

**Execution timing:** ce plan s'exécute **immédiatement APRÈS E1 Task 1** (scaffold Next.js terminé) et **AVANT E1 Task 2** (tooling Vitest/Playwright/zod). Aucune ligne de code applicatif ne doit être écrite sans que les gates soient actifs — c'est la première action après le scaffold.

---

## File Structure

```
garmin_training/
├── .husky/
│   ├── pre-commit
│   ├── pre-push
│   └── commit-msg
├── .github/
│   └── workflows/
│       ├── ci.yml
│       └── lighthouse.yml
├── .gitleaks.toml
├── .lintstagedrc.json
├── .prettierrc.json
├── .prettierignore
├── eslint.config.mjs
├── commitlint.config.mjs
├── codecov.yml
├── lighthouserc.json
├── tsconfig.json                       ← modifié (strict mode)
├── package.json                        ← modifié (scripts + devDeps)
└── vitest.config.ts                    ← modifié (coverage v8)
```

---

## Task 1: Install Prettier + format the codebase

**Files:**
- Create: `.prettierrc.json`, `.prettierignore`
- Modify: `package.json`

- [ ] **Step 1.1: Install Prettier**

```bash
pnpm add -D prettier prettier-plugin-tailwindcss
```

- [ ] **Step 1.2: Create `.prettierrc.json`**

```json
{
  "semi": false,
  "singleQuote": true,
  "trailingComma": "es5",
  "printWidth": 100,
  "tabWidth": 2,
  "plugins": ["prettier-plugin-tailwindcss"]
}
```

- [ ] **Step 1.3: Create `.prettierignore`**

```
.next/
node_modules/
public/
pnpm-lock.yaml
*.md
coverage/
test-results/
playwright-report/
.vercel/
supabase/migrations/
```

- [ ] **Step 1.4: Add scripts**

In `package.json`, add to `scripts`:

```json
"format": "prettier --write .",
"format:check": "prettier --check ."
```

- [ ] **Step 1.5: Format existing code**

```bash
pnpm format
```

Expected: all `.ts`, `.tsx`, `.json` files reformatted. No errors.

- [ ] **Step 1.6: Commit**

```bash
git add -A
git commit -m "build: setup Prettier 3 with Tailwind plugin"
```

---

## Task 2: Install ESLint 9 (flat config) with all plugins

**Files:**
- Create: `eslint.config.mjs`
- Modify: `package.json`

- [ ] **Step 2.1: Install ESLint and plugins**

```bash
pnpm add -D eslint@^9 @eslint/js typescript-eslint \
  eslint-plugin-sonarjs eslint-plugin-unicorn \
  eslint-plugin-tailwindcss eslint-plugin-react eslint-plugin-react-hooks \
  @next/eslint-plugin-next eslint-config-prettier
```

- [ ] **Step 2.2: Create `eslint.config.mjs`**

```js
import js from '@eslint/js'
import tseslint from 'typescript-eslint'
import sonarjs from 'eslint-plugin-sonarjs'
import unicorn from 'eslint-plugin-unicorn'
import tailwindcss from 'eslint-plugin-tailwindcss'
import react from 'eslint-plugin-react'
import reactHooks from 'eslint-plugin-react-hooks'
import next from '@next/eslint-plugin-next'
import prettier from 'eslint-config-prettier'

export default [
  js.configs.recommended,
  ...tseslint.configs.strictTypeChecked,
  ...tseslint.configs.stylisticTypeChecked,
  sonarjs.configs.recommended,
  {
    plugins: {
      unicorn,
      tailwindcss,
      react,
      'react-hooks': reactHooks,
      '@next/next': next,
    },
    languageOptions: {
      parserOptions: {
        projectService: true,
        tsconfigRootDir: import.meta.dirname,
      },
      globals: {
        React: 'readonly',
      },
    },
    settings: {
      react: { version: 'detect' },
      tailwindcss: { callees: ['cn', 'clsx', 'cva'] },
    },
    rules: {
      // Next.js
      ...next.configs.recommended.rules,
      ...next.configs['core-web-vitals'].rules,

      // React
      ...react.configs.recommended.rules,
      ...reactHooks.configs.recommended.rules,
      'react/react-in-jsx-scope': 'off',
      'react/prop-types': 'off',

      // Tailwind
      'tailwindcss/classnames-order': 'warn',
      'tailwindcss/no-custom-classname': 'off',

      // Unicorn — selected rules
      'unicorn/filename-case': ['error', { case: 'kebabCase' }],
      'unicorn/no-null': 'off',
      'unicorn/prevent-abbreviations': 'off',
      'unicorn/no-array-reduce': 'off',

      // SonarJS — already covers cognitive complexity, duplications
      'sonarjs/cognitive-complexity': ['error', 15],
      'sonarjs/no-duplicate-string': ['error', { threshold: 4 }],

      // TypeScript strictness
      '@typescript-eslint/no-explicit-any': 'error',
      '@typescript-eslint/no-unused-vars': ['error', { argsIgnorePattern: '^_' }],
      '@typescript-eslint/consistent-type-imports': 'error',
    },
  },
  {
    files: ['**/*.{js,mjs,cjs}'],
    ...tseslint.configs.disableTypeChecked,
  },
  {
    files: ['tests/**/*.{ts,tsx}'],
    rules: {
      'sonarjs/no-duplicate-string': 'off',
      '@typescript-eslint/no-unsafe-assignment': 'off',
    },
  },
  {
    ignores: ['.next/**', 'node_modules/**', 'coverage/**', 'public/**', 'supabase/migrations/**'],
  },
  prettier, // must be last — disables ESLint rules conflicting with Prettier
]
```

- [ ] **Step 2.3: Add scripts**

In `package.json`, add to `scripts`:

```json
"lint": "eslint .",
"lint:fix": "eslint . --fix"
```

- [ ] **Step 2.4: Run lint and fix what's autofixable**

```bash
pnpm lint:fix
```

Expected: most issues auto-fixed. Remaining manual fixes needed if any TypeScript strict errors.

- [ ] **Step 2.5: Verify lint passes**

```bash
pnpm lint
```

Expected: 0 errors. Warnings are OK at this stage.

If there are residual errors from the shadcn-generated files, fix them by either adjusting the rule (if the rule conflicts with the framework) or fixing the code. Document any rule adjustment in the commit message.

- [ ] **Step 2.6: Commit**

```bash
git add -A
git commit -m "build: setup ESLint 9 flat config with SonarJS, Unicorn, Tailwind plugins"
```

---

## Task 3: Strict TypeScript config

**Files:**
- Modify: `tsconfig.json`

- [ ] **Step 3.1: Update `tsconfig.json` to strict**

Open `tsconfig.json` and ensure `compilerOptions` contains :

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "noFallthroughCasesInSwitch": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true
  }
}
```

Keep the other options that Next.js scaffolded (e.g. `target`, `module`, `paths`, `incremental`).

- [ ] **Step 3.2: Run typecheck**

```bash
pnpm typecheck
```

If errors appear, fix them. Most likely issues:
- `verbatimModuleSyntax` requires `import type` for type-only imports → use `pnpm lint:fix` (ESLint rule `consistent-type-imports` auto-fixes).
- `exactOptionalPropertyTypes` may require explicit `| undefined` on some props.
- `noUncheckedIndexedAccess` requires null-checking array access — fix call sites.

Expected after fixes: 0 errors.

- [ ] **Step 3.3: Commit**

```bash
git add -A
git commit -m "build: enable strict TypeScript options"
```

---

## Task 4: Husky + lint-staged for pre-commit

**Files:**
- Create: `.husky/pre-commit`, `.husky/pre-push`, `.husky/commit-msg`, `.lintstagedrc.json`
- Modify: `package.json`

- [ ] **Step 4.1: Install husky and lint-staged**

```bash
pnpm add -D husky lint-staged tsc-files
```

- [ ] **Step 4.2: Initialize husky**

```bash
pnpm exec husky init
```

This creates `.husky/` directory with a sample `pre-commit` hook and adds `prepare: husky` script to `package.json`.

- [ ] **Step 4.3: Configure `.lintstagedrc.json`**

```json
{
  "*.{ts,tsx}": [
    "eslint --fix",
    "prettier --write",
    "tsc-files --noEmit"
  ],
  "*.{js,mjs,cjs,json,md}": [
    "prettier --write"
  ]
}
```

- [ ] **Step 4.4: Write the pre-commit hook**

Overwrite `.husky/pre-commit`:

```sh
pnpm exec lint-staged
```

- [ ] **Step 4.5: Make it executable**

```bash
chmod +x .husky/pre-commit
```

- [ ] **Step 4.6: Test the pre-commit hook**

Modify a file (e.g. add a trailing space to `app/page.tsx`), stage it, and commit:

```bash
echo " " >> app/page.tsx
git add app/page.tsx
git commit -m "test: pre-commit hook"
```

Expected: lint-staged runs, Prettier auto-fixes the trailing space, commit succeeds.

Verify the trailing space was removed:

```bash
tail -c 20 app/page.tsx | od -c | head -1
```

- [ ] **Step 4.7: Commit**

(The previous commit already worked, but ensure all `.husky/` files are tracked.)

```bash
git add .husky/ .lintstagedrc.json package.json pnpm-lock.yaml
git commit -m "build: setup husky pre-commit with lint-staged"
```

---

## Task 5: commitlint for Conventional Commits

**Files:**
- Create: `commitlint.config.mjs`, `.husky/commit-msg`
- Modify: `package.json`

- [ ] **Step 5.1: Install commitlint**

```bash
pnpm add -D @commitlint/cli @commitlint/config-conventional
```

- [ ] **Step 5.2: Create `commitlint.config.mjs`**

```js
export default {
  extends: ['@commitlint/config-conventional'],
  rules: {
    'subject-case': [0],
    'header-max-length': [2, 'always', 100],
    'type-enum': [
      2,
      'always',
      [
        'feat',
        'fix',
        'docs',
        'style',
        'refactor',
        'perf',
        'test',
        'build',
        'ci',
        'chore',
        'revert',
      ],
    ],
  },
}
```

- [ ] **Step 5.3: Create `.husky/commit-msg` hook**

Create `.husky/commit-msg`:

```sh
pnpm exec commitlint --edit "$1"
```

```bash
chmod +x .husky/commit-msg
```

- [ ] **Step 5.4: Test commit-msg hook**

Try an invalid commit message:

```bash
git commit --allow-empty -m "broken message"
```

Expected: commitlint rejects with "subject may not be empty" or "type may not be empty".

Then try a valid one:

```bash
git commit --allow-empty -m "chore: test commitlint"
```

Expected: succeeds.

- [ ] **Step 5.5: Commit**

```bash
git add commitlint.config.mjs .husky/commit-msg package.json pnpm-lock.yaml
git commit -m "build: enforce Conventional Commits via commitlint"
```

---

## Task 6: gitleaks for secret detection

**Files:**
- Create: `.gitleaks.toml`
- Modify: `.husky/pre-commit`

- [ ] **Step 6.1: Install gitleaks binary**

On Linux/WSL:

```bash
curl -sSfL https://github.com/gitleaks/gitleaks/releases/download/v8.21.2/gitleaks_8.21.2_linux_x64.tar.gz \
  | sudo tar -xz -C /usr/local/bin gitleaks
gitleaks version
```

Expected output: `8.21.2` or similar.

If sudo unavailable, install via Homebrew (`brew install gitleaks`) or download to `~/.local/bin`.

- [ ] **Step 6.2: Create `.gitleaks.toml`**

Use the default ruleset extended with a few custom allowlists for false positives:

```toml
[extend]
useDefault = true

[allowlist]
description = "Global allowlist"
paths = [
  '''node_modules''',
  '''pnpm-lock\.yaml''',
  '''\.env\.local\.example''',
  '''public/.+\.(png|jpg|svg|webp|ico)''',
]
regexes = [
  '''example\.(com|supabase\.co)''',
  '''your-(anon-key|project)''',
]
```

- [ ] **Step 6.3: Add gitleaks to pre-commit**

Update `.husky/pre-commit`:

```sh
pnpm exec lint-staged
gitleaks protect --staged --redact --verbose --config .gitleaks.toml
```

- [ ] **Step 6.4: Test gitleaks**

Create a fake secret file:

```bash
echo "AWS_SECRET_ACCESS_KEY=AKIAIOSFODNN7EXAMPLE_FAKE_FORTEST" > /tmp/fake-secret.txt
git add /tmp/fake-secret.txt 2>/dev/null || cp /tmp/fake-secret.txt fake-secret.txt && git add fake-secret.txt
git commit -m "test: should fail"
```

Expected: gitleaks blocks the commit with a "leak found" error.

Clean up:

```bash
git restore --staged fake-secret.txt
rm fake-secret.txt
```

- [ ] **Step 6.5: Commit**

```bash
git add .gitleaks.toml .husky/pre-commit
git commit -m "build: add gitleaks secret detection to pre-commit"
```

---

## Task 7: Pre-push hook (tests + build)

**Files:**
- Create: `.husky/pre-push`

- [ ] **Step 7.1: Create pre-push hook**

Create `.husky/pre-push`:

```sh
pnpm exec tsc --noEmit
pnpm test
pnpm build
```

```bash
chmod +x .husky/pre-push
```

- [ ] **Step 7.2: Test pre-push hook**

(This runs the full suite, takes ~30-60s. Push to verify.)

```bash
git push --dry-run origin master
```

Or actually push (the hook runs on real push too):

```bash
git push origin master
```

Expected: typecheck → test → build all pass, push succeeds. If any fail, push is blocked.

- [ ] **Step 7.3: Commit**

```bash
git add .husky/pre-push
git commit -m "build: pre-push hook runs typecheck, tests, build"
git push
```

---

## Task 8: Vitest coverage configuration

**Files:**
- Modify: `vitest.config.ts`, `package.json`

- [ ] **Step 8.1: Install coverage provider**

```bash
pnpm add -D @vitest/coverage-v8
```

- [ ] **Step 8.2: Update `vitest.config.ts`**

```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import path from 'node:path'

export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'node',
    include: ['tests/unit/**/*.test.ts', 'tests/unit/**/*.test.tsx'],
    globals: false,
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov', 'html', 'json-summary'],
      reportsDirectory: './coverage',
      include: ['app/**/*.{ts,tsx}', 'lib/**/*.{ts,tsx}', 'components/**/*.{ts,tsx}'],
      exclude: [
        '**/*.d.ts',
        '**/*.config.*',
        'app/**/layout.tsx',
        'app/**/loading.tsx',
        'app/**/error.tsx',
        'app/**/not-found.tsx',
        'components/ui/**',         // shadcn-generated, not our code
      ],
      thresholds: {
        lines: 80,
        functions: 80,
        branches: 75,
        statements: 80,
      },
    },
  },
  resolve: {
    alias: { '@': path.resolve(__dirname, '.') },
  },
})
```

- [ ] **Step 8.3: Add coverage script**

In `package.json`:

```json
"test:coverage": "vitest run --coverage"
```

- [ ] **Step 8.4: Verify coverage runs**

```bash
pnpm test:coverage
```

Expected: tests pass + coverage report printed + `coverage/` directory created.

The thresholds may fail at this stage if coverage is below 80% — that's OK for now (only the env validation test exists). Document this and proceed; coverage will rise as more tests are added.

- [ ] **Step 8.5: Update `.gitignore`**

Append:

```
coverage/
```

- [ ] **Step 8.6: Commit**

```bash
git add -A
git commit -m "build: enable Vitest coverage with v8 provider"
```

---

## Task 9: GitHub Actions CI workflow

**Files:**
- Create: `.github/workflows/ci.yml`

- [ ] **Step 9.1: Create the CI workflow**

Create `.github/workflows/ci.yml`:

```yaml
name: CI

on:
  pull_request:
    branches: [main, master]
  push:
    branches: [main, master]

concurrency:
  group: ${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  lint:
    name: Lint
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm lint
      - run: pnpm format:check

  typecheck:
    name: TypeCheck
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm typecheck

  test-unit:
    name: Unit tests + coverage
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm test:coverage
        env:
          NEXT_PUBLIC_SUPABASE_URL: https://example.supabase.co
          NEXT_PUBLIC_SUPABASE_ANON_KEY: anon-key-test
      - name: Upload coverage to Codecov
        uses: codecov/codecov-action@v4
        with:
          files: ./coverage/lcov.info
          fail_ci_if_error: true
        env:
          CODECOV_TOKEN: ${{ secrets.CODECOV_TOKEN }}

  test-e2e:
    name: E2E tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm exec playwright install --with-deps chromium
      - run: pnpm test:e2e
        env:
          NEXT_PUBLIC_SUPABASE_URL: ${{ secrets.SUPABASE_URL_TEST }}
          NEXT_PUBLIC_SUPABASE_ANON_KEY: ${{ secrets.SUPABASE_ANON_KEY_TEST }}

  build:
    name: Build
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm build
        env:
          NEXT_PUBLIC_SUPABASE_URL: https://example.supabase.co
          NEXT_PUBLIC_SUPABASE_ANON_KEY: anon-key-test

  audit:
    name: Dependencies audit
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm audit --prod --audit-level=high

  secrets:
    name: Secret scan
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - uses: gitleaks/gitleaks-action@v2
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

- [ ] **Step 9.2: Configure GitHub repo secrets**

Manual action (after creating the repo on GitHub in E1 Task 10):

In GitHub → repo Settings → Secrets and variables → Actions, add:
- `CODECOV_TOKEN` — get from https://app.codecov.io after linking the repo (Codecov free tier auto-detects)
- `SUPABASE_URL_TEST` — a test Supabase project URL (can be the dev one for MVP)
- `SUPABASE_ANON_KEY_TEST` — corresponding anon key

For the MVP, you can skip the Codecov token until after the first push (it works without token for public repos; for private repos the token is required).

- [ ] **Step 9.3: Commit**

```bash
git add .github/
git commit -m "ci: GitHub Actions workflow with lint, typecheck, test, build, audit, secrets"
```

---

## Task 10: Codecov configuration

**Files:**
- Create: `codecov.yml`

- [ ] **Step 10.1: Create `codecov.yml`**

```yaml
coverage:
  precision: 2
  round: down
  range: "70...100"
  status:
    project:
      default:
        target: 80%
        threshold: 1%
        if_ci_failed: error
    patch:
      default:
        target: 95%
        threshold: 0%
        if_ci_failed: error
        only_pulls: true

comment:
  layout: "header, diff, files, footer"
  behavior: default
  require_changes: true
  require_base: false
  require_head: true

ignore:
  - "components/ui/**"
  - "**/*.config.*"
  - "**/*.d.ts"
  - "supabase/migrations/**"
  - "tests/**"
```

- [ ] **Step 10.2: Link repo to Codecov**

Manual action (after GitHub push):

1. Go to https://app.codecov.io
2. Login with GitHub
3. Add the repo
4. Copy the upload token → add as `CODECOV_TOKEN` GitHub secret (cf Task 9.2)

- [ ] **Step 10.3: Commit**

```bash
git add codecov.yml
git commit -m "ci: Codecov config with 95% coverage gate on new code"
```

---

## Task 11: Lighthouse CI workflow

**Files:**
- Create: `lighthouserc.json`, `.github/workflows/lighthouse.yml`

- [ ] **Step 11.1: Create `lighthouserc.json`**

```json
{
  "ci": {
    "collect": {
      "url": ["http://localhost:3000/login"],
      "startServerCommand": "pnpm start",
      "startServerReadyPattern": "Ready in",
      "numberOfRuns": 3
    },
    "assert": {
      "assertions": {
        "categories:pwa": ["error", { "minScore": 0.9 }],
        "categories:accessibility": ["error", { "minScore": 0.9 }],
        "categories:performance": ["warn", { "minScore": 0.8 }],
        "categories:best-practices": ["warn", { "minScore": 0.9 }]
      }
    },
    "upload": {
      "target": "temporary-public-storage"
    }
  }
}
```

- [ ] **Step 11.2: Create Lighthouse workflow**

Create `.github/workflows/lighthouse.yml`:

```yaml
name: Lighthouse CI

on:
  pull_request:
    branches: [main, master]
  push:
    branches: [main, master]

jobs:
  lighthouse:
    name: Lighthouse
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: pnpm/action-setup@v4
        with: { version: 9 }
      - uses: actions/setup-node@v4
        with:
          node-version: 20
          cache: pnpm
      - run: pnpm install --frozen-lockfile
      - run: pnpm build
        env:
          NEXT_PUBLIC_SUPABASE_URL: https://example.supabase.co
          NEXT_PUBLIC_SUPABASE_ANON_KEY: anon-key-test
      - run: pnpm dlx @lhci/cli@0.14.x autorun
        env:
          NEXT_PUBLIC_SUPABASE_URL: https://example.supabase.co
          NEXT_PUBLIC_SUPABASE_ANON_KEY: anon-key-test
```

- [ ] **Step 11.3: Commit**

```bash
git add lighthouserc.json .github/workflows/lighthouse.yml
git commit -m "ci: Lighthouse CI gate on PWA/A11y/Perf"
```

---

## Task 12: Update README with quality gate instructions

**Files:**
- Modify: `README.md`

- [ ] **Step 12.1: Append quality gate section to README**

Add to `README.md` (after existing content):

```markdown
## Quality Gates

Voir `QUALITY_GATES.md` pour la politique complète.

**TL;DR développeur** :

```bash
pnpm lint          # ESLint
pnpm typecheck     # TypeScript
pnpm test          # Vitest
pnpm test:coverage # avec coverage
pnpm test:e2e      # Playwright
pnpm format        # Prettier auto-fix
pnpm build         # Build prod
```

Tous ces gates tournent automatiquement :
- Sur `git commit` (Prettier + ESLint + tsc + gitleaks + commitlint)
- Sur `git push` (typecheck + tests + build)
- Sur PR GitHub (tous les jobs CI + Lighthouse + Codecov)

Pour contourner un gate (cas rare et justifié), ajouter un commentaire avec justification au-dessus du code et utiliser `// eslint-disable-next-line <rule> -- <raison>`.
```

- [ ] **Step 12.2: Commit**

```bash
git add README.md
git commit -m "docs: README section on quality gates"
```

---

## Definition of Done (E1b)

- [ ] `pnpm lint` passes (0 erreur)
- [ ] `pnpm typecheck` passes (0 erreur)
- [ ] `pnpm format:check` passes
- [ ] `pnpm test:coverage` passes (les seuils peuvent échouer tant que peu de code → on les ajustera)
- [ ] Pre-commit hook bloque un commit qui contient une erreur ESLint
- [ ] Pre-commit hook bloque un commit avec un secret AWS factice
- [ ] commit-msg hook bloque un message non-Conventional Commits
- [ ] Pre-push hook s'exécute (test + build) avant un `git push`
- [ ] Workflow `.github/workflows/ci.yml` se déclenche sur PR (vérifiable après E1 Task 10 deploy)
- [ ] `QUALITY_GATES.md` à jour avec la stack effectivement installée
- [ ] README mentionne la section quality gates

---

## Notes pour l'engineer

- **Ordre d'exécution critique** : ce plan se déroule entre E1 Task 1 (scaffold) et E1 Task 2 (tooling). Ne pas démarrer E1 Task 2 ou suivantes avant que E1b soit complet, sinon du code applicatif (lib/env.ts, tests, composants…) ne passera pas par les gates dès son écriture.
- **Codecov token** : pour repo privé, indispensable. Pour repo public, optionnel. À configurer après le push GitHub (E1 Task 10).
- **SonarCloud upgrade** : si plus tard tu veux le vrai SonarCloud avec son dashboard, ajouter un job CI `sonarcloud-github-action` et un `sonar-project.properties`. Le reste de la stack (ESLint sonarjs, Codecov) reste compatible et complémentaire.
- **Strict TypeScript peut surprendre** : `noUncheckedIndexedAccess` change la signature de `array[i]` qui devient `T | undefined`. Soit gérer le undefined, soit utiliser `array.at(i)` qui est explicite. Pas de `as` non-justifié.
- **Cognitive complexity SonarJS à 15** : si un test/fonction dépasse, refactor en sous-fonctions. C'est volontairement strict.
