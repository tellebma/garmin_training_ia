# E-Q — SonarQube Quality Gate & 90 % Coverage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restaurer une Quality Gate SonarQube bloquante en CI, fusionner la
coverage frontend + worker dans le scan Sonar, faire passer la gate au vert,
et amener la coverage globale du projet à **90 %** (objectif owner).

**Architecture:** voir spec [`../specs/2026-05-19-eq-sonar-quality-gate-design.md`](../specs/2026-05-19-eq-sonar-quality-gate-design.md).

**Tech Stack:** GitHub Actions, `SonarSource/sonarqube-scan-action@v4`,
`SonarSource/sonarqube-quality-gate-action@v1.2.0`, Vitest v8 coverage,
pytest-cov, jq, curl.

**Spec reference:** [`../specs/2026-05-19-eq-sonar-quality-gate-design.md`](../specs/2026-05-19-eq-sonar-quality-gate-design.md).

**Branch:** `feat/eq-sonar-quality-gate` (créée depuis `main` après merge E7
dashboard, OU exécutable directement depuis `main` car aucun conflit attendu
avec E7).

**Execution timing:** EPIC transversal. Idéal après E7 et avant E9 (beta
privée). Toutes les phases sont séquentielles ; la Phase 1 est indépendante
du reste et peut être merged seule.

---

## File Structure

```
garmin_training/
├── .github/workflows/
│   ├── ci.yml                          ← MOD: job sonarqube blocking + merge coverage
│   └── worker-ci.yml                   ← MOD: upload coverage avec retention 1d
├── sonar-project.properties            ← MOD: exclusions affinées, version
├── vitest.config.ts                    ← MOD: thresholds 90/85/90/90
├── worker/pyproject.toml               ← MOD: pytest --cov-fail-under=90
├── components/
│   └── forms/
│       └── form-field.tsx              ← NEW: composant partagé (anti-duplication)
├── app/(app)/
│   ├── onboarding/_components/         ← MOD: 4 forms refactor avec FormField
│   └── profile/_components/            ← MOD: 2 forms refactor avec FormField
├── worker/src/garmin_sync/
│   ├── main.py                         ← MOD: Annotated dependency injection
│   └── coach/
│       ├── banister.py                 ← MOD: retirer code commenté
│       └── planner.py                  ← MOD: refactor cognitive complexity
├── tests/unit/
│   ├── lib/
│   │   ├── worker.test.ts              ← NEW
│   │   ├── supabase/server.test.ts     ← NEW
│   │   └── supabase/middleware.test.ts ← NEW
│   ├── actions/garmin-auth.test.ts     ← NEW
│   ├── components/
│   │   ├── auth/                       ← NEW (3 fichiers)
│   │   ├── garmin/                     ← NEW (2 fichiers)
│   │   └── nav/                        ← NEW (2 fichiers)
│   └── forms/
│       └── form-field.test.tsx         ← NEW
├── QUALITY_GATES.md                    ← MOD: section Sonar gate
└── CLAUDE.md                           ← MOD: statut E-Q
```

---

## Phase 1 — Infrastructure CI

### Task 1 : Inspecter et confirmer la baseline

**Files:** (lecture seule)

- [ ] **Step 1.1 :** Lire les fichiers existants pour vérifier qu'aucune
      modif récente n'a changé l'analyse :

```bash
cat .github/workflows/ci.yml
cat .github/workflows/worker-ci.yml
cat sonar-project.properties
cat vitest.config.ts
cat worker/pyproject.toml
```

- [ ] **Step 1.2 :** Capturer le snapshot Sonar baseline (référence pour la PR
      finale) :

```bash
curl -sS -u "${SONAR_TOKEN_TELLEBMA}:" \
  "https://sonarqube.tellebma.fr/api/measures/component?component=garmin_training_ia&metricKeys=alert_status,coverage,new_coverage,duplicated_lines_density,new_duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots,ncloc" \
  | jq . > /tmp/sonar-baseline.json

cat /tmp/sonar-baseline.json
```

Garder ce fichier pour la description de la PR finale.

- [ ] **Step 1.3 :** Vérifier que `SONAR_TOKEN` et `SONAR_HOST_URL` sont bien
      des GitHub Actions secrets dans le repo (la CI actuelle les utilise déjà,
      donc OK) :

```bash
gh api repos/tellebma/garmin_training_ia/actions/secrets --jq '.secrets[].name'
```

