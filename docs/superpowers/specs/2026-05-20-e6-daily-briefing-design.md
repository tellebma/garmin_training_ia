# E6 — Daily Briefing + Session Adjustment — Design

**Date** : 2026-05-20
**Statut** : Auto-drafted (owner en sport, à reviewer post-implémentation)
**EPIC** : E6 — Briefing quotidien + ajustement
**Dépendances entrantes** : E2 (HRV/sleep/daily_metrics sync), E4 (planned_sessions + daily_banister_state), E5 (workout structure)
**Dépendances sortantes** : E9 (beta privée) consommera le briefing pour rappels push
**Effort estimé** : 1 jour

---

## 1. Objectif

Quand l'utilisateur ouvre `/today`, lui afficher un **briefing du jour** qui :

1. Calcule un **score de readiness** (0-100) basé sur HRV, sommeil, body battery, TSB Banister
2. Affiche un **statut** clair : Ready / Caution / Rest advised
3. Si statut ≠ Ready, **suggère une adaptation** de la séance planifiée (downgrade ou repos)
4. Fournit une **explication courte FR** des facteurs limitants

**Pourquoi** : un plan rigide ignore les jours où l'athlète est cuit. Pousser un intervalle quand le HRV est dans le rouge augmente le risque de surentraînement. E6 ferme la boucle Plan → Réalité.

---

## 2. Critères d'acceptation

- `POST /coach/daily-briefing` retourne `{ readiness_score, status, explanation_md, planned_session, suggested_session? }`
- Statut dérivé du score : ≥70=ready, 40-69=caution, <40=rest_advised
- Pas de tunneling : la suggestion ne mute pas `planned_sessions.workout`, c'est purement une vue alternative
- L'utilisateur garde le choix : afficher la séance prévue OU la suggestion adaptée
- Si pas de HRV/sleep récent (cold-start), retourne `status=ready` avec explication "Données limitées"
- Endpoint user-scoped, rate-limité comme les autres `/coach/*`

---

## 3. Règles de scoring

**Baseline** : 80 (corps en forme normale)

**Modifiers négatifs** (cumulables) :

| Signal | Seuil | Pénalité |
|---|---|---|
| HRV today | < 0.70 × weekly_avg | -25 |
| HRV today | < 0.85 × weekly_avg | -10 |
| HRV status | `unbalanced` / `poor` / `low` | -15 |
| Sleep duration | < 6h | -15 |
| Sleep duration | < 7h | -5 |
| Sleep score | < 50 | -10 |
| Resting HR | > 1.10 × baseline | -10 |
| TSB Banister | < -30 (très fatigué) | -15 |
| TSB Banister | < -20 (fatigué) | -8 |
| Body battery (soir J-1) | < 30 | -10 |

**Modifiers positifs** (cumulables) :

| Signal | Seuil | Bonus |
|---|---|---|
| HRV today | > 1.10 × weekly_avg | +5 |
| Sleep duration | > 8h ET score > 80 | +5 |
| TSB | > +5 (frais) | +5 |

Score borné [0, 100].

---

## 4. Règles d'adaptation

| Statut | Adaptation |
|---|---|
| Ready (≥70) | Garder la séance planifiée |
| Caution (40-69) | Downgrade d'1 niveau (intervals→threshold, threshold→endurance, long→endurance, endurance→recovery) |
| Rest advised (<40) | Forcer rest (ou recovery si déjà rest planifié) |

L'adaptation **n'écrit pas en DB**. Elle est calculée à la volée à chaque appel, parce que les signaux changent (HRV mesuré le matin, sleep mesuré la nuit). Si l'utilisateur consulte le briefing à 8h vs 18h, le score peut différer si une nouvelle sleep entry est arrivée.

---

## 5. Architecture

```
[Vercel /today RSC]
  │ Server Action: getDailyBriefing()
  ▼
[Worker POST /coach/daily-briefing]
  │ rate_limit.check_or_raise (60/h/user)
  │
  ├── briefing.compute_readiness(user_id):
  │     - fetch today's hrv (table hrv, date=today)
  │     - fetch yesterday's sleep (table sleep, date=yesterday)
  │     - fetch yesterday's daily_metrics (resting_hr, body_battery_low)
  │     - fetch today's Banister state (daily_banister_state.tsb)
  │     - apply scoring rules -> score, factors[]
  │
  ├── briefing.derive_status(score) -> ready|caution|rest_advised
  ├── briefing.suggest_adjustment(planned_session, status) -> suggested_session?
  ├── briefing.format_explanation(factors, status, locale='fr') -> markdown
  │
  └── return DailyBriefing
```

