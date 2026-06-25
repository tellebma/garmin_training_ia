# Quality Gates — Garmin Training Coach

> Politique qualité du projet. Tous les contributeurs (humains et subagents) doivent respecter ces gates.
> Si un gate KO bloque le travail légitimement → on corrige le code, on ne contourne pas le gate.

## Principes

1. **Évidence avant assertion** : aucune affirmation de "ça marche" sans output de commande prouvant le succès.
2. **Fail fast, fail local** : le maximum de gates en local (pre-commit/pre-push) pour ne pas attendre la CI.
3. **Pas de skip silencieux** : `--no-verify`, `// eslint-disable`, `@ts-ignore` interdits sauf justification écrite dans le code adjacent.
4. **Couverture sur le nouveau code** : on ne demande pas 95% partout, on demande 95% sur ce qu'on ajoute/modifie.
5. **Gates progressifs** : niveau de strictness augmente avec la maturité du module.

---

## Niveau 1 — Pre-commit (local, automatisé, < 5s)

Outil : **husky + lint-staged**. S'exécute sur les fichiers stagés uniquement.

| Gate | Outil | Comportement |
|---|---|---|
| Formattage | Prettier 3 | Auto-fix puis re-stage |
| Lint zéro erreur | ESLint 9 (config flat) + plugins : `next`, `typescript-eslint`, `sonarjs`, `unicorn`, `tailwindcss` | Bloque si erreur, auto-fix si possible |
| Types stricts | `tsc --noEmit` (incrémental sur fichiers modifiés via `tsc-files`) | Bloque si erreur |
| Pas de secret en clair | `gitleaks protect --staged` | Bloque si pattern de secret détecté |
| Message de commit | `commitlint` + Conventional Commits | Bloque si format invalide |

**Setup** : `pnpm install` exécute `husky install` automatiquement (post-install hook).

**Format Conventional Commits attendu :**
```
<type>(<scope>): <subject>

<body optional>

<footer optional>
```
Types autorisés : `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`.

---

## Niveau 2 — Pre-push (local, automatisé, ~30s)

Outil : **husky pre-push hook**.

| Gate | Commande | Seuil |
|---|---|---|
| Tests unitaires complets | `pnpm test` | 100% pass |
| TypeCheck projet | `pnpm typecheck` | 0 erreur |
| Build prod | `pnpm build` | succès |
| Pas de tests `.only` ou `.skip` | grep | 0 occurrence |

Si l'un échoue → push refusé.

---

## Niveau 3 — CI GitHub Actions (bloquant pour merge)

Workflow `.github/workflows/ci.yml` déclenché sur :
- Pull request vers `main`
- Push direct sur `main` (deploy)

### Jobs CI

| Job | Étapes | Seuil |
|---|---|---|
| **lint** | ESLint + Prettier check | 0 erreur |
| **typecheck** | `tsc --noEmit` | 0 erreur |
| **test-unit** | Vitest + coverage v8 | Tests pass + coverage uploadé Codecov |
| **test-e2e** | Playwright (chromium headless) | Tests pass |
| **build** | `pnpm build` | succès |
| **audit** | `pnpm audit --prod --audit-level=high` | 0 high/critical CVE |
| **secrets** | `gitleaks detect` | 0 leak |
| **lighthouse** | LHCI sur `/login` + `/today` | PWA ≥ 90, A11y ≥ 90, Perf ≥ 80 |
| **db-migrations** | `supabase db reset` sur DB éphémère | succès |
| **quality-gate** | Coverage diff Codecov + SonarJS rules ESLint | **Coverage nouveau code ≥ 95%** |
| **sonarqube** | SonarQube scan + quality gate (bloquant) | Gate Sonar = PASSED + coverage globale ≥ 90 % |

### SonarQube quality gate (E-Q EPIC)

**URL** : https://sonarqube.tellebma.fr/dashboard?id=garmin_training_ia
**Profile** : Sonar way (defaults, projet non-admin)

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