Expected : `SONAR_TOKEN`, `SONAR_HOST_URL` présents.

---

### Task 2 : Fusionner coverage frontend + worker dans le scan Sonar

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `.github/workflows/worker-ci.yml`
- Modify: `sonar-project.properties`

Le job `sonarqube` actuel ne télécharge que la coverage frontend. Le worker
remonte donc comme « 0 % couvert » dans Sonar alors qu'il a 46 tests.

- [ ] **Step 2.1 :** Modifier `worker-ci.yml` pour augmenter la rétention de
      l'artefact (la CI principale doit pouvoir le lire depuis un run worker
      potentiellement antérieur du même SHA, mais on va plutôt déclencher le
      worker depuis ci.yml directement — cf Step 2.2).

```yaml
# .github/workflows/worker-ci.yml — pas de changement immédiat ici,
# on aurait pu retention-days: 7, mais la solution propre est d'exécuter
# pytest dans ci.yml pour récupérer l'artefact dans le même run.
```

**Décision :** ajouter un job `test-worker` directement dans `ci.yml` qui
produit `worker-coverage-lcov`. `worker-ci.yml` reste pour la version Docker
build et la garde-fou paths-filter (`paths: ['worker/**']`).

- [ ] **Step 2.2 :** Ajouter le job `test-worker` dans `ci.yml`, AVANT le job
      `sonarqube` (qui en dépend) :

```yaml
  test-worker:
    name: Worker tests + coverage
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: worker
    steps:
      - uses: actions/checkout@v4
      - name: Install uv
        uses: astral-sh/setup-uv@v3
        with: { version: '0.5.x' }
      - name: Install Python
        run: uv python install 3.12
      - name: Install deps
        run: uv sync --all-groups --frozen
      - name: Pytest with coverage
        run: uv run pytest --cov=garmin_sync --cov-report=lcov:coverage/lcov.info
      - name: Upload worker coverage artifact
        uses: actions/upload-artifact@v4
        with:
          name: worker-coverage-lcov
          path: worker/coverage/lcov.info
          retention-days: 1
```

- [ ] **Step 2.3 :** Modifier le job `sonarqube` pour télécharger les deux
      artefacts ET dépendre des deux jobs de tests :

```yaml
  sonarqube:
    name: SonarQube scan + gate
    runs-on: ubuntu-latest
    needs: [test-unit, test-worker]
    steps:
      - uses: actions/checkout@v4
        with: { fetch-depth: 0 }
      - name: Download frontend coverage
        uses: actions/download-artifact@v4
        with:
          name: coverage-lcov
          path: coverage/
      - name: Download worker coverage
        uses: actions/download-artifact@v4
        with:
          name: worker-coverage-lcov
          path: worker/coverage/
      - name: SonarQube scan
        uses: SonarSource/sonarqube-scan-action@v4
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
      # Quality gate ajouté en Task 3
```

- [ ] **Step 2.4 :** Vérifier `sonar-project.properties` :

  Ajuster les exclusions pour exclure les routes pures (RSC) sans logique :

