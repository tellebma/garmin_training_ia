# E-Q — SonarQube Quality Gate & 90 % Coverage — Design Spec

> **EPIC transversal** (hors série E1→E9). Cousin de E1b (Quality Gates Setup).
> S'exécute en parallèle de E7 (dashboard) avant la beta privée (E9).

**Auteur :** Maxime BELLET
**Date :** 2026-05-19
**Statut :** Validé (owner request)
**Plan d'implémentation :** [`../plans/2026-05-19-eq-sonar-quality-gate.md`](../plans/2026-05-19-eq-sonar-quality-gate.md)

---

## 1. Contexte

SonarQube self-hosted (`https://sonarqube.tellebma.fr`) scanne le projet
`garmin_training_ia` à chaque push/PR depuis le job `sonarqube` de
`.github/workflows/ci.yml`. Mais :

1. **La Quality Gate n'est jamais vérifiée par la CI.** Le job exécute
   `SonarSource/sonarqube-scan-action@v4` qui pousse le scan, puis **se termine
   en succès**, indépendamment du statut de la gate. Conséquence : un PR peut
   merger sur `main` alors que la gate est rouge.
2. **La coverage Python du worker n'arrive jamais dans SonarQube.** Le
   `sonar-project.properties` déclare `sonar.python.coverage.reportPaths=worker/coverage/lcov.info`,
   mais le job `sonarqube` ne télécharge que l'artefact `coverage-lcov`
   (frontend Vitest) et pas `worker-coverage-lcov` (worker pytest, généré dans
   `.github/workflows/worker-ci.yml`). Résultat : tout le code worker (~3 000
   ncloc bien testés) est compté comme non-couvert.
3. **La couverture frontend reste très basse.** Snapshot SonarQube au
   2026-05-19 :
   - Coverage global : **8.4 %** (objectif owner : **90 %**)
   - New code coverage : **9.7 %** (gate threshold 80 %, ECHEC)
   - Lines to cover : 1984 / Uncovered : 1814
4. **23 nouvelles violations bloquent la gate** (sur 28 totales, toutes
   `CODE_SMELL`, aucun BUG ni VULNERABILITY) :
   - 13 × `typescript:S6772` — espaces ambigus avant `<span>` dans les
     formulaires onboarding/profile
   - 5 × `python:S8410` — FastAPI : utiliser `Annotated[T, Depends(...)]`
   - 3 × `typescript:S6754` — `useState` non déstructuré
   - 3 × `python:S1192` — strings dupliquées
   - 2 × `typescript:S7735`
   - 1 × `python:S125` — code commenté (`worker/src/garmin_sync/coach/banister.py:28`)
   - 1 × `python:S3776` — cognitive complexity 23 > 15
     (`worker/src/garmin_sync/coach/planner.py:85`)
5. **7.89 % de duplication sur new code** (gate threshold 3 %, ECHEC). Les
   formulaires `onboarding/_components/step-*-form.tsx` et `profile/_components/*-edit-form.tsx`
   répètent les mêmes blocs `<Label> + <Input> + <span class="text-destructive">`.

## 2. Objectifs

| # | Objectif | Mesure |
|---|----------|--------|
| O1 | Bloquer les merges sur main quand la gate Sonar est rouge | Job `sonarqube` échoue si `alert_status=ERROR` |
| O2 | Inclure la coverage worker dans le scan Sonar | Coverage totale > 50 % dès le 1er run après E-Q |
| O3 | Atteindre **90 %** de coverage globale (frontend + worker) | Métrique Sonar `coverage` ≥ 90 % en fin d'EPIC |
| O4 | Zéro code smell ouvert ≥ MAJOR | Issues Sonar : 0 BLOCKER, 0 CRITICAL, 0 MAJOR open |
| O5 | Duplication new code < 3 % | Métrique Sonar `new_duplicated_lines_density` < 3 % |
| O6 | Documenter la gate dans `QUALITY_GATES.md` + `CLAUDE.md` | Section dédiée |