**Comment ça s'enforce** : job `sonarqube` dans `.github/workflows/ci.yml` :
1. `SonarSource/sonarqube-scan-action@v4` pousse le scan
2. `SonarSource/sonarqube-quality-gate-action@v1.2.0` polle l'API et fait
   échouer le step si la gate est ERROR (timeout 10 min)
3. Un step custom appelle `api/measures/component` et vérifie
   `coverage ≥ 90 %`. Activé via repo variable `ENFORCE_90_COVERAGE=true`
   (à activer une fois Phase 3 E-Q terminée).

**Coverage merge** : le job télécharge deux artefacts (frontend Vitest +
worker pytest, tous deux en LCOV) que `sonar-project.properties` consomme
via `sonar.javascript.lcov.reportPaths` et `sonar.python.coverage.reportPaths`.

### Quality Gate "coverage 95% sur nouveau code"

**Approche retenue (pragmatique MVP) :**

Plutôt que de payer SonarCloud (10€/mois pour repo privé) ou self-host SonarQube, on combine :

1. **`eslint-plugin-sonarjs`** : 60+ règles SonarQube directement dans ESLint (zéro coût, intégré au lint normal). Couvre cognitive complexity, duplications, code smells, bug patterns.
2. **Codecov free tier** : tracking coverage, diff report sur PRs (gratuit pour ≤ 5 contributeurs privés).
3. **`diff-cover`** ou seuil GitHub Actions : bloque la PR si coverage des lignes modifiées < 95%.

Configuration Codecov (`codecov.yml`) :

```yaml
coverage:
  status:
    project:
      default:
        target: 80%       # global, indulgent au début
        threshold: 1%
    patch:
      default:
        target: 95%       # nouveau code = strict
        threshold: 0%
```

**Upgrade path SonarCloud** : si en P2/P3 on veut le vrai SonarQube avec son dashboard, hot spots de sécurité, et règles plus poussées :
- SonarCloud Pro : 10€/mois pour 1 dev privé, 100K LOC
- ou SonarQube Community self-hosted : gratuit, requiert Docker + 4GB RAM sur serveur
- Migration : ajouter `sonar-project.properties` + action `SonarSource/sonarcloud-github-action`. La couverture Codecov reste compatible.

**Pas de gate flaky** : si un test E2E flake, on le marque `test.fixme()` avec issue ouverte, on n'ignore pas le gate.

---

## Niveau 4 — Review subagent entre tasks (manuel intelligent)

Après chaque task implémentée par le subagent dev, un subagent reviewer (`code-reviewer` ou `general-purpose` selon disponibilité) vérifie :

### Checklist review

1. **Conformité au plan** — fichiers créés au bon endroit, signatures conformes
2. **DRY** — pas de duplication évidente, helpers partagés extraits si pattern répété 2x+
3. **YAGNI** — pas de code spéculatif, pas d'abstraction prématurée
4. **Sécurité critique** :
   - Toute nouvelle table a RLS active + policies définies
   - Aucun secret hardcodé (clés API, mots de passe, tokens)
   - Validation Zod aux frontières (input utilisateur, payload API externe)
   - Pas d'exécution arbitraire (`eval`, `Function`, `dangerouslySetInnerHTML` sans assainissement)
5. **Tests pertinents** :
   - Couvrent au moins le happy path + 1 cas d'erreur + 1 cas limite
   - Pas de `expect(true).toBe(true)` ou tests vides
6. **Pas de régression sémantique** — relire le diff dans le contexte des fichiers existants
7. **Hygiène** — pas de `console.log`, `// TODO` orphelin, import inutilisé, code commenté
8. **Lisibilité** — noms explicites, fonctions < 50 lignes, nesting < 4 niveaux

### Output reviewer

Format de retour structuré :

```
STATUS: APPROVED | NEEDS_CHANGES

Findings (par ordre de criticité):
- [CRITICAL] <ce qui DOIT être corrigé avant merge>
- [MAJOR] <à corriger avant de passer à la task suivante>
- [MINOR] <améliorations recommandées, non bloquantes>
- [NIT] <préférences, non bloquantes>
```