```properties
# Coverage exclusions — fichiers qui n'ont pas de logique testable
sonar.coverage.exclusions=\
  app/**/layout.tsx,\
  app/**/loading.tsx,\
  app/**/error.tsx,\
  app/**/not-found.tsx,\
  app/**/page.tsx,\
  components/ui/**,\
  supabase/migrations/**,\
  worker/src/garmin_sync/main.py
```

  Note : `main.py` du worker = FastAPI app entry, testé en intégration via
  `test_main.py` mais les decorators `@app.post(...)` ne montent pas en
  unitaire. Exclure de la coverage Sonar (déjà la pratique d'usage).

  Ajouter `sonar.projectVersion` qui suit la version `package.json` :

```properties
sonar.projectVersion=0.1.0
```

- [ ] **Step 2.5 :** Commit :

```bash
git add .github/workflows/ci.yml sonar-project.properties
git commit -m "ci: merge worker coverage into SonarQube scan"
```

---

### Task 3 : Activer la Quality Gate bloquante

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 3.1 :** Ajouter le step quality-gate APRÈS le scan dans le job
      `sonarqube` :

```yaml
      - name: SonarQube quality gate check
        id: sonarqube-quality-gate-check
        uses: SonarSource/sonarqube-quality-gate-action@v1.2.0
        timeout-minutes: 10
        with:
          pollingTimeoutSec: 600
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
```

  Cette action lit le `report-task.txt` produit par le scan-action, polle
  l'API SonarQube jusqu'à 10 min, et **fait échouer** le step si la gate est
  ERROR.

- [ ] **Step 3.2 :** Ajouter aussi un fallback "verify coverage ≥ 90 %"
      (objectif owner, non couvert par la gate Sonar par défaut qui ne check
      que new_coverage) :

```yaml
      - name: Enforce 90% global coverage (owner objective)
        env:
          SONAR_TOKEN: ${{ secrets.SONAR_TOKEN }}
          SONAR_HOST_URL: ${{ secrets.SONAR_HOST_URL }}
        run: |
          set -euo pipefail
          # Attendre que le scan soit indexé (l'action quality-gate l'a déjà fait, mais on est sûrs)
          sleep 5
          COVERAGE=$(curl -sS -u "${SONAR_TOKEN}:" \
            "${SONAR_HOST_URL}/api/measures/component?component=garmin_training_ia&metricKeys=coverage" \
            | jq -r '.component.measures[0].value // "0"')
          echo "Global coverage: ${COVERAGE}%"
          awk -v c="$COVERAGE" 'BEGIN { exit (c+0 < 90) ? 1 : 0 }'
```

  Note : tant que la coverage est < 90 %, ce step échouera. C'est attendu
  jusqu'à la fin de Phase 3. Pour ne pas bloquer la Phase 1 qui n'a pas
  vocation à atteindre 90 %, on encapsule ce step derrière un toggle :

```yaml
      - name: Enforce 90% global coverage (owner objective)
        if: vars.ENFORCE_90_COVERAGE == 'true'
        # … reste identique
```

  → la Phase 3 activera la repo variable `ENFORCE_90_COVERAGE=true` une fois
  le seuil franchi.

- [ ] **Step 3.3 :** Tester la chaîne avec un commit volontairement cassant
      sur une branche feature :

```bash
git checkout -b test/break-sonar-gate
# ajouter du code dupliqué ou non-couvert
git commit -am "test: deliberately break sonar gate"
git push -u origin test/break-sonar-gate
gh pr create --title "test: sonar gate enforcement" --body "Should FAIL on sonarqube job"
```

Expected : la PR check `sonarqube` doit être ❌ rouge.

```bash
# rollback
git checkout main
gh pr close test/break-sonar-gate --delete-branch
```

- [ ] **Step 3.4 :** Commit :

```bash
git add .github/workflows/ci.yml
git commit -m "ci: enforce SonarQube quality gate blocking on PR/push"
```

---

### Task 4 : Documenter la gate

**Files:**
- Modify: `QUALITY_GATES.md`
- Modify: `CLAUDE.md`

- [ ] **Step 4.1 :** Ajouter une section "SonarQube" dans `QUALITY_GATES.md`
      (entre les sections existantes "CI pipeline" et "Coverage") :

```markdown
### SonarQube quality gate

URL : https://sonarqube.tellebma.fr/dashboard?id=garmin_training_ia
Profile : Sonar way (defaults)

**Conditions bloquantes sur new code (PR/push)** :

| Condition | Threshold |
|-----------|-----------|
| Coverage on new code | ≥ 80 % |
| Duplicated lines on new code | < 3 % |
| Maintainability rating | A |
| Reliability rating | A |
| Security rating | A |
| Security hotspots reviewed | 100 % |
| New violations | 0 |

**Conditions bloquantes globales (objectif owner)** :

| Condition | Threshold |
|-----------|-----------|
| Coverage globale | ≥ 90 % |

**Comment ça s'enforce** : voir job `sonarqube` dans `.github/workflows/ci.yml`.
Le step `SonarSource/sonarqube-quality-gate-action@v1.2.0` fait échouer la
CI si la gate est ERROR. Un step custom vérifie en plus la coverage globale
≥ 90 % (toggle `ENFORCE_90_COVERAGE` repo variable).
```

- [ ] **Step 4.2 :** Mettre à jour `CLAUDE.md` table EPIC pour ajouter une
      ligne :

```markdown
| **E-Q — SonarQube Quality** | 🟡 En cours |
```

- [ ] **Step 4.3 :** Commit Phase 1 complète :

```bash
git add QUALITY_GATES.md CLAUDE.md
git commit -m "docs(eq): document SonarQube quality gate policy"
```

- [ ] **Step 4.4 :** Ouvrir une première PR "Phase 1" qui peut merger seule :

```bash
gh pr create --title "feat(eq): SonarQube quality gate phase 1 — CI infrastructure" \
  --body "Phase 1 of E-Q EPIC. Adds blocking SonarQube QG check, merges worker coverage."
```

  Merge cette PR avant Phase 2.

---

## Phase 2 — Fix des 28 code smells

### Task 5 : Auto-fix des règles React/TS

**Files:**
- Modify: `app/(app)/onboarding/_components/step-dispo-form.tsx`
- Modify: `app/(app)/onboarding/_components/step-perf-form.tsx`
- Modify: `app/(app)/onboarding/_components/step-perso-form.tsx`
- Modify: `app/(app)/onboarding/_components/step-race-form.tsx`
- Modify: `app/(app)/profile/_components/perso-edit-form.tsx`
- Modify: `app/(app)/profile/_components/race-edit-form.tsx`

`typescript:S6772` (13×) — *Ambiguous spacing before `<span>` element* : il
manque un `{' '}` explicite ou un wrapper. `typescript:S6754` (3×) —
`useState` non déstructuré (sont des `setState` only). `typescript:S7735` (2×).

- [ ] **Step 5.1 :** Tenter l'auto-fix global :

```bash
pnpm lint:fix
```

  ESLint ne corrige PAS S6772 automatiquement (rule SonarJS sans fixer). Donc
  fix manuel ligne par ligne.

- [ ] **Step 5.2 :** Corriger les 13 `S6772` — patron de fix :

```diff
- <span className="text-destructive">*</span>
+ <span className="text-destructive">{' '}*</span>
```

  ou utiliser un wrapper :

```tsx
<Label>
  Nom <span className="text-destructive">*</span>
</Label>
```

  Lister les lignes via :

```bash
grep -nE '<span className="text-destructive"' app/\(app\)/onboarding/_components/*.tsx app/\(app\)/profile/_components/*.tsx
```

  Fixer chacune. Re-run :

```bash
pnpm lint
```

- [ ] **Step 5.3 :** Corriger les 3 `S6754` (useState non-déstructuré) :

```diff
- const isSubmitting = useState(false)
+ const [isSubmitting, setIsSubmitting] = useState(false)
```

  Lignes :
  - `app/(app)/profile/_components/race-edit-form.tsx:105`
  - `app/(app)/onboarding/_components/step-perso-form.tsx:24`
  - `app/(app)/onboarding/_components/step-race-form.tsx:76`

- [ ] **Step 5.4 :** Corriger les 2 `S7735` (regarder le détail via Sonar UI
      ou API — souvent règle sur Promise/async non-awaited).

```bash
curl -sS -u "${SONAR_TOKEN_TELLEBMA}:" \
  "https://sonarqube.tellebma.fr/api/issues/search?componentKeys=garmin_training_ia&rules=typescript:S7735&resolved=false" \
  | jq '.issues[] | {file: .component, line: .line, msg: .message}'
```

- [ ] **Step 5.5 :** `pnpm typecheck && pnpm test && pnpm lint` doivent
      passer.

- [ ] **Step 5.6 :** Commit :

```bash
git commit -am "fix(forms): resolve SonarJS S6772/S6754/S7735 in onboarding+profile forms"
```

---

### Task 6 : Refactor FastAPI Annotated injection (5× S8410)

**Files:**
- Modify: `worker/src/garmin_sync/main.py`

`python:S8410` (5×, BLOCKER) — *Use "Annotated" type hints for FastAPI
dependency injection*.

- [ ] **Step 6.1 :** Lire les 5 lignes incriminées :

```bash
grep -nE "Depends\(" worker/src/garmin_sync/main.py
```

- [ ] **Step 6.2 :** Refactor pattern :

```diff
- def endpoint(user: dict = Depends(verify_jwt)):
+ from typing import Annotated
+ def endpoint(user: Annotated[dict, Depends(verify_jwt)]):
```

  Appliquer aux 5 occurrences. Imports : `from typing import Annotated`.

- [ ] **Step 6.3 :** Tests worker :

```bash
cd worker
uv run pytest -v tests/test_main.py
```

  Expected : tous les tests passent (changement de signature transparent
  pour FastAPI).

- [ ] **Step 6.4 :** Commit :

```bash
git commit -am "refactor(worker): use Annotated[T, Depends(...)] for FastAPI DI (S8410)"
```

---

### Task 7 : Cleanup worker (S125, S1192, S3776)

**Files:**
- Modify: `worker/src/garmin_sync/coach/banister.py`
- Modify: `worker/src/garmin_sync/coach/planner.py`
- Modify: 1-2 fichiers worker selon les S1192 (à identifier)

- [ ] **Step 7.1 :** Retirer le code commenté dans `banister.py:28` :

```bash
sed -n '20,40p' worker/src/garmin_sync/coach/banister.py
```

  Supprimer les lignes commentées (sauf docstrings/comments expliquant le
  pourquoi).

- [ ] **Step 7.2 :** Identifier les 3 strings dupliquées (`S1192`) :

```bash
curl -sS -u "${SONAR_TOKEN_TELLEBMA}:" \
  "https://sonarqube.tellebma.fr/api/issues/search?componentKeys=garmin_training_ia&rules=python:S1192&resolved=false" \
  | jq '.issues[] | {file: .component, line: .line, msg: .message}'
```

  Pour chaque occurrence, extraire la string vers une constante module-level :

```python
_ACTIVITY_KEY_RUN = "run"  # ou nom plus parlant
```

- [ ] **Step 7.3 :** Refactor cognitive complexity dans `planner.py:85`
      (S3776, 23 → 15) :

  Lire la fonction concernée :

```bash
sed -n '85,160p' worker/src/garmin_sync/coach/planner.py
```

  Approches possibles :
  - Extraire les blocs `if/elif/elif` en fonctions helpers (`_apply_phase_rules`,
    `_pick_session_type`, etc.).
  - Remplacer un `match` ou un dict-dispatch pour les phases.

  **GARDE-FOU :** avant refactor, lancer `uv run pytest worker/tests/coach/ -v`
  → tous verts. Re-lancer après refactor → identiques.

- [ ] **Step 7.4 :** Tests worker complets :

```bash
cd worker && uv run pytest -v && uv run ruff check . && uv run mypy src/
```

- [ ] **Step 7.5 :** Commit :

```bash
git commit -am "refactor(worker/coach): cleanup S125/S1192/S3776 (planner complexity)"
```

---

### Task 8 : Extraire `<FormField>` pour stopper la duplication

**Files:**
- Create: `components/forms/form-field.tsx`
- Create: `tests/unit/forms/form-field.test.tsx`
- Modify: tous les `app/(app)/{onboarding,profile}/_components/*-form.tsx`

L'objectif est de faire baisser `new_duplicated_lines_density` sous 3 %. Le
pattern dupliqué est :

```tsx
<div className="space-y-2">
  <Label htmlFor={id}>{label} <span className="text-destructive">*</span></Label>
  <Input id={id} {...props} />
  {error && <p className="text-sm text-destructive">{error}</p>}
</div>
```

- [ ] **Step 8.1 :** Créer `components/forms/form-field.tsx` :

```tsx
import type { ComponentPropsWithoutRef, ReactNode } from 'react'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { cn } from '@/lib/utils'

type FormFieldProps = {
  id: string
  label: ReactNode
  required?: boolean
  error?: string
  hint?: ReactNode
} & Omit<ComponentPropsWithoutRef<typeof Input>, 'id'>

export function FormField({ id, label, required, error, hint, className, ...input }: FormFieldProps) {
  return (
    <div className={cn('space-y-2', className)}>
      <Label htmlFor={id}>
        {label}
        {required ? <span className="text-destructive">{' '}*</span> : null}
      </Label>
      <Input id={id} aria-invalid={error ? true : undefined} {...input} />
      {hint ? <p className="text-sm text-muted-foreground">{hint}</p> : null}
      {error ? <p className="text-sm text-destructive">{error}</p> : null}
    </div>
  )
}
```

- [ ] **Step 8.2 :** Créer le test :

```tsx
// tests/unit/forms/form-field.test.tsx
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FormField } from '@/components/forms/form-field'

describe('FormField', () => {
  it('renders label and input with id link', () => {
    render(<FormField id="name" label="Nom" />)
    expect(screen.getByLabelText('Nom')).toBeInTheDocument()
  })

  it('shows required marker', () => {
    render(<FormField id="name" label="Nom" required />)
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('renders error message', () => {
    render(<FormField id="name" label="Nom" error="Required" />)
    expect(screen.getByText('Required')).toBeInTheDocument()
  })

  it('renders hint', () => {
    render(<FormField id="name" label="Nom" hint="Format libre" />)
    expect(screen.getByText('Format libre')).toBeInTheDocument()
  })
})
```

- [ ] **Step 8.3 :** Refactor les 6 fichiers de formulaires pour utiliser
      `<FormField>`. Travailler fichier par fichier, lancer `pnpm test` après
      chaque pour s'assurer qu'aucun test e2e ne casse.

- [ ] **Step 8.4 :** Vérifier la baisse de duplication :

```bash
# Localement, via le scanner
pnpm lint
# Ne renseigne pas la duplication. C'est SonarQube qui mesure après push.
```

  → push la branche, attendre la CI, vérifier sur Sonar UI que
  `new_duplicated_lines_density` < 3 %.

- [ ] **Step 8.5 :** Commit :

```bash
git commit -am "refactor(forms): extract <FormField> shared component (kills duplication)"
```

- [ ] **Step 8.6 :** Ouvrir PR Phase 2 et merger :

```bash
gh pr create --title "fix(eq): SonarQube phase 2 — zero MAJOR+ smells, dedupe forms" \
  --body "Fixes 28 SonarQube issues. Duplication new code < 3%."
```

Verification Sonar après merge :

```bash
curl -sS -u "${SONAR_TOKEN_TELLEBMA}:" \
  "https://sonarqube.tellebma.fr/api/qualitygates/project_status?projectKey=garmin_training_ia" \
  | jq '.projectStatus.status'
```

  Expected sur `main` après merge Phase 2 : `"OK"` sur les conditions
  "new code" (violations + duplication). Coverage condition reste KO car
  encore < 80 % new code.

---

## Phase 3 — Atteindre 90 % de coverage

### Task 9 : Tests `lib/worker.ts` (HTTP client → worker)

**Files:**
- Create: `tests/unit/lib/worker.test.ts`

`lib/worker.ts` contient le client `fetch()` qui appelle le worker depuis les
Server Actions. Facile à tester avec `vi.fn()`.

- [ ] **Step 9.1 :** Lire `lib/worker.ts` pour identifier les fonctions
      exportées et les branches (success/error_id/network).

- [ ] **Step 9.2 :** Écrire le fichier de test :

```ts
// tests/unit/lib/worker.test.ts
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { callWorker } from '@/lib/worker'

const ORIGINAL_FETCH = global.fetch

describe('callWorker', () => {
  beforeEach(() => {
    vi.stubEnv('WORKER_URL', 'http://worker.local')
    vi.stubEnv('WORKER_SHARED_TOKEN', 'test-token')
    global.fetch = vi.fn()
  })
  afterEach(() => {
    global.fetch = ORIGINAL_FETCH
    vi.unstubAllEnvs()
  })

  it('sends shared token header', async () => {
    (fetch as ReturnType<typeof vi.fn>).mockResolvedValueOnce(
      new Response(JSON.stringify({ ok: true }), { status: 200 })
    )
    await callWorker('/garmin/connect', { method: 'POST' })
    const call = (fetch as ReturnType<typeof vi.fn>).mock.calls[0]
    expect(call[1].headers).toMatchObject({ 'X-Worker-Token': 'test-token' })
  })

  // … 4-5 tests : success JSON, success no body, error_id, network error, timeout
})
```

  Cibler **100 %** de coverage sur `lib/worker.ts` (fichier petit, fortement
  utilisé).

- [ ] **Step 9.3 :** `pnpm test:coverage` localement → vérifier que
      `lib/worker.ts` est ≥ 95 % couvert.

- [ ] **Step 9.4 :** Commit.

---

### Task 10 : Tests `lib/supabase/{server,middleware,browser}.ts`

**Files:**
- Create: `tests/unit/lib/supabase/server.test.ts`
- Create: `tests/unit/lib/supabase/middleware.test.ts`
- Create: `tests/unit/lib/supabase/browser.test.ts` (si pas déjà existant)

- [ ] **Step 10.1 :** Lire les 3 fichiers.

- [ ] **Step 10.2 :** Mocker `@supabase/ssr` (`createServerClient`) avec
      `vi.mock('@supabase/ssr', ...)` et vérifier :
  - Le client est créé avec les bonnes URLs / keys (depuis `lib/env.ts`)
  - Les cookies sont correctement passés (`cookies()` de `next/headers`)
  - La factory est appelée à chaque invocation (pas de singleton qui leak
    entre requêtes)

- [ ] **Step 10.3 :** Commit.

---

### Task 11 : Tests Server Actions restantes

**Files:**
- Create: `tests/unit/actions/garmin-auth.test.ts`

L'action `app/actions/garmin-auth.ts` orchestre le call worker via
`callWorker`. Tests :

- [ ] **Step 11.1 :** Mocker `callWorker`, `cookies()`, redirect (`next/navigation`).

- [ ] **Step 11.2 :** Couvrir :
  - Connect Garmin OK (worker répond `{status: "connected"}`)
  - Connect Garmin demande MFA (`{status: "mfa_required"}`)
  - Worker répond error_id → action retourne un message d'erreur
  - User non authentifié → throw / redirect login
  - Body mal formé (zod fail) → retourne erreur form

- [ ] **Step 11.3 :** Commit.

---

### Task 12 : Tests composants Auth/Garmin/Nav

**Files:**
- Create: `tests/unit/components/auth/magic-link-form.test.tsx`
- Create: `tests/unit/components/auth/sign-out-button.test.tsx`
- Create: `tests/unit/components/garmin/connect-form.test.tsx`
- Create: `tests/unit/components/garmin/mfa-form.test.tsx`
- Create: `tests/unit/components/nav/bottom-nav.test.tsx`
- Create: `tests/unit/components/nav/side-nav.test.tsx`

Setup React Testing Library si pas déjà :

- [ ] **Step 12.1 :** Vérifier la stack :

```bash
grep -E "@testing-library|jsdom" package.json
```

Si manquant :

```bash
pnpm add -D @testing-library/react @testing-library/dom @testing-library/user-event jsdom
```

  Et activer `environment: 'jsdom'` dans `vitest.config.ts` pour les fichiers
  `*.test.tsx` (via `environmentMatchGlobs`) :

```ts
test: {
  environment: 'node',
  environmentMatchGlobs: [['tests/unit/components/**', 'jsdom'], ['tests/unit/forms/**', 'jsdom']],
  ...
}
```

- [ ] **Step 12.2 :** Pour chaque composant, écrire 3-5 tests :
  - Render initial
  - Interaction utilisateur (`userEvent.type`, `userEvent.click`)
  - États de chargement / erreur
  - Mock `next/navigation` pour `redirect`, `useRouter`

- [ ] **Step 12.3 :** `pnpm test:coverage` → vérifier que tous les `components/auth/`,
      `components/garmin/`, `components/nav/` sont ≥ 90 % couverts.

- [ ] **Step 12.4 :** Commit chacun progressivement (1 commit par module).

---

### Task 13 : Tests handlers formulaires onboarding (extraits)

**Files:**
- Modify: `app/(app)/onboarding/_components/step-*-form.tsx` (extraire les
  handlers pures)
- Create: `tests/unit/onboarding/handlers.test.ts`

Les Client Components React sont complexes à tester en isolation. Pattern :
extraire les handlers (validation, transformation) en fonctions pures dans
`app/(app)/onboarding/_lib/` puis tester ces fonctions.

- [ ] **Step 13.1 :** Identifier les handlers réutilisables/testables :
  - `handleSubmit` validation+payload preparation
  - Helpers `formatDuration`, `parseHRZones`, etc.

- [ ] **Step 13.2 :** Les déplacer dans `app/(app)/onboarding/_lib/handlers.ts`.

- [ ] **Step 13.3 :** Écrire les tests unitaires :

```ts
describe('prepareSubmitPayload', () => {
  it('drops empty optional fields', () => { ... })
  it('throws if name missing', () => { ... })
  it('converts duration "5h30" to minutes', () => { ... })
})
```

- [ ] **Step 13.4 :** Commit.

---

### Task 14 : Activer les seuils 90 % + finaliser

**Files:**
- Modify: `vitest.config.ts`
- Modify: `worker/pyproject.toml`
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 14.1 :** Vérifier la coverage locale :

```bash
pnpm test:coverage
```

  Output attendu : > 90 % lines/statements, > 85 % branches.

```bash
cd worker && uv run pytest --cov=garmin_sync --cov-report=term-missing
```

  Output attendu : > 90 % lines.

- [ ] **Step 14.2 :** Activer les thresholds Vitest dans `vitest.config.ts` :

```ts
coverage: {
  // ...
  thresholds: {
    lines: 90,
    functions: 90,
    branches: 85,
    statements: 90,
  },
}
```

  Retirer le hack `--coverage.thresholds.100=false` du script CI :

```diff
- "test:coverage:ci": "vitest run --coverage --coverage.thresholds.100=false",
+ "test:coverage:ci": "vitest run --coverage",
```

- [ ] **Step 14.3 :** Activer `--cov-fail-under=90` côté worker :

  Dans `worker/pyproject.toml`, ajouter à `[tool.pytest.ini_options]` :

```toml
addopts = "-v --cov=garmin_sync --cov-report=term-missing --cov-fail-under=90"
```

  ou laisser le flag dans le job CI :

```yaml
- run: uv run pytest --cov=garmin_sync --cov-report=lcov:coverage/lcov.info --cov-fail-under=90
```

- [ ] **Step 14.4 :** Activer le toggle Sonar gate 90 % global :

```bash
gh variable set ENFORCE_90_COVERAGE --body "true"
```

- [ ] **Step 14.5 :** Push, attendre la CI. Toutes les checks doivent être
      vertes y compris `Enforce 90% global coverage` et la Quality Gate
      Sonar (alert_status=OK).

- [ ] **Step 14.6 :** Mettre à jour `CLAUDE.md` :

```diff
- | **E-Q — SonarQube Quality** | 🟡 En cours |
+ | **E-Q — SonarQube Quality** | ✅ Livré (coverage 90 %, gate enforced) |
```

  Et dans la section "Statut actuel" :

```markdown
| E-Q — SonarQube Quality | ✅ Livré (coverage 90 %, gate enforced) |
```

- [ ] **Step 14.7 :** Commit final + PR Phase 3 :

```bash
git commit -am "feat(eq): enforce 90% coverage thresholds (Vitest + pytest + Sonar)"
gh pr create --title "feat(eq): SonarQube phase 3 — 90% coverage achieved" \
  --body "Coverage frontend 90%+, worker 90%+, Sonar gate green."
```

---

## Definition of Done (E-Q)

- [ ] CI job `sonarqube` échoue quand la gate Sonar est ERROR (testé en Step 3.3)
- [ ] Coverage worker visible dans Sonar (> 80 % sur `worker/src/**`)
- [ ] Métrique Sonar `coverage` ≥ 90 %
- [ ] Métrique Sonar `new_duplicated_lines_density` < 3 %
- [ ] 0 BLOCKER, 0 CRITICAL, 0 MAJOR ouvert sur Sonar
- [ ] Quality Gate Sonar = PASSED sur `main`
- [ ] `QUALITY_GATES.md` documente la gate et le seuil 90 %
- [ ] `CLAUDE.md` ligne E-Q ✅
- [ ] 3 PRs merged (1 par phase)

---

## Notes pour l'engineer

- **Ordre des phases :** Phase 1 doit merger avant Phase 2 (sinon les fixes
  Phase 2 ne sont pas validés par une gate). Phase 2 peut merger avant
  Phase 3 (coverage <90% n'est enforced qu'au step 14.4).
- **Sub-agent split :** Phase 2 et Phase 3 sont parallélisables par
  sub-task (S6772 ≠ S8410 ≠ S3776). Utiliser
  `superpowers:dispatching-parallel-agents` pour Tasks 5/6/7 simultanément.
- **Sonar way profile :** on ne modifie PAS le profile. Si une règle nous
  ennuie vraiment, on la désactive **localement** via `// NOSONAR <raison>`
  ou via la UI Sonar (besoin admin). Le owner n'est pas admin sur
  l'instance, donc pas de modification de la gate elle-même.
- **`callWorker` est appelé depuis Server Actions** : faire tourner le test
  en `environment: 'node'` (pas jsdom).
- **Tests Client Components** : `environment: 'jsdom'` + `@testing-library/react`.
  Mocker `next/navigation`, `next/headers` (le second crashe en jsdom).
- **Worker `--cov-fail-under=90`** : si certains modules ne peuvent pas
  monter à 90 % (ex: `main.py` FastAPI app entry), les exclure via
  `[tool.coverage.run] omit = ["src/garmin_sync/main.py"]` dans
  `pyproject.toml` — déjà exclu Sonar via `sonar.coverage.exclusions`.
- **Validation finale :** après merge Phase 3 sur `main`, attendre 1 run
  CI complet, puis interroger l'API Sonar pour confirmer
  `alert_status=OK` et `coverage≥90`.
