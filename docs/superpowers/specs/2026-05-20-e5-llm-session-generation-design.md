# E5 — LLM Session Generation — Design

**Date** : 2026-05-20
**Statut** : Validated (brainstorm with owner, 6 design questions answered)
**EPIC** : E5 — Génération séances par LLM
**Dépendances entrantes** : E4 (Banister planner) ✅ — produit `planned_sessions` (sport+type+TSS+durée+phase) ; E3 ✅ — `athlete_profiles` + `race_goals`
**Dépendances sortantes** : E6 (briefing quotidien + ajustement HRV) consommera `planned_sessions.workout` ; E7 dashboard ✅ déjà mergé peut afficher les structures dès qu'elles existent
**Effort estimé** : 2-3 jours

---

## 1. Objectif

Transformer chaque `planned_session` produite par E4 (sport, type, durée cible, TSS cible, phase) en une **structure de séance utilisable** : warmup / main intervals / cooldown avec cibles physiologiques en chiffres absolus (allure, FC, watts) calibrées sur le profil athlète.

**Pourquoi maintenant** : sans description concrète, un "endurance run 60min @75 TSS" reste un nombre. L'utilisateur a besoin de voir "Échauffement 10min Z1 → 40min Z2 @ 145-155 bpm → 10min Z1" pour exécuter sa séance sans interpréter Banister.

---

## 2. Critères d'acceptation

- Quand l'utilisateur ouvre `/today` ou `/calendar`, les séances pour J+0 à J+7 ont leur champ `workout jsonb` rempli (ou en cours de génération asynchrone, fallback "génération en cours").
- Le champ `workout` est un JSON validé par schema Pydantic côté worker : `{ warmup, main[], cooldown, summary_md }`.
- Chaque structure est calibrée sur le profil athlète : si `athlete_profiles.fc_max_bpm` connu, les cibles sont en bpm absolus ; sinon en zones Z1-Z5. Pareil pour FTP (vélo) et VMA (course).
- La spécificité course est respectée : un long run en build phase pour un trail (`race_context.total_elevation_gain_m > 500`) inclut du dénivelé ; un long run sur route reste plat.
- Le templating Python produit un texte FR markdown lisible depuis le JSON (pas de second call LLM).
- L'utilisateur peut **régénérer** une séance via un bouton UI (endpoint dédié).
- Si l'appel LLM échoue, `workout` reste `null`, un `error_id` est loggé, l'UI affiche "Structure indisponible" + bouton "Réessayer".

---

## 3. Choix structurants (issus du brainstorm)

| Sujet | Choix retenu | Alternatives écartées |
|---|---|---|
| Format LLM | **JSON structuré uniquement** (texte FR généré localement par template Python) | "Texte + JSON" (2× tokens output, divergence possible) ; "Texte libre seul" (pas exploitable par UI riche) |
| Provider | **OpenAI GPT-4o-mini** ($0.15/M in, $0.60/M out, structured outputs natifs) | Claude Haiku 4.5 (~6× plus cher) ; Ollama self-hosted (qualité inférieure sur JSON complexe) |
| Timing | **Hybride++** : génération à l'ouverture de `/today` ou `/calendar`, fenêtre J+0 à J+7 | Batch à la création du plan (gaspille tokens si user inactif) ; Cron quotidien (idem) ; Lazy 100% on-demand (latence visible) |
| Contexte LLM | **Minimal** : sport+type+TSS+durée+phase + athlete metrics + race_context (3 champs : discipline, total D+, weeks_to_race) | Full race info (legs détaillées, nom, lieu, target_time → bruit) ; Génétique sans race_context (perd la spécificité terrain) |
| Personnalisation | **Hybride** : chiffres absolus (bpm, watts, allure km/h) si profil complet, sinon zones Z1-Z5 | Always absolus (impossible si Garmin pas encore sync) ; Always Z1-Z5 (moins actionnable) |
| Stockage | **Colonne JSONB `workout`** sur `planned_sessions` | Table dédiée `workout_descriptions` (over-engineered pour MVP, versioning pas nécessaire) |
| Régénération | **Endpoint user-triggered** `POST /coach/regenerate-session/{id}` | Auto-retry sur erreur (risque de spam OpenAI) ; Non régénérable (UX bloquante si LLM hallucine) |

---

## 4. Architecture

```
[Vercel /today RSC page]
  │
  │ (ouvre /today)
  ▼
[Server Action: ensureGeneratedSessions(days=7)]
  │
  │ POST /coach/ensure-sessions?days=7  (worker shared-token)
  ▼
[Worker FastAPI]
  │
  ├── garmin_sync.coach.sessions.ensure_sessions(user_id, until_date)
  │     │
  │     ├── 1. fetch planned_sessions WHERE user_id AND date BETWEEN today AND until_date AND workout IS NULL
  │     ├── 2. fetch athlete_profile (FC max, FTP, VMA, sports_strengths)
  │     ├── 3. fetch active race_goal (discipline, total_elevation_gain_m, race_date)
  │     ├── 4. for each session: build prompt + call OpenAI structured output
  │     ├── 5. validate response with Pydantic Workout schema
  │     ├── 6. upsert planned_sessions.workout
  │     └── 7. (frontend) re-fetch + display
  │
  └── garmin_sync.coach.templates.{sport}_{type}_to_markdown(workout, athlete) → FR markdown text
        (called by the RSC dashboard when rendering each session — runs in-process Vercel, NOT in worker)
```