## 3. Non-objectifs

- Migrer vers SonarCloud (hosting reste tellebma.fr).
- Activer des règles Sonar custom : on garde le Sonar way profile.
- Ajouter Codecov en plus de Sonar (Sonar gère le diff coverage déjà).
- Refactorer le worker pour réduire ncloc (séparé de cet EPIC).

## 4. Architecture cible

### 4.1 Flux CI mis à jour

```
                            push / PR
                                │
                  ┌─────────────┼─────────────┐
                  ▼             ▼             ▼
              (frontend)     (worker)     (autres jobs)
            test-unit + cov  test + cov   lint, typecheck,
                  │             │         build, audit…
                  ▼             ▼
            artifact:        artifact:
            coverage-lcov    worker-coverage-lcov
                  └─────────────┬─────────────┘
                                ▼
                         sonarqube job
                  - download coverage-lcov → coverage/
                  - download worker-coverage-lcov → worker/coverage/
                  - sonarqube-scan-action (push)
                  - sonarqube-quality-gate-action (BLOCKING)
                                │
                                ▼
                     CI green ⇔ Gate PASSED
```

### 4.2 Quality Gate utilisé

On garde la gate **Sonar way** (par défaut, déjà associée au projet, owner
non-admin sur l'instance) avec ses conditions par défaut on *new code* :

- Coverage on new code ≥ 80 %
- Duplicated lines on new code < 3 %
- Maintainability rating on new code = A
- Reliability rating on new code = A
- Security rating on new code = A
- Security hotspots reviewed on new code = 100 %
- New violations = 0

Notre **objectif owner de 90 %** s'applique au **coverage global** (pas new
code). On enforce ça via une threshold Vitest + un check post-scan custom
dans le job CI (script qui appelle `api/measures/component` et vérifie
`coverage ≥ 90`).

### 4.3 Coverage budgets

| Périmètre | Provider | Threshold actuel | Cible E-Q |
|-----------|----------|------------------|-----------|
| Frontend (`app/`, `lib/`, `components/`) | Vitest v8 | `coverage.thresholds.100=false` (CI) | lines 90, functions 90, branches 85, statements 90 |
| Worker (`worker/src/garmin_sync/`) | pytest-cov | (aucun) | 90 % lines (pytest `--cov-fail-under=90`) |
| Global Sonar | LCOV merge | (non vérifié) | `coverage ≥ 90` post-scan |

### 4.4 Stack technique

- **GitHub Actions** : ajout job `worker-coverage` réutilisable, modification
  job `sonarqube` (download 2 artefacts, ajout step quality-gate).
- **`SonarSource/sonarqube-quality-gate-action@v1.2.0`** : bloque la CI si la
  gate échoue (10 min timeout configurable).
- **Vitest coverage v8** : seuils 90 % lines / 85 % branches.
- **pytest-cov** : `--cov-fail-under=90`.
- **`sonar-project.properties`** : `sonar.coverageReportPaths` séparés par
  langue, exclusions affinées.

## 5. Plan d'attaque (résumé — détail dans le plan)

L'EPIC se découpe en **3 phases** :

### Phase 1 — Infrastructure CI (Tasks 1–4)

Sans toucher au code applicatif :
1. Fusionner les artefacts coverage frontend + worker dans le job Sonar
2. Ajouter `sonarqube-quality-gate-action` (BLOCKING)
3. Ajouter un step post-scan qui vérifie `coverage ≥ 90` global (objectif owner)
4. Mettre à jour `sonar-project.properties` (exclusions + coverage paths)

**Effet :** la gate redevient enforce-able ; la coverage worker remonte dans Sonar.
Estimation : coverage post-Phase 1 → ~50-60 % (effet du worker bien testé).

### Phase 2 — Fix des 28 code smells (Tasks 5–8)

5. Auto-fix des 13 `S6772` + 3 `S6754` + 2 `S7735` (formulaires React) via
   `pnpm lint:fix` puis revue manuelle