Critères pour APPROVED : 0 CRITICAL, 0 MAJOR. MINOR/NIT acceptés mais loggués.

---

## Niveau 5 — Definition of Done par EPIC

Avant de marquer un EPIC comme livré :

- [ ] Tous critères d'acceptation du spec validés (cocher 1 à 1)
- [ ] Manual smoke test passé (sur device réel pour EPICs UI)
- [ ] Documentation à jour (README, ENV vars, CHANGELOG si applicable)
- [ ] Pas de régression sur EPICs précédents (re-run E2E complets)
- [ ] Migration DB testée sur DB fraîche (rollback non requis pour MVP mais migration idempotente où possible)
- [ ] Lighthouse PWA/A11y/Perf maintenus sur pages livrées
- [ ] Sentry n'a pas reçu d'erreur critique pendant la phase de test
- [ ] Coverage global ne régresse pas

---

## Déploiement des migrations Supabase (EPIC E17)

Les migrations `supabase/migrations/*.sql` sont appliquées **automatiquement** par le
workflow `.github/workflows/supabase-migrations.yml` à chaque merge sur `main` touchant
`supabase/migrations/**`. Plus de `db push` manuel dans le dashboard.

- **Mécanisme** : `supabase link --project-ref peiyrqplymdlmlpsbqzu` puis `supabase db push`
  (idempotent — seules les migrations absentes de `supabase_migrations.schema_migrations`
  sont rejouées). `concurrency` empêche deux applications simultanées.
- **Mode** : auto-apply, sans approbation manuelle. Le DDL va **directement en prod** au
  merge (pas de staging sur ce projet).
- **Secrets CI requis** : `SUPABASE_ACCESS_TOKEN` (Personal Access Token du compte) et
  `SUPABASE_DB_PASSWORD` (mot de passe DB du projet).

### Contrat de migration — expand/contract (backward-compatible)

Le job migration et le deploy Vercel se déclenchent **en parallèle** sur le même merge.
Le nouveau code front/worker peut donc tourner *avant* que la migration soit appliquée,
et inversement. Pour éviter toute fenêtre cassée, toute migration doit être **additive
d'abord** :

- une migration n'ajoute que des objets (table, colonne, index) — jamais un `DROP` /
  `RENAME` d'une colonne encore lue par le code en place ;
- une suppression de colonne se fait **une version après** le déploiement du code qui ne
  la lit plus (étape « contract » dans un merge ultérieur) ;
- privilégier `IF NOT EXISTS` / `CREATE OR REPLACE` pour l'idempotence.

Cette règle est rappelée dans le template de PR (`.github/pull_request_template.md`).

---

## Outils & coût récap

| Outil | Coût | Niveau |
|---|---|---|
| husky + lint-staged | gratuit | N1 |
| Prettier | gratuit | N1 |
| ESLint + plugins (sonarjs, unicorn, tailwindcss) | gratuit | N1, N3 |
| gitleaks | gratuit | N1, N3 |
| commitlint + Conventional Commits | gratuit | N1 |
| Vitest + coverage v8 | gratuit | N2, N3 |
| Playwright | gratuit | N2, N3 |
| GitHub Actions | gratuit (2000 min/mois sur free tier perso) | N3 |
| Codecov | gratuit ≤ 5 contributeurs privés | N3 |
| Lighthouse CI | gratuit | N3 |
| Supabase CLI | gratuit | N3 |
| **Total** | **0€/mois** | — |
| (Optionnel) SonarCloud Pro | 10€/mois | N3 upgrade |

---

## Exemptions et exceptions

Tout skip de gate doit être justifié dans le code :

```ts
// eslint-disable-next-line @typescript-eslint/no-explicit-any -- payload externe Garmin a un schéma trop volatile, validé runtime via Zod plus bas
const raw = data as any
```

Les exemptions globales (désactivation d'une règle pour tout le projet) doivent passer par PR avec discussion.

---

## Versions et mise à jour

Ce document est versionné dans git. Modifications via PR. Les seuils (95%, 80%, etc.) peuvent être ajustés après le premier mois de feedback réel.