**Note** : le templating markdown vit côté **frontend** (TypeScript `lib/coach/templates.ts`) car il est appelé à chaque render de la page dashboard, donc faire un call worker pour ça ajouterait latence pour zéro valeur. Le worker ne stocke que la structure JSON.

---

## 5. Modèle de données

### Migration `20260522000000_e5_session_workout.sql`

```sql
alter table public.planned_sessions
  add column if not exists workout jsonb,
  add column if not exists workout_generated_at timestamptz;

create index if not exists planned_sessions_workout_pending_idx
  on public.planned_sessions (user_id, date)
  where workout is null;
```

### Workout JSON schema (Pydantic)

```python
class IntervalTarget(BaseModel):
    """Physiological target for an interval block."""
    label: Literal["Z1", "Z2", "Z3", "Z4", "Z5"]
    bpm_low: int | None         # null if FC max unknown
    bpm_high: int | None
    watts_low: int | None       # null if FTP unknown OR sport != bike
    watts_high: int | None
    pace_low_kmh: float | None  # null if VMA unknown OR sport != run
    pace_high_kmh: float | None
    rpe: Literal[1,2,3,4,5,6,7,8,9,10]  # subjective effort fallback

class IntervalBlock(BaseModel):
    duration_s: int
    target: IntervalTarget
    notes: str | None  # short coach cue (FR), e.g. "respiration profonde"

class IntervalSet(BaseModel):
    """Repeated block (intervals/threshold sessions)."""
    reps: int = Field(ge=1, le=20)
    work: IntervalBlock
    rest: IntervalBlock

class Workout(BaseModel):
    warmup: IntervalBlock
    main: list[IntervalBlock | IntervalSet]
    cooldown: IntervalBlock
    summary_md: str  # short coach summary (1-2 sentences, FR)
    technical_focus: str | None  # optional FR, e.g. "Travail du virage / poussée"
```

**Total duration check** : sum(warmup + main + cooldown) doit être dans ±10% de `target_duration_s` (validation post-LLM).

---

## 6. Prompt LLM (OpenAI GPT-4o-mini)

### System prompt (mis en cache via prompt caching côté OpenAI)

```
Tu es un coach triathlon expert. Tu produis des séances d'entraînement structurées
au format JSON strict suivant le schema fourni. Tu adaptes les cibles physiologiques
au profil de l'athlète. Tu réponds uniquement en JSON valide, sans aucun texte
en dehors du schema.

Règles :
- Échauffement : 10-15min, progression Z1→Z2.
- Retour calme : 8-12min, Z1.
- Séance "long" : un seul gros bloc continu (pas d'intervalles).
- Séance "intervals" : des sets répétés (work + rest).
- Séance "threshold" : 1-2 sets longs (≥8min work, 2-3min rest).
- Séance "recovery" : Z1 seulement, durée courte.
- Séance "endurance" : un seul bloc Z2-Z3 continu.
- summary_md : 1-2 phrases FR conseil du jour, motivant mais bref.
- technical_focus : 1 phrase FR sur l'aspect technique spécifique au sport.
```

### User prompt (par séance)

```
Session : {sport} {session_type} en phase {phase}, durée cible {minutes}min, TSS {tss}.

Athlète :
- FC max : {fc_max_bpm} bpm  (ou "non connue")
- FTP : {ftp_watts} W  (si vélo, sinon omettre)
- VMA : {vma_kmh} km/h  (si course, sinon omettre)
- Niveau (1-5) : swim={swim_str}, bike={bike_str}, run={run_str}

Course objectif (dans {weeks_to_race} semaines) :
- Discipline : {race_discipline}
- Dénivelé total : {race_d_plus_m}m
```

### Sortie attendue (structured output via OpenAI `response_format: json_schema`)

Le schema Pydantic est sérialisé en JSON schema OpenAI ; le modèle est forcé d'émettre uniquement du JSON valide. Pas besoin de regex parsing.

---

## 7. Frontend templating (Markdown FR)

Module : `lib/coach/session-templates.ts`

```ts
export function workoutToMarkdown(workout: Workout, sport: Sport, athlete: Athlete): string
```

Stratégie :
- 21 templates indexés par `${sport}_${session_type}` (swim_endurance, bike_threshold, run_long, etc.).
- Chaque template prend le JSON et émet du markdown FR avec mise en forme cohérente :
  - Titre séance : `## {emoji_sport} {sport_label} {type_label} — {duration}min`
  - Block warmup : `### Échauffement\n- {duration}min @ {target}` (target = bpm si dispo, sinon Z label)
  - Block main : `### Corps de séance` avec sous-listes par set
  - Block cooldown : `### Retour calme\n- {duration}min @ {target}`
  - Footer : `*{summary_md}*`
