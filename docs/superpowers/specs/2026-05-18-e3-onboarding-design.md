# E3 — Profile & Onboarding — Design

**Date** : 2026-05-18
**Statut** : Validated (brainstorm + 3-section design review with owner)
**EPIC parent** : E3 — Profile & Onboarding (CLAUDE.md)
**Dépendances entrantes** : E1 (auth) ✅, E2 (Garmin sync worker) ✅
**Dépendances sortantes** : E4 (planning Banister) consomme `athlete_profiles` + `race_goals`
**Effort estimé** : 3 jours

---

## 1. Objectif

Permettre à un user fraîchement inscrit (E1) de fournir, en moins de 5 minutes, les informations indispensables pour générer plus tard un plan d'entraînement personnalisé (E4) :

- identité minimale (prénom, date de naissance, sexe, ville),
- course-cible (date, distance, temps cible optionnel),
- niveau de performance (FTP / VMA / FCmax),
- disponibilité hebdomadaire (jours + heures + forces par sport),
- consentement explicite au traitement des données.

Le système doit aussi permettre à l'user de **modifier** ces informations à tout moment via la page `/profile`.

## 2. Critères d'acceptation

- Onboarding complétable en < 5 minutes par un user qui a déjà toutes ses valeurs.
- **Étapes obligatoires** : Perso (au moins prénom + dob + sexe + consent) et Course (au moins date + distance) — sans ça E4 ne peut pas générer de plan.
- **Étapes optionnelles** : Perf (FTP/VMA/FCmax, tous nullable) et Dispo (defaults raisonnables si vides : 5 jours / 6h / niveaux 3/3/3).
- À l'étape Performance, le worker tente de pré-remplir FTP / VMA / FCmax depuis Garmin Connect. Si ça échoue, l'user remplit manuellement ou laisse vide.
- Un user dont `onboarding_completed_at IS NULL` est redirigé vers `/onboarding` à chaque visite d'une route protégée.
- Une fois `onboarding_completed_at` rempli, la page `/profile` affiche les valeurs en lecture + permet édition section par section.
- Multi-tenant : chaque user ne voit / modifie que ses propres données (RLS).

## 3. Choix structurants (issus du brainstorm)

| Décision | Choix retenu | Alternatives écartées |
|---|---|---|
| Modèle course | Table `race_goals` séparée (1→N, `is_primary` partial unique) | Champs dans `athlete_profiles` (mono-course) ; report en E4 |
| FTP / VMA / FCmax inconnus | Auto-fetch depuis Garmin Connect + fallback champs libres | Champs libres seulement ; questionnaire d'estimation RPE |
| Édition post-onboarding | `/profile` éditable inline section par section | Re-jouer le wizard pré-rempli ; mix |
| Archi wizard | Hybrid : page unique `/onboarding` avec tabs + save par étape | Multi-route `/onboarding/[step]` ; single-page save final unique |

YAGNI (volontairement hors scope E3, à revoir post-MVP) :

- Estimateur RPE de FTP/VMA si Garmin n'a rien remonté → E4 gérera les fallbacks (FCmax = 220 − age si null, refus de plan si trop incomplet).
- UI avancée multi-courses simultanées (`is_primary` swap fluide). MVP : 1 active + bouton "Ajouter".
- i18n (FR uniquement).
- Avatar / photo profil.
- Préférences notifications (couvertes par E6 / E9).
- Validation âge minimum / RGPD enfant.

## 4. Data model

### 4.1 Nouvelle table `race_goals`

```sql
create table public.race_goals (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  race_date date not null,
  race_distance text not null
    check (race_distance in ('sprint','olympique','half_ironman','ironman','autre')),
  name text,                                  -- ex: "Ironman 70.3 Nice"
  location text,                              -- ville/pays (utilisé en E8 météo)
  target_time_seconds integer
    check (target_time_seconds is null or target_time_seconds between 600 and 86400),
  is_primary boolean not null default true,   -- "course A" vs B/C secondaires
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index race_goals_user_primary_idx
  on race_goals (user_id, is_primary) where is_primary;
create unique index race_goals_one_primary_per_user
  on race_goals (user_id) where is_primary;   -- au plus 1 active par user

alter table public.race_goals enable row level security;

create policy "users read own race_goals"   on race_goals for select
  using (auth.uid() = user_id);
create policy "users insert own race_goals" on race_goals for insert
  with check (auth.uid() = user_id);
create policy "users update own race_goals" on race_goals for update
  using (auth.uid() = user_id);
create policy "users delete own race_goals" on race_goals for delete
  using (auth.uid() = user_id);

create trigger touch_race_goals_updated_at before update on race_goals
  for each row execute function public.touch_updated_at();
```