6. Refactor des 5 `S8410` dans `worker/src/garmin_sync/main.py` (Annotated)
7. Refactor des 3 `S1192` + 1 `S125` + 1 `S3776` (worker, planner)
8. Extraction d'un composant partagé `<FormField>` pour les formulaires
   onboarding/profile → fait baisser la duplication new code sous 3 %

**Effet :** gate gate Sonar passe à vert sur new code (violations + duplication).

### Phase 3 — Couverture 90 % (Tasks 9–14)

Priorité par ROI (lignes non-couvertes / coût test) :

9. Tests `lib/worker.ts` (HTTP client → Server Action) — mockable
10. Tests `lib/supabase/` (server/middleware clients) — mockable
11. Tests Server Actions restantes (`app/actions/garmin-auth.ts`)
12. Tests composants présentationnels (`components/auth/`, `components/garmin/`,
    `components/nav/`) via React Testing Library
13. Tests des form handlers onboarding (`step-*-form.tsx`) — sans monter le
    composant, juste les handlers extraits
14. Activer les seuils Vitest 90 % et `--cov-fail-under=90` côté worker

**Effet :** coverage global Sonar atteint 90 %, seuils enforced.

## 6. Risques

| Risque | Mitigation |
|--------|------------|
| `sonarqube-quality-gate-action` timeout sur instance self-hosted lente | Augmenter `pollingTimeoutSec` à 600s, vérifier dispo Sonar avant. |
| Le scan échoue si `worker/coverage/lcov.info` absent (cas worker-ci skip via `paths`) | Job sonar conditionnel sur présence des deux artefacts + `continue-on-error` sur le download worker. |
| Tests UI flaky (RTL + Next.js Server Components) | Tester via testing-library/react avec mock complet `next/navigation` ; éviter de tester les RSC, tester les Client Components et les actions séparément. |
| Atteindre 90 % sur les `app/(app)/<page>/page.tsx` (RSC qui font 1 await + JSX) est coûteux pour peu de valeur | Exclure les `page.tsx` simples de la coverage Sonar via `sonar.coverage.exclusions` documenté. |
| Refactor du planner (`S3776`) risque de casser le moteur Banister | Refactor 100 % couvert par les tests existants `worker/tests/coach/test_planner.py` — verrouiller avant. |

## 7. Definition of Done EPIC

- [ ] CI job `sonarqube` échoue quand la gate Sonar est ERROR (vérifié via PR cassant la gate volontairement)
- [ ] Coverage worker visible dans le dashboard Sonar (> 80 % sur `worker/src/**`)
- [ ] Métrique Sonar `coverage` ≥ 90 %
- [ ] Métrique Sonar `new_duplicated_lines_density` < 3 %
- [ ] 0 BLOCKER, 0 CRITICAL, 0 MAJOR ouvert sur Sonar
- [ ] Quality Gate Sonar = PASSED sur `main`
- [ ] `QUALITY_GATES.md` documente la gate Sonar et le seuil 90 %
- [ ] `CLAUDE.md` section "Statut actuel" mise à jour avec ligne E-Q ✅

## 8. Suivi des métriques

Avant de fermer l'EPIC, capturer (manuellement, ou via cron Wiki-Brain) :

```bash
curl -sS -u "${SONAR_TOKEN_TELLEBMA}:" \
  "https://sonarqube.tellebma.fr/api/measures/component?component=garmin_training_ia&metricKeys=alert_status,coverage,duplicated_lines_density,bugs,vulnerabilities,code_smells,security_hotspots"
```

Snapshot 2026-05-19 (baseline) :

```
alert_status=ERROR
coverage=8.4
duplicated_lines_density=8.1
code_smells=28
bugs=0
vulnerabilities=0
security_hotspots=0
```

Target post E-Q :

```
alert_status=OK
coverage≥90
duplicated_lines_density<3
code_smells=0  (sur MAJOR+)
bugs=0
vulnerabilities=0
security_hotspots=0
```