- Les conseils techniques par sport (technical_focus) sont alimentés par le LLM, pas hardcodés. Mais le **format** du markdown est imposé par le template (cohérence visuelle).

**Note pour l'implémentation** : pendant la rédaction du plan, on consultera un agent expert sport pour valider la terminologie FR utilisée par les templates (ex: "fartlek" vs "jeu d'allure", "sweet spot" vs "tempo moyen").

---

## 8. Endpoints worker

### `POST /coach/ensure-sessions`

Body : `{ "until_date": "2026-08-15" }` (optionnel ; défaut J+7)
Auth : Bearer JWT user (Supabase)

Réponse :
```json
{
  "status": "ok",
  "generated_count": 5,
  "failed_count": 0,
  "skipped_count": 2
}
```

Comportement :
- Récupère les `planned_sessions` du user dans [today, until_date] dont `workout IS NULL`.
- Boucle séquentielle (pas parallèle, OpenAI rate-limited free tier 3 req/s).
- Pour chaque succès, upsert `workout` + `workout_generated_at`.
- Pour chaque échec : log avec error_id, n'écrase pas la ligne, continue.

### `POST /coach/regenerate-session/{session_id}`

Auth : Bearer JWT user.

Réponse :
```json
{ "status": "ok", "workout": {...} }
```

Comportement : récupère la session (vérifie user_id matche), force la regénération, upsert.

---

## 9. Gestion des erreurs

| Cause | Comportement |
|---|---|
| OpenAI 429 (rate limit) | Sleep 5s, retry 1x. Si échec, return `{status: "rate_limited", error_id}` ; UI affiche un message. |
| OpenAI JSON invalide (rare avec structured outputs) | Log error_id, return `{status: "invalid_response", error_id}` ; workout reste null. |
| Duration sum hors ±10% du target | Log warning + accepte quand même (validation soft). |
| OpenAI down | error_id, workout=null, UI bouton "Réessayer". |
| Session déjà générée (workout NOT NULL) | Skip (sauf si endpoint /regenerate). |

Toutes les erreurs loggent via le même pattern `error_id` que E2/E4 (greppable dans `docker logs garmin-sync`).

---

## 10. Testing

### Worker (pytest)

- `tests/coach/test_sessions.py` :
  - mock OpenAI client (`pytest-mock`)
  - test ensure_sessions filtre bien les `workout IS NULL`
  - test prompt builder produit le bon format pour chaque sport×type×profil-complet/profil-vide
  - test schema Pydantic rejette payload invalide
  - test duration sum check
- `tests/test_main.py` : tests d'endpoint /coach/ensure-sessions + /coach/regenerate-session

### Frontend (vitest)

- `tests/unit/lib/coach/session-templates.test.ts` : 21 sport×type, vérifier le markdown généré pour chaque combo
- `tests/unit/actions/ensure-sessions.test.ts` : Server Action mock worker, vérifie le call

### Integration

- e2e Playwright : ouvrir `/today` (avec planned_sessions seedées), vérifier que les structures apparaissent ou que "Génération en cours" s'affiche.

**Coverage cibles** : ≥90% lines sur worker `coach/sessions.py` et `lib/coach/session-templates.ts`.

---

## 11. Coût opérationnel

| Plan | Séances | Tokens in (500/sess) | Tokens out (200/sess) | Coût |
|---|---|---|---|---|
| Plan 12 sem complet | 84 | 42 000 | 16 800 | $0.0164 |
| Hebdo (génération J+0..J+7) | 7 | 3 500 | 1 400 | $0.0014 |
| Régen 1 séance | 1 | 500 | 200 | $0.0002 |

Pour 5-10 amis beta sur 12 sem : ~$0.10-0.20 total. Aucun risque budget.

---

## 12. Variables d'environnement

Ajout côté worker `.env` + Docker compose :

```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4o-mini  # configurable pour A/B
OPENAI_TIMEOUT_S=30
```

`OPENAI_API_KEY` géré comme secret. Pas exposé côté frontend.

---

## 13. Migrations + déploiement

1. SQL migration `20260522000000_e5_session_workout.sql` (colonne JSONB)
2. Worker version bumpée (0.2.0) — nouvelle dépendance `openai` (Pydantic-compatible)
3. Docker image rebuild + push tellebma/garmin-sync:latest
4. UNRAID `docker compose pull && docker compose up -d garmin-sync`
5. Vercel auto-deploy (Server Actions + templates)

Pas de breaking change : les `planned_sessions` existantes ont juste `workout=null`, l'UI sait l'afficher.

---

## 14. Hors scope (renvoyé à E6+)

- **Adaptation HRV / status du jour** : si l'user a un HRV bas, faire passer une séance "threshold" en "recovery". → E6 (briefing quotidien).
- **Feedback sur la séance** : "comment était la séance ?" + rating + ajustement futur. → E6 ou post-MVP.
- **Workout sync vers Garmin Connect** (FIT file export). → Post-MVP, complexe (format FIT propriétaire).
- **Multi-langue** (EN, ES). → Post-MVP.
- **Personnalisation prompt par utilisateur** (ex: "je préfère les côtes"). → Post-MVP.