Pas de LLM côté E6 (rule-based pur). Explanation est templated FR.

---

## 6. Modèle de données

**Pas de nouvelle table.** E6 consomme :
- `hrv` (déjà rempli par E2)
- `sleep` (déjà rempli par E2)
- `daily_metrics` (déjà rempli par E2)
- `daily_banister_state` (déjà rempli par E7 + E2 cron)
- `planned_sessions` (déjà rempli par E4 + E5)

Le briefing est **calculé on-demand** à chaque appel. Pas de cache (overkill pour MVP, les inputs changent).

---

## 7. Pydantic schema (worker)

```python
class ReadinessFactor(BaseModel):
    name: str  # ex: "hrv_low", "sleep_short"
    impact: int  # signed integer (negative = penalty)
    explanation: str  # short FR

class SuggestedSession(BaseModel):
    sport: str
    session_type: str
    note: str  # ex: "Downgrade intervals -> threshold"

class DailyBriefing(BaseModel):
    date: str  # ISO date
    readiness_score: int  # 0-100
    status: Literal["ready", "caution", "rest_advised"]
    explanation_md: str
    factors: list[ReadinessFactor]
    planned_session: dict | None  # raw planned_sessions row
    suggested_session: SuggestedSession | None  # adjustment if status != ready
```

---

## 8. UI

`/today` ajoute une **carte de briefing** au-dessus du workout :

```
┌─ Briefing du jour ─────────────────────┐
│  [Ready] Score: 78/100                 │
│                                         │
│  Tout est OK : HRV stable, bon sommeil.│
│  Bonne séance !                         │
└─────────────────────────────────────────┘
```

Pour statut "caution" :
```
┌─ Briefing du jour ─────────────────────┐
│  [Attention] Score: 52/100              │
│                                         │
│  HRV un peu bas (32 vs moy 41), sommeil│
│  court (5h45). Allège ta séance.       │
│                                         │
│  Adaptation : Endurance au lieu de     │
│  Intervals (- 1 niveau)                │
│  [Voir la séance adaptée]              │
└─────────────────────────────────────────┘
```

Pour statut "rest_advised" :
```
┌─ Briefing du jour ─────────────────────┐
│  [Repos conseillé] Score: 28/100        │
│                                         │
│  Signes de fatigue marqués : HRV très  │
│  bas, sommeil interrompu, TSB -32.     │
│  Repos ou marche tranquille aujourd'hui.│
└─────────────────────────────────────────┘
```

Couleurs : vert (ready), orange (caution), rouge (rest_advised). Aucun emoji (CI gate).

---

## 9. Endpoint & rate limit

`POST /coach/daily-briefing` :
- Auth : Bearer JWT user
- Body : `{}` (rien à passer, on lit la DB)
- Rate limit : 60/h/user (idem ensure_sessions)
- Réponse type `DailyBriefing`

---

## 10. Erreurs

| Cause | Comportement |
|---|---|
| Pas de HRV/sleep récent | `status="ready"`, score=80 par défaut, factors=[{name:"insufficient_data", impact:0, explanation:"..."}] |
| Pas de planned_session pour today | Retourne quand même le briefing, `planned_session=None`, pas de suggestion |
| Rate limited | Statut `rate_limited`, UI affiche message |

---

## 11. Testing

- `worker/tests/coach/test_briefing.py` : scoring rules (HRV low / sleep short / TSB low / mix), downgrade rules, no-data fallback
- `worker/tests/test_main.py` : endpoint /coach/daily-briefing
- `tests/unit/lib/coach/briefing-types.test.ts`
- `tests/unit/actions/briefing.test.ts`
- E2E Playwright (post-merge) : connecté, /today affiche bien la carte

Coverage cible : 90 % sur briefing.py.

---

## 12. Hors scope (post-MVP)

- Push notification quotidienne avec le briefing (E9 ou plus tard)
- Historique des briefings + accuracy review (post-MVP)
- Modèle ML qui apprend les seuils personnels (post-MVP, après collecte de feedback)
- Briefing pré-séance vs post-séance (post-MVP)