### 4.2 Alter `athlete_profiles`

```sql
alter table public.athlete_profiles
  add column if not exists hours_per_week integer
    check (hours_per_week is null or hours_per_week between 1 and 30),
  add column if not exists garmin_synced_at timestamptz;

comment on column public.athlete_profiles.hours_per_week is
  'Heures d''entraînement disponibles par semaine (1-30).';
comment on column public.athlete_profiles.garmin_synced_at is
  'Last successful auto-fetch from Garmin user-settings (FTP/VO2max/FCmax).';
```

Champs déjà présents réutilisés sans modification : `first_name`, `dob`, `sex` (`M`/`F`/`X`), `city`, `country`, `lat`, `lon`, `ftp_watts`, `vma_kmh`, `fc_max_bpm`, `sports_strengths` (jsonb : `{"swim":3,"bike":4,"run":2}` 1=faible…5=fort), `available_days` (jsonb : `["mon","tue","thu","sat","sun"]`), `consent_data_processing`, `consent_signed_at`, `onboarding_completed_at`.

### 4.3 Migration

Un seul fichier `supabase/migrations/20260518000000_e3_onboarding.sql` contenant les deux changements ci-dessus + commentaires d'index. La migration est idempotente (`create table if not exists`, `add column if not exists`, `create policy if not exists` quand pertinent).

## 5. Architecture frontend

### 5.1 Arborescence

```
app/(app)/
├── layout.tsx                        # MOD: redirect vers /onboarding si onboarding_completed_at IS NULL
├── onboarding/
│   ├── page.tsx                      # Server Component : load profile + race + détermine step initial
│   ├── actions.ts                    # Server Actions : saveStep1/2/3/4, finalizeOnboarding, syncGarminProfile
│   └── _components/
│       ├── onboarding-wizard.tsx     # Client : stepper UI, manage currentStep
│       ├── step-perso-form.tsx       # Zod : first_name, dob, sex, city, country, consent
│       ├── step-race-form.tsx        # Zod : race_date, race_distance, name?, location?, target_time?
│       ├── step-perf-form.tsx        # Zod : ftp_watts?, vma_kmh?, fc_max_bpm? + auto-fetch trigger
│       └── step-dispo-form.tsx       # Zod : available_days[], hours_per_week, sports_strengths{}
├── profile/
│   └── page.tsx                      # MOD: ajout 4 sections éditables inline (1 form par section)
└── profile/_components/
    ├── perso-edit-form.tsx
    ├── race-edit-form.tsx            # gère aussi création course additionnelle
    ├── perf-edit-form.tsx            # bouton "↻ Sync Garmin" qui appelle la même action que wizard step 3
    └── dispo-edit-form.tsx

lib/
└── onboarding/
    ├── schemas.ts                    # Zod schemas partagés wizard + profile-edit
    └── steps.ts                      # type Step = 'perso'|'race'|'perf'|'dispo' + helpers (next, isComplete)
```

### 5.2 Flow wizard

