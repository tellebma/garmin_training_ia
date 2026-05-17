# Design — Garmin Training Coach (MVP)

**Date :** 2026-05-17
**Statut :** Validé (architecture + EPICs)
**Échéance MVP :** début juillet 2026 (~6 semaines)
**Date triathlon cible :** août-septembre 2026

---

## 1. Contexte & objectif

Application web (PWA) qui synchronise les données Garmin Connect d'un utilisateur, génère un plan d'entraînement triathlon périodisé, et ajuste chaque jour la séance prescrite en fonction des signaux de fatigue (HRV, sommeil, charge). Le projet sert d'abord à l'auteur et à un groupe restreint d'amis inscrits au même triathlon (beta privée), avec une architecture déjà préparée pour un éventuel passage SaaS (P3).

## 2. Vision

> Donner à chaque triathlète amateur un coach personnel disponible 24h/24, qui comprend ses données physiologiques et lui propose la bonne séance au bon moment, dans des conditions réelles (météo, terrain, fatigue).

## 3. Non-objectifs (MVP)

Les éléments suivants sont **hors scope** du MVP et ne seront pas développés :

- Paiement / facturation / abonnements (Stripe)
- Site marketing / landing page commerciale
- Conformité RGPD complète (registre des traitements, DPO, HDS) — sera traitée en P3
- Application native iOS/Android (PWA suffit)
- Features sociales (likes, commentaires, leaderboard)
- Intégrations tierces autres que Garmin (Strava, Wahoo, Apple Health)
- Coaching de discipline unique sans triathlon (running pur, cyclisme pur)
- Plans pour Ironman (focus distance courte/moyenne d'abord)

## 4. Architecture

### 4.1 Vue d'ensemble

```
┌──────────────────────────────────────────────────────────────┐
│  Frontend Next.js 15 (Vercel) — PWA installable              │
│  • Dashboard "Séance du jour" + calendrier + métriques       │
│  • Plan détaillé, historique, profil                         │
│  • Notifications push web (Web Push API)                     │
└─────────┬────────────────────────────────────────┬───────────┘
          │ supabase-js                            │
          ▼                                        │
┌──────────────────────┐                          │
│  Supabase            │◄─────────────────────────┤
│  • Postgres + RLS    │      service_role        │
│  • Auth (magic link) │                          │
│  • Storage (FIT)     │                          │
│  • Edge Functions    │                          │
└──────────┬───────────┘                          │
           │                                      │
           ▼                                      │
   ┌──────────────────────────────────────────────┴───────────┐
   │  Worker Python (Fly.io free tier) — cron quotidien 5h    │
   │  • Sync Garmin (python-garminconnect)                    │
   │  • Calcul charge (CTL/ATL/TSB) + détection fatigue       │
   │  • Génère séance du jour via Claude API (hybride)        │
   │  • Match parcours selon météo + dénivelé requis          │
   │  • Envoie notif push via Supabase Edge Function          │
   └──────────────────────────────────────────────────────────┘
        │              │                    │
        ▼              ▼                    ▼
   Garmin Connect   Claude API         Open-Meteo (météo)
                                       OpenRouteService (parcours)
```

### 4.2 Principes structurants

- **Multi-tenant dès J0** : toutes les tables ont une colonne `user_id`, Row Level Security Supabase active.
- **Stateless API** : pas d'état serveur côté Next.js, tout l'état est en DB.
- **Worker découplé** : la sync Garmin est isolée dans un service Python (lib Python mature), pas de réécriture TypeScript.
- **Coaching hybride** : algorithme déterministe pour la structure macro (volumes, charge, périodisation), LLM pour le contenu créatif et l'ajustement contextuel.
- **PWA mobile-first** : install sur écran d'accueil, push notifications, accès offline pour la séance du jour.
- **Free tier partout** : Supabase + Vercel + Fly.io + Open-Meteo en gratuit. Seul coût récurrent = Claude API (~1-2€/mois).

### 4.3 Sécurité

- Tokens Garmin OAuth chiffrés en DB via Supabase Vault (ou clé symétrique stockée en var d'env Fly.io).
- RLS Postgres : un user ne peut lire/écrire que ses propres lignes.
- Service role key Supabase utilisée uniquement côté worker Python et Supabase Edge Functions, jamais exposée au front.
- Auth magic link (pas de mot de passe stocké).
- HTTPS partout (Vercel + Fly.io par défaut).
- Pas de stockage de données médicales sensibles au sens RGPD art. 9 strict (données fitness, pas diagnostic médical) — mais on consigne quand même un consentement explicite à l'onboarding pour les amis beta.

## 5. Stack technique

| Couche | Technologie |
|---|---|
| Frontend | Next.js 15 (App Router) + TypeScript + Tailwind + shadcn/ui |
| Charts | Recharts ou Tremor |
| State / data | Server Components + supabase-js + React Query côté client |
| Auth | Supabase Auth (magic link email) |
| DB | Supabase Postgres + Row Level Security |
| Storage | Supabase Storage (fichiers FIT bruts si utile) |
| Worker | Python 3.11+, FastAPI optionnel pour endpoints internes |
| Sync Garmin | `python-garminconnect` (v0.3.2+) |
| LLM | Claude Sonnet 4.6 via Anthropic SDK + prompt caching |
| Météo | Open-Meteo (gratuit, sans clé) |
| Routing | OpenRouteService (2000 req/jour gratuites) |
| Hébergement front | Vercel free |
| Hébergement worker | Fly.io free (3 VMs partagées) |
| Monitoring | Sentry (free tier) |
| Notifications | Web Push API (VAPID) via Supabase Edge Function |

## 6. Modèle de données (schéma initial)

```
auth.users (Supabase managé)
  │
  └──┬── athlete_profiles
     │     - user_id (PK, FK auth.users)
     │     - first_name, dob, sex
     │     - city, country, lat, lon
     │     - ftp_watts, vma_kmh, fc_max_bpm
     │     - sports_strengths jsonb (e.g. {swim: "weak", bike: "strong", run: "medium"})
     │     - available_days jsonb (e.g. ["mon", "wed", "fri", "sat", "sun"])
     │     - consent_data_processing bool, consent_signed_at timestamptz
     │
     ├── garmin_credentials
     │     - user_id (PK, FK)
     │     - oauth_tokens_encrypted bytea
     │     - last_sync_at timestamptz
     │
     ├── goals
     │     - id (PK), user_id (FK)
     │     - race_name, race_date, distance ('sprint'|'olympic'|'half'|'full')
     │     - target_time_seconds nullable
     │     - is_primary bool
     │
     ├── activities
     │     - id (PK), user_id (FK)
     │     - garmin_activity_id, start_time, sport, duration_s, distance_m
     │     - tss numeric, hr_avg, hr_max, power_avg, pace_avg
     │     - raw jsonb (payload Garmin complet pour analyse ultérieure)
     │
     ├── daily_metrics
     │     - user_id (FK) + date (PK composite)
     │     - resting_hr, hrv_rmssd, body_battery, stress_avg
     │     - sleep_duration_s, sleep_score, deep_sleep_s, rem_sleep_s
     │     - readiness_score numeric (calculé)
     │
     ├── training_plans
     │     - id (PK), user_id (FK), goal_id (FK)
     │     - generated_at, valid_from, valid_to
     │     - phase_structure jsonb (squelette macro)
     │     - status ('active'|'archived')
     │
     ├── planned_sessions
     │     - id (PK), plan_id (FK), user_id (FK)
     │     - scheduled_date, sport, type, target_tss, target_duration_s
     │     - description text (généré LLM)
     │     - intervals jsonb (structure détaillée)
     │     - adjusted_from_id (FK self, si swap)
     │     - status ('planned'|'completed'|'skipped'|'swapped')
     │
     ├── daily_briefings
     │     - user_id (FK) + date (PK composite)
     │     - readiness_assessment text
     │     - session_id (FK planned_sessions)
     │     - weather_summary jsonb
     │     - route_suggestion_id (FK routes, nullable)
     │     - notified_at timestamptz
     │
     └── routes (parcours détectés ou suggérés)
           - id (PK), user_id (FK)
           - name, sport, distance_m, elevation_gain_m
           - polyline text, start_lat, start_lon
           - source ('detected'|'generated')
           - usage_count int
```

## 7. EPICs

### E1 — Foundations & Auth

**Objectif :** poser les bases du projet (front + DB + auth) et installer la PWA sur mobile.

**Livrables :**
- Repo Next.js 15 initialisé (TypeScript, App Router, Tailwind, shadcn/ui).
- Projet Supabase créé, schéma initial (auth.users + athlete_profiles + garmin_credentials).
- Auth magic link fonctionnelle (login, logout, session persistée).
- Layout app responsive (header + bottom nav mobile).
- PWA configurée : manifest, icônes, service worker (next-pwa), installable iOS/Android.
- CI/CD Vercel branché sur main.

**Critères d'acceptation :**
- Un utilisateur peut s'inscrire via email, recevoir le magic link, se connecter, voir son tableau de bord vide.
- L'app s'installe sur l'écran d'accueil d'un iPhone et d'un Android.
- Lighthouse PWA score ≥ 90.

**Dépendances :** aucune.
**Effort estimé :** 3-4 jours.

---

### E2 — Sync Garmin (worker)

**Objectif :** synchroniser quotidiennement les données Garmin de chaque utilisateur dans Supabase.

**Livrables :**
- Service Python déployé sur Fly.io (Dockerfile, fly.toml).
- Flow d'authentification Garmin : l'user entre email/pwd Garmin une fois (avec MFA), les tokens OAuth sont chiffrés et stockés dans `garmin_credentials`.
- Cron quotidien (Fly.io scheduled machines) à 5h00 UTC : pour chaque user actif, sync activités J-7 à J, sommeil J-1, HRV J-1, FC repos, body battery, stress.
- Tables `activities`, `daily_metrics` peuplées avec déduplication par `garmin_activity_id`.
- Endpoint manuel `/sync/:user_id` pour re-sync à la demande (protégé service role).

**Critères d'acceptation :**
- Première sync d'un nouvel user récupère 90 jours d'historique.
- Sync quotidienne complète en < 30 s par user.
- RLS empêche un user de lire les données d'un autre user.
- Si Garmin renvoie une erreur d'auth, l'user reçoit un email pour reconnecter.

**Dépendances :** E1.
**Effort estimé :** 5-6 jours.
**Risque :** Garmin peut changer son API sans préavis, on est dépendant de `python-garminconnect`. Mitigation : monitoring d'erreur Sentry agressif sur le worker.

---

### E3 — Profil athlète & onboarding

**Objectif :** collecter les informations indispensables pour personnaliser le coaching.

**Livrables :**
- Wizard onboarding en 4 étapes :
  1. Informations personnelles (prénom, date de naissance, sexe, ville).
  2. Objectif principal (date du triathlon, distance, temps cible optionnel).
  3. Niveau de performance (FTP/VMA/FC max si connus, ou estimation par questionnaire).
  4. Disponibilité (jours d'entraînement, heures dispo/semaine, sports fort/faible).
- Page profil éditable post-onboarding.
- Consentement explicite au traitement des données (case à cocher, timestamp stocké).

**Critères d'acceptation :**
- L'onboarding est complétable en < 5 minutes.
- Aucun champ obligatoire n'est bloquant si l'user ne connaît pas la valeur (estimations proposées).
- Un user qui n'a pas complété son onboarding est redirigé vers le wizard à chaque login.

**Dépendances :** E1.
**Effort estimé :** 2-3 jours.

---

### E4 — Moteur de planification (algo)

**Objectif :** générer le squelette d'un plan triathlon périodisé à partir du profil et de la date de course.

**Livrables :**
- Module Python `coach.planner` :
  - Calcul CTL/ATL/TSB selon modèle Banister à partir de l'historique TSS.
  - Détermination des phases : `base` (50-60% du temps), `build` (25-30%), `peak` (10%), `taper` (1-2 semaines).
  - Génération squelette : pour chaque semaine, volume cible par sport + nombre de séances par type (endurance/intervalles/longue/récup) + TSS hebdo progressive.
  - Respect des jours dispos de l'user. Le sport déclaré "faible" reçoit un volume hebdo augmenté de 15-25% par rapport aux autres pour rattraper l'écart de performance.
- Persistance dans `training_plans` et `planned_sessions` (uniquement champs structurels, pas encore le contenu détaillé — c'est E5).
- Tests unitaires : progression de charge cohérente, taper bien dimensionné, semaines de récup tous les 4.

**Critères d'acceptation :**
- À partir d'un profil donné + date course, le moteur génère 8-12 semaines de plan en < 2 s.
- La charge hebdo progresse de manière monotone avec deconload toutes les 4 semaines.
- La phase taper réduit le volume de 40-50% sur les 10 derniers jours.

**Dépendances :** E2, E3.
**Effort estimé :** 5-7 jours.

---

### E5 — Génération des séances (LLM)

**Objectif :** transformer chaque slot du squelette en séance détaillée et lisible.

**Livrables :**
- Module Python `coach.session_generator` :
  - Prompt structuré envoyé à Claude Sonnet 4.6 avec : profil athlète + contrainte slot (sport, type, durée cible, TSS cible).
  - Prompt caching activé sur la partie profil athlète (réduit coûts ~80%).
  - Réponse au format JSON validé via Pydantic : `description`, `warmup`, `main_set` (liste d'intervalles), `cooldown`, `coaching_notes`.
  - Validation : la séance respecte la durée et la TSS cibles à ±10%.
  - Fallback : si LLM échoue ou hors-cadre, utiliser un template par défaut du type de séance.
- Génération en batch lors de la création du plan + à la demande pour replanification.

**Critères d'acceptation :**
- 100 séances générées en < 5 minutes.
- Coût total Claude < 0,50€ pour générer un plan de 12 semaines (84 séances).
- Aucune séance ne sort hors des bornes de TSS/durée.
- Les séances sont en français, lisibles, motivantes mais factuelles.

**Dépendances :** E4.
**Effort estimé :** 4-5 jours.

---

### E6 — Briefing quotidien + ajustement

**Objectif :** chaque matin, livrer à l'user la séance du jour ajustée selon sa fatigue, avec une explication courte.

**Livrables :**
- Cron Fly.io 5h30 UTC (après sync Garmin E2) :
  1. Pour chaque user, calcule un `readiness_score` (0-100) à partir de HRV, sommeil, FC repos, charge TSB.
  2. Applique règles d'ajustement :
     - `readiness < 40` → swap séance dure pour récup active ou repos.
     - `readiness 40-65` → garde la séance mais réduit l'intensité de 10-15%.
     - `readiness > 65` → garde la séance prévue.
     - 2 jours consécutifs `< 40` → flag "fatigue cumulée", notif spéciale.
  3. Génère un briefing court (3-5 phrases) via **Claude Haiku 4.5** (moins coûteux que Sonnet pour ce format court) avec contexte (séance + readiness + météo).
  4. Persiste dans `daily_briefings`.
  5. Envoie push notification Web Push via Supabase Edge Function.
- Page `/today` côté front affiche le briefing + séance + bouton "marquer comme faite/sautée/swap".

**Critères d'acceptation :**
- 100% des users actifs reçoivent leur briefing avant 6h locale.
- Le swap d'une séance dure → récup est tracé (`adjusted_from_id` rempli).
- L'user peut accepter ou refuser l'ajustement automatique depuis le front.

**Dépendances :** E5.
**Effort estimé :** 3-4 jours.

---

### E7 — Dashboard frontend

**Objectif :** offrir une interface mobile-first complète pour consulter plan, séances, métriques et historique.

**Livrables :**
- Page **`/today`** : briefing du jour, séance détaillée, météo, parcours suggéré, boutons d'action.
- Page **`/plan`** : calendrier 4 semaines (vue semaine sur mobile, vue mois sur desktop), navigation aisée, drag pour replanifier (post-MVP).
- Page **`/stats`** : graphiques CTL/ATL/TSB sur 12 semaines, HRV 30 jours, sommeil 30 jours, volume hebdo par sport.
- Page **`/history`** : liste des activités synchronisées avec analyse rapide (TSS, durée, FC, allure/puissance).
- Page **`/profile`** : édition profil + paramètres (notifications, unités, reconnexion Garmin).
- Design system shadcn/ui, dark mode par défaut, polices et palette cohérentes.

**Critères d'acceptation :**
- Toutes les pages utilisables sur iPhone 12+ sans scroll horizontal.
- First Contentful Paint < 1,5 s en 4G.
- Lighthouse Performance ≥ 85.

**Dépendances :** E2, E4 (données nécessaires).
**Effort estimé :** 5-7 jours.

---

### E8 — Parcours géolocalisés (Should-have)

**Objectif :** suggérer un parcours adapté à la séance, au terrain et à la météo du jour.

**Livrables :**
- Clustering des activités passées en "spots" : détection des zones de départ récurrentes (DBSCAN sur lat/lon de start).
- Récupération météo Open-Meteo daily pour la ville/zone du user.
- Logique de matching :
  - Séance vélo vallonnée → parcours historiques avec D+ adapté.
  - Séance pluie + run intervalles → suggérer piste indoor si déclarée, sinon prévenir.
  - Sortie longue vélo + beau temps → suggestion via OpenRouteService (loop autour de chez l'user avec D+ cible).
- Affichage dans le briefing et page `/today` : nom du parcours, distance, D+, polyline carte (Leaflet ou Mapbox GL en mode token-free).

**Critères d'acceptation :**
- Au moins 80% des séances ont une suggestion pertinente après 4 semaines d'usage.
- L'user peut désactiver les suggestions globalement.

**Dépendances :** E2 (historique), E6 (briefing).
**Effort estimé :** 3-5 jours.
**Note :** EPIC marqué "Should-have", peut glisser sur P2 si le timing devient serré.

---

### E9 — Beta privée (invitations + monitoring)

**Objectif :** ouvrir l'app à 5-10 amis triathlètes dans des conditions sûres et instrumentées.

**Livrables :**
- Système d'invitation : génération de codes d'invitation uniques (max 10), envoi par email avec lien magique.
- Page `/invite` (admin only, accès via flag dans `athlete_profiles`) pour gérer les invitations.
- Page "À propos / Privacy" minimaliste expliquant le traitement des données et la base légale (consentement).
- Sentry intégré sur le front et le worker, alerts email en cas d'erreur critique.
- Formulaire feedback intégré (`/feedback`) → table `user_feedback` consultable par admin.
- Documentation onboarding pour les beta testers (1-pager markdown ou page in-app).

**Critères d'acceptation :**
- 5 amis utilisent l'app pendant 2 semaines sans incident bloquant.
- Tout crash front ou erreur worker remonte dans Sentry en < 1 minute.
- Au moins 3 retours feedback collectés.

**Dépendances :** E7, E6.
**Effort estimé :** 2-3 jours.

---

## 8. Chemin critique & planning

```
Semaine 1 ─ E1 ──────────────┐
                              ├─→ Semaine 2-3 ─ E2 ──┐
Semaine 1 ─ E3 ──────────────┘                       │
                                                      ├─→ Semaine 4 ─ E4 ──→ Semaine 5 ─ E5 ──→ Semaine 5 ─ E6 ──┐
                                                      │                                                            │
                                                      └─→ Semaine 3-4 ─ E7 (parallèle) ──────────────────────────┤
                                                                                                                   │
                                                                                                    Semaine 6 ─ E8 (optionnel) + E9 (release beta)
```

**Jalon 1 (fin semaine 1)** : E1 + E3 prêts → un user peut s'inscrire et compléter son profil.
**Jalon 2 (fin semaine 3)** : E2 + E7 partiels → données Garmin visibles dans un dashboard.
**Jalon 3 (fin semaine 5)** : E4 + E5 + E6 → un plan complet est généré et la séance du jour s'affiche avec ajustement.
**Jalon 4 (fin semaine 6)** : E9 → invitations envoyées aux amis triathlètes.
**Jalon 5 (mi-juillet)** : E8 livré si tout va bien.

## 9. Coûts opérationnels MVP

| Poste | Coût mensuel |
|---|---|
| Supabase (free tier) | 0€ |
| Vercel (free tier) | 0€ |
| Fly.io (free tier 3 VMs) | 0€ |
| Open-Meteo | 0€ |
| OpenRouteService | 0€ |
| Sentry (free tier) | 0€ |
| Claude API (Sonnet 4.6 + cache) | 1-2€ (10 users) |
| Domaine (optionnel) | ~1€/mois (10-15€/an) |
| **Total** | **1-3€/mois** |

## 10. Risques & mitigations

| Risque | Impact | Mitigation |
|---|---|---|
| Garmin change son API privée | Élevé (worker cassé) | Monitoring Sentry, fallback sur Garth si python-garminconnect en panne, export FIT manuel d'urgence |
| Tokens OAuth Garmin expirent | Moyen (UX) | Email automatique à l'user pour reconnecter, expiration ~6 mois |
| Hallucinations LLM dans les séances | Moyen (séance absurde) | Validation Pydantic stricte + fallback template, prompts cadrés avec exemples |
| Free tier Fly.io limite (3 VMs) | Faible en MVP | Surveiller usage CPU, passer en payant (~5€/mois) si > 20 users |
| RGPD si projet s'élargit | Élevé en P3 | Consentement écrit signé dès la beta, registre prêt à formaliser, hébergement EU (Supabase Frankfurt) |
| Sur-engineering perte de focus | Moyen (deadline ratée) | Strict "must-have" only pour MVP, EPICs "should" reportables sur P2 |
| Charges LLM si beaucoup d'users | Faible en MVP | Prompt caching + génération batch + modèle Haiku pour fallback |

## 11. Décisions ouvertes

Aucune décision bloquante. Quelques points à trancher en cours d'implémentation, mais non bloquants pour démarrer :

- **Tremor vs Recharts** pour les graphiques : sera testé en E7.
- **Mapbox vs Leaflet** pour l'affichage carte : sera testé en E8 (préférence Leaflet pour zéro coût).
- **Fréquence du cron** : 5h00 UTC retenu, à valider selon fuseaux des beta testers.
- **Stratégie de seed** des FTP/VMA pour user sans valeur connue : tests progressifs ou estimation auto à partir des activités passées — à raffiner en E3/E4.

## 12. Roadmap post-MVP (indicatif)

- **P2 (sept-déc 2026)** — Itérations basées sur retours beta : améliorer ajustement quotidien, raffiner UX, ajouter intégration Strava optionnelle, dashboards plus fins, partage de plans entre amis (light social).
- **P3 (2027+)** — Passage SaaS : Stripe, marketing, RGPD complet, support multi-langues, plans pour Ironman/duathlon, app native si justifié par les usages.