1. User non-onboardé visite n'importe quelle route protégée → `(app)/layout.tsx` détecte `onboarding_completed_at IS NULL` → `redirect('/onboarding')`.
2. `/onboarding/page.tsx` (Server) lit en parallèle `athlete_profiles` + `race_goals (is_primary=true)`, calcule `initialStep` = première étape non remplie (perso si first_name null, sinon race si pas de race_goal, sinon perf si ftp/vma/fcmax tous null ET garmin_synced_at null, sinon dispo). Rend `<OnboardingWizard initial={...} initialStep={...} />`.
3. Wizard client : 4 tabs visibles (Perso / Course / Perf / Dispo) avec un ✓ vert sur les étapes complètes. User remplit, clique "Suivant".
4. Server Action correspondante (`saveStepPerso`, `saveStepRace`, `saveStepPerf`, `saveStepDispo`) : Zod valide → upsert Supabase (anon client + RLS) → retourne `{ success: true, nextStep }` ou `{ success: false, errors }`.
5. À l'entrée de **l'étape Perf** : le step component appelle `syncGarminProfile()` (Server Action proxy vers le worker) **uniquement si `garmin_synced_at IS NULL`** (premier auto-fetch). Si succès → champs pré-remplis + badge "↻ Synchronisé de Garmin le DD/MM" sous chaque champ + champs éditables. Si échec → champs vides + hint "Ta montre Garmin > Performance > Statistiques". Si `garmin_synced_at` déjà set → on ne re-sync pas auto, on affiche les valeurs courantes telles quelles (l'user a éventuellement modifié manuellement entre-temps, on respecte sa saisie).
6. À la fin de **l'étape Dispo** (dernière) → submit appelle `finalizeOnboarding()` qui set `onboarding_completed_at = now()` + `consent_signed_at = now()` → redirect `/profile`.

### 5.3 Flow édition `/profile`

- Page `/profile` (Server Component) lit `athlete_profiles`, `garmin_credentials`, dernière `race_goals (is_primary=true)`, et la liste des courses secondaires.
- Render 5 cards : Garmin Connect (déjà fait — PR #8) + Perso + Course + Perf + Dispo.
- Chaque card est un client component avec deux modes : `view` (default) et `edit` (toggle via bouton "Modifier"). En `edit`, le form Zod réutilisé du wizard prend la valeur courante en `defaultValue`, save via la même Server Action que l'équivalent wizard.
- Card Course : bouton "+ Ajouter une autre course" → form inline qui crée une nouvelle ligne `race_goals` avec `is_primary = false`. Switch d'is_primary géré via un dropdown "promouvoir course principale" sur chaque card course secondaire.
- Card Perf : bouton "↻ Sync Garmin" supplémentaire qui re-appelle `syncGarminProfile()`.

## 6. Architecture worker — auto-fetch Garmin (E3.x)

### 6.1 Nouveau endpoint `POST /garmin/profile-sync`

Auth = user JWT (même flow que `/garmin/connect`).

```python
# worker/src/garmin_sync/main.py
@app.post("/garmin/profile-sync")
def garmin_profile_sync(authorization: str | None = Header(default=None)) -> dict[str, Any]:
    user_id = _require_user_jwt(authorization)
    try:
        from garmin_sync.profile_sync import sync_garmin_profile
        return sync_garmin_profile(user_id)
    except Exception as e:
        error_id = _new_error_id()
        log.exception("[%s] garmin_profile_sync crashed user=%s", error_id, user_id)
        return {"status": "unexpected_error", "error_id": error_id, "type": type(e).__name__}
```

### 6.2 Module `worker/src/garmin_sync/profile_sync.py`

```python
def sync_garmin_profile(user_id: str) -> dict[str, Any]:
    """Read Garmin user profile + max metrics, upsert subset into athlete_profiles."""
    db = get_admin_client()
    creds = ... # read garmin_credentials, decrypt
    try:
        client = login_with_tokens(serialized)
    except GarminAuthError:
        return {"status": "auth_failed"}

    try:
        user_profile = client.get_user_profile()
        max_metrics  = client.get_max_metrics(date.today().isoformat())
    except GarminConnectTooManyRequestsError:
        return {"status": "rate_limited"}
    except Exception as e:
        return {"status": "garmin_error", "type": type(e).__name__}

    row = _transform_profile(user_profile, max_metrics)
    db.table("athlete_profiles").update({
        **row,
        "garmin_synced_at": datetime.now(UTC).isoformat(),
    }).eq("user_id", user_id).execute()
    return {"status": "ok", "fetched": row}
```

### 6.3 Transformer `_transform_profile`

**Scope volontairement limité aux 3 champs de perf** — pas de `dob` ni `sex`, qui sont saisis par l'user à l'étape Perso et NE doivent JAMAIS être écrasés par Garmin (UX surprenante sinon).

```python
def _transform_profile(user_profile: dict, max_metrics: dict) -> dict[str, Any]:
    """Return only non-null perf fields. Keys with None values are EXCLUDED so
    the UPDATE never overwrites a value the user typed manually before."""
    row: dict[str, Any] = {}
    ftp = _safe_int(user_profile.get("functionalThresholdPower"))
    if ftp is not None:
        row["ftp_watts"] = ftp
    vma = _vma_from_vo2max(max_metrics.get("vo2MaxValueRunning"))
    if vma is not None:
        row["vma_kmh"] = vma
    fcmax = _safe_int(user_profile.get("userMaxHr"))
    if fcmax is not None:
        row["fc_max_bpm"] = fcmax
    return row

def _vma_from_vo2max(vo2: float | None) -> float | None:
    """VO2max (ml/kg/min) → VMA (km/h) via la formule classique VMA = VO2max / 3.5."""
    return round(vo2 / 3.5, 2) if vo2 else None
```

L'UPDATE Supabase est ensuite : `db.table("athlete_profiles").update({**row, "garmin_synced_at": now()}).eq("user_id", user_id)` — donc si `row` est vide (Garmin n'a rien remonté), seul `garmin_synced_at` est mis à jour.

Notes :

- **Quand Garmin écrase la saisie user** :
  - Au **premier auto-fetch** à l'étape Perf du wizard (seul cas où c'est implicite).
  - Sur **clic explicite** de "↻ Sync Garmin" depuis `/profile` (action volontaire de l'user).
  - Pas de re-sync automatique récurrent (un cron `/garmin/profile-sync` mensuel est listé en post-MVP, à activer plus tard avec consentement).
- L'user voit toujours **une seule valeur courante par champ** + un badge "↻ Synchronisé de Garmin le DD/MM" si applicable. Pas de double affichage user/Garmin (overhead UI et schéma pour MVP, YAGNI). L'horodatage `garmin_synced_at` rend la provenance transparente.
- Choix sportif : Garmin (FTP auto-detected sur 8 sem. de sorties power-meter, FCmax observé sur 30j, VO2max recalculé en continu) est généralement plus précis que la saisie manuelle. L'user peut overrider à tout moment via `/profile` edit, sa valeur sera respectée jusqu'au prochain "↻ Sync Garmin" volontaire.
- Pas de cooldown sur `/garmin/profile-sync` : l'endpoint ne déclenche aucune cascade auth (tokens déjà valides). Si tokens KO → retour `auth_failed` immédiat. Si Garmin 429 sur les endpoints de profil → retour `rate_limited` sans matraquage.

### 6.4 Réutilisation infra existante

- `auth.verify_supabase_jwt` (JWKS ES256) : déjà OK.
- `crypto.TokenCipher` : décryption Fernet, déjà OK.
- `garmin_client.login_with_tokens` : déjà OK.
- `supabase_client.get_admin_client` : déjà OK.

Aucune nouvelle dépendance Python.

## 7. Validation (Zod schemas partagés)

`lib/onboarding/schemas.ts` :

```ts
import { z } from 'zod'

export const personSchema = z.object({
  first_name: z.string().min(1).max(80),
  dob: z.iso.date().refine(d => new Date(d) < new Date(), 'DOB doit être passée'),
  sex: z.enum(['M', 'F', 'X']),
  city: z.string().max(120).optional(),
  country: z.string().max(80).optional(),
  consent_data_processing: z.literal(true),  // doit être coché
})

export const raceSchema = z.object({
  race_date: z.iso.date().refine(d => new Date(d) > new Date(), 'race_date doit être future'),
  race_distance: z.enum(['sprint','olympique','half_ironman','ironman','autre']),
  name: z.string().max(160).optional(),
  location: z.string().max(160).optional(),
  target_time_seconds: z.number().int().min(600).max(86400).optional(),
})

export const perfSchema = z.object({
  ftp_watts: z.number().int().min(50).max(600).optional(),
  vma_kmh: z.number().min(5).max(30).optional(),
  fc_max_bpm: z.number().int().min(100).max(230).optional(),
})

export const dispoSchema = z.object({
  // Tout optional → l'user peut skip cette étape. Defaults appliqués à la finalize.
  available_days: z.array(z.enum(['mon','tue','wed','thu','fri','sat','sun'])).optional(),
  hours_per_week: z.number().int().min(1).max(30).optional(),
  sports_strengths: z.object({
    swim: z.number().int().min(1).max(5),
    bike: z.number().int().min(1).max(5),
    run:  z.number().int().min(1).max(5),
  }).optional(),
})

// Defaults appliqués par finalizeOnboarding si user a tout laissé vide :
export const DISPO_DEFAULTS = {
  available_days: ['mon','tue','wed','thu','sat'],   // 5 jours, week-end partiel libre
  hours_per_week: 6,
  sports_strengths: { swim: 3, bike: 3, run: 3 },     // moyen partout
} as const
```

Wizard et `/profile` edit utilisent **les mêmes schemas**.

## 8. Error handling

| Source | Comportement |
|---|---|
| Zod validation fail (frontend) | Server Action retourne `{ success: false, errors }`. Form affiche les messages inline (1 par champ). |
| Supabase upsert fail (RLS, contrainte) | Server Action attrape, retourne `{ success: false, error: 'save_failed' }`. Toast "Erreur sauvegarde, réessaye". |
| Garmin profile-sync échec (auth_failed / rate_limited / garmin_error) | Ne bloque PAS le wizard. L'étape Perf affiche un alert "Garmin indisponible — remplis manuellement". `garmin_synced_at` reste null. |
| Refresh sur étape en cours | Perte des changements locaux non-sauvés (acceptable). Les étapes précédentes restent persistées. |
| User tente de skip Perso ou Course | Refusé : le wizard bloque "Suivant" tant que les champs required (Perso : prénom+dob+sex+consent ; Course : date+distance) ne sont pas valides. |
| User skip Perf ou Dispo (champs vides) | Autorisé : Zod tolère les `.optional()` sur tous les champs de Perf et Dispo. À la finalize, on remplit Dispo avec defaults raisonnables si vide. |

## 9. Tests

| Couche | Outil | Cas couverts |
|---|---|---|
| **Worker** | pytest (`worker/tests/test_profile_sync.py`) | (1) mapping correct birthDate/gender/FTP/VO2max → row Supabase ; (2) clés absentes → champs exclus, pas de crash ; (3) sex `MALE`/`FEMALE`/inconnu → `M`/`F`/None ; (4) VMA = vo2max ÷ 3.5 arrondi ; (5) `GarminConnectTooManyRequestsError` → status `rate_limited` ; (6) `GarminAuthError` → status `auth_failed` |
| **Supabase migration** | psql dry-run dans CI worker | (1) Migration s'applique sans erreur ; (2) RLS bloque cross-user select sur `race_goals` ; (3) `race_goals_one_primary_per_user` unique index empêche 2 is_primary=true |
| **Frontend unit** | Vitest | Chaque Zod schema accepte un payload valide minimal + rejette les bornes (dob future, race_date passée, FTP 49/601, vma 4.99/30.01, fc_max 99/231, sports_strengths score 0/6, available_days vide) |
| **Frontend e2e** | Playwright | 1 happy path : magic link → callback → redirect `/onboarding` → 4 étapes remplies (mock l'auto-fetch Garmin pour ne pas hit le worker) → finalize → vérif badge "Connecté" + données affichées sur `/profile` |

CI : tout passe dans le pipeline existant. Pas de nouveau workflow GH Action.

## 10. Découpage en sous-livrables (input du plan d'implémentation)

1. **Migration DB** — `race_goals` table + alter `athlete_profiles`. Tests RLS dans CI worker.
2. **Worker — `/garmin/profile-sync`** — endpoint + module `profile_sync.py` + transformer + 6 tests pytest. Pas de cooldown nécessaire.
3. **Schemas Zod partagés** — `lib/onboarding/schemas.ts` + tests vitest.
4. **Server Actions** — `app/(app)/onboarding/actions.ts` : `saveStepPerso`, `saveStepRace`, `saveStepPerf`, `saveStepDispo`, `finalizeOnboarding`, `syncGarminProfile`.
5. **Wizard hybride** — `app/(app)/onboarding/page.tsx` (Server) + `_components/onboarding-wizard.tsx` (Client) + 4 step forms.
6. **Layout redirect** — modifier `(app)/layout.tsx` pour rediriger non-onboardé.
7. **Profile editable inline** — modifier `app/(app)/profile/page.tsx` + 4 edit forms réutilisant les schemas.
8. **E2E Playwright happy path**.

Ordre conseillé d'implémentation : 1 → 2 (les deux ensemble : worker peut être testé en isolation) → 3 → 4 → 5 + 6 (wizard prêt + protection redirect activée) → 7 → 8.

## 11. Points de vigilance / décisions à revoir

- Si la cron daily du worker se déclenche pendant qu'un user fait son onboarding, et que ce user n'a pas de credentials Garmin valides (cas impossible ici car user_a fait connect avant onboarding), il n'y a pas de conflit — `run_daily_cron` skip les rows sans credentials.
- `garmin_synced_at` ne sert pour l'instant qu'à afficher l'horodatage dans `/profile`. Plus tard, on pourra en faire un trigger de re-sync automatique mensuel (post-MVP).
- Si Garmin renomme un endpoint (cf. fix garminconnect 0.3.x PR #5), le transformer doit échouer proprement (test #2 ci-dessus le couvre).
- La table `race_goals` n'a pas de versioning historique : éditer une course écrase l'ancienne valeur. Post-MVP envisageable : table `race_goals_history` ou colonnes audit.

---

**Fin du spec.**

Une fois ce spec validé par le user, on passe à `superpowers:writing-plans` pour générer le plan d'implémentation détaillé (tâches, ordre, dépendances entre sous-livrables, critères de done par tâche).
