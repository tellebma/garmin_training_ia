# Backlog — Garmin Training Coach

Ce fichier est la source de vérité du backlog post-MVP. Les specs détaillées
restent dans `docs/superpowers/specs/` et les plans d'exécution dans
`docs/superpowers/plans/`.

## Re-priorisation 2026-06-28 (ouverture beta amis + course août-sept)

L'owner ouvre la beta à ses amis et la course est dans ~2-3 mois. Re-priorisation
selon trois lentilles retenues — **qualité coach** (prépa course), **latence / temps
réel**, **solidité multi-utilisateurs** — et **abandon de la lentille polish UX** pour
l'instant. Conséquences :

- **Remontés en P0** : E16.1 (double appel auth, plafond de latence transversal),
  « Worker : filtrer le plan actif » (correctness multi-users), « Observabilité production »
  (Sentry — voir les erreurs des amis), E9.4 (progression par discipline).
  E13.2 (déjà P0) est **V1 livrée** (PR #75, mergée 2026-07-02).
- **Rétrogradés en P2** (polish UX différé) : « Identité numérique / `DESIGN.md` »
  (était P0), E14.3 bulles explicatives, carte « dernière activité » de `/today`.
- Inchangés : E15.1 Strava (P1, plus gros chantier), E18 admin/coût IA (P1).

## Mise à jour 2026-07-26 (pause Strava + resynchronisation)

- **Strava mis en pause** (abonnement API payant non prévu) : voir l'encadré en tête de
  l'EPIC E15. E15.1 reste livrée mais désactivée par configuration.
- **Livrés depuis la dernière revue** : E18 console admin (#90, #93, #95, #105),
  E15.1 Strava (#101), E14.2 livrable C (#100), E16.1 (#99), E19/E20/E21 (#103),
  sommets `natural=peak` (#102, #106).
- **Reste P0** : E9.4 progression par discipline (spec écrite le 2026-07-26, plan à écrire),
  « Worker : filtrer le plan actif », « Recommandations sportives sourcées et auditables ».

## Audit du coach 2026-08-01 — 16 constats, 5 lots livrés

Audit complet du moteur de coaching (code + données de prod). Trois défauts structurels
rendaient le plan inopérant sans qu'aucune erreur ne remonte :

1. **Le TSS n'était jamais calculé** — 100 % des activités valaient `durée × 50` (`fc_max_bpm`
   NULL + `CYCLING_SPORTS` omettant `"bike"`). CTL/ATL/TSB ne mesuraient que du volume horaire.
2. **Plan sans intensité ni séance longue** — `max_level = min(niveaux)` verrouillait tous les
   sports sur la discipline la plus faible ; le type `long` n'était attribuable qu'au dimanche,
   jamais retenu par le sélecteur de jours. Sur 82 séances en prod : 0 threshold, 0 pma, 0 long.
3. **Périodisation réinitialisée chaque semaine** — les phases étaient recalculées depuis
   `today` à chaque régénération : phase « base » à J-21 de la course A, jamais de `peak`.

Constat produit le plus parlant : sur 20 jours consécutifs, **aucune séance planifiée n'a été
suivie**, et le briefing pénalisait l'athlète (-3 readiness) à chaque substitution de discipline.

**V1 livrée** — issues #120 à #135, toutes fermées :

| Lot | Périmètre | Issues | PR |
|---|---|---|---|
| A | TSS / Banister / sports | #120, #133, #134 | #139 |
| B | planner (intensité, longue, périodisation, volume, D+, sports) | #121-#123, #127, #128-#131, #135 | #141 |
| C | génération LLM (modèle, échecs, zones chiffrées, natation) | #124, #125 | #140 |
| D | briefing (jour de repos, readiness) | #132, ½ #127 | #136 |
| E | fraîcheur des données + alerte | #126 | #138 |

Correctif d'exploitation associé : #143 (ordre des migrations Supabase).

**Suites — items *Todo* distincts** : #145 (2ᵉ verrou d'intensité dans le prompt LLM),
#146 (`load_spike`/`elevation_spike` permanents), #147 (briefing sur données périmées),
#148 (rendu front course multisport + écart budget), #149 (`resolve_fc_max_bpm` dans
`sync.py`), #144 (lint d'antériorité des migrations).

**Actions d'exploitation restant à l'owner** : re-puller `tellebma/garmin-sync:latest` sur
UNRAID (sans quoi rien de tout ceci ne tourne), lancer le backfill TSS
(`python -m garmin_sync.coach.backfill_tss --recompute-all`) **avant** toute régénération de
plan, et reconnecter le compte Garmin dont le token a expiré.

## Coût LLM — bascule sur gpt-5.6-luna (2026-08-03)

Comparaison des tarifs OpenAI à partir de la consommation réelle (`llm_usage`, 3 372 tokens
d'entrée / 1 343 de sortie par génération). Le lot C de l'audit (issue #124) avait remplacé
`gpt-4o-mini` par `gpt-5.4-mini` pour supprimer ~34 % de rejets d'enveloppe, au prix d'un
coût par génération **×6,5** (0,13 ¢ → 0,86 ¢ : +5× sur le tarif, +2,3× sur les tokens de
sortie, le modèle raisonnant davantage).

| Modèle | $/1M in | $/1M out | $/1 000 générations |
|---|---:|---:|---:|
| gpt-4o-mini | 0,15 | 0,60 | 1,31 |
| **gpt-5.6-luna** | **0,20** | **1,20** | **2,29** |
| gpt-5-mini | 0,25 | 2,00 | 3,53 |
| gpt-5.4-mini | 0,75 | 4,50 | 8,57 |
| gpt-5.6-terra | 2,00 | 12,00 | 22,9 |
| gpt-5.6-sol | 5,00 | 30,00 | 57,2 |

**V1 livrée** (PR #152) — défaut `OPENAI_MODEL` = `gpt-5.6-luna` (~3,75× moins cher que `gpt-5.4-mini`,
génération de modèle plus récente, contexte 1,05 M) et `llm_pricing.py` complété avec les
familles 5.6 / 5 / 5.4 + test de régression garantissant que le défaut est toujours tarifé
(un modèle absent de la table faisait silencieusement remonter des coûts à 0 dans la console
admin). Tarifs vérifiés le 2026-08-03.

**Suites — items *Todo* distincts** :

- Surveiller le taux de rejet d'enveloppe sur les premières générations luna ; retour arrière
  immédiat par `OPENAI_MODEL=gpt-5.4-mini` (variable d'env, pas de redéploiement).
- Modéliser le *cached input* (~10 % du tarif input) : le prompt système est stable, l'écart
  de sur-comptage grandit avec le volume.
- Évaluer le Batch API (−50 %) pour la régénération de plans du cron 05:00 UTC, asynchrone
  par nature.
## Audit spécificité course 2026-08-14 — 7 constats (retour owner « je ne me retrouve pas dans les demandes du coach »)

Contexte : plan actif de l'owner pour le **Triathlon de la Madelaine** du 2026-08-22
(1,4 km natation / 47 km vélo — 2000 m D+ / 8 km course à pied — 200 m D+). Sur les
41 séances planifiées, le plan reste générique : la course est un triathlon très typé
montagne, l'entraînement ne l'exprime presque pas. Le D+ vélo est bien capté (sorties
longues à 1920 m et 1739 m) — c'est le seul axe réellement spécifique.

### P0 — Aucune séance d'enchaînement (brick) n'est jamais planifiée

- `allocate_sport_sessions` / `assign_sports` (`worker/src/garmin_sync/coach/training_days.py`)
  ne répartissent que les disciplines présentes dans les `legs` de la course : `brick`
  n'est jamais candidat, alors que `planner.py` porte déjà ses tables TSS/heure
  (`("brick", "endurance") = 65.0`), sa vitesse de référence et son seuil de D+.
- Constat prod : **0 brick sur 41 séances** d'une prépa triathlon dont l'épreuve enchaîne
  8 km de course après 2000 m de D+ à vélo.
- **Critère** : au moins une séance d'enchaînement par semaine en phase build/peak dès que
  la course comporte ≥ 2 disciplines successives, avec un contenu vélo→CAP explicite.

### P0 — Volume de qualité quasi nul dans le plan généré

- Sur les 41 séances : 1 seule `threshold`, 0 `intervals`, 0 `pma`, 0 `sprint` ; tout le
  reste est `endurance` / `recovery` / `rest`.
- L'audit du 2026-08-01 avait débloqué l'attribution d'intensité (#121), mais la
  répartition réelle reste écrasée par l'endurance — le plan ne ressemble pas à une prépa.
- **Critère** : sur une semaine build, au moins une séance de qualité par discipline
  prioritaire, et une répartition intensité/endurance vérifiable en test.

### P1 — La discipline faible déclarée n'est pas travaillée

- Profil owner : `sports_strengths = {run: 1, swim: 2, bike: 4}`. Le run — point faible
  explicite — ne reçoit que de l'`endurance` et de la `recovery`, jamais de qualité.
- Le D+ ciblé en course à pied (40 à 116 m) reste sous l'exigence réelle de l'épreuve
  (200 m sur 8 km).
- **Critère** : le biais point-faible de `allocate_sport_sessions` se traduit aussi en
  *nature* de séance, pas seulement en nombre ; la cible D+ course à pied atteint le
  niveau de l'épreuve en phase build/peak.

### P1 — Le jour J n'a aucun contenu

- La séance `race` est créée sans `target_duration_s`, sans `target_tss` et sans `workout`
  (`_race_day_session`, `planner.py:260`) : l'athlète n'a ni estimation de temps, ni pacing
  par segment, ni plan nutrition, ni consigne de transition.
- **Critère** : le jour de course affiche une durée estimée, un déroulé par segment et des
  consignes course (pacing, nutrition, transitions), cohérents avec les `legs` saisis.

### P1 — Le D+ hebdomadaire est concentré au-delà du réalisable

- `_ELEVATION_SESSION_WEIGHT` (`long: 2.0`) empile l'essentiel du D+ de la semaine sur une
  seule sortie : 1920 m sur 2 h le 2026-08-08, soit ~960 m/h, plus raide que la course
  elle-même (~700 m/h estimés sur la partie vélo).
- **Critère** : un plafond de gradient (m de D+ par heure, par sport) borne la cible d'une
  séance ; le surplus est réparti sur les autres séances de la semaine ou écrêté.

### P2 — La natation n'est jamais spécifique à l'épreuve

- 9 séances de natation, toutes `endurance` / `recovery` : rien qui prépare 1,4 km en eau
  libre (départ groupé, sighting, allure de course, combinaison).
- **Critère** : au moins une séance « format course » avant l'échéance quand la course
  comporte un leg natation en eau libre.

### P2 — Une fenêtre de préparation très courte n'est pas signalée

- `prep_start_date = 2026-08-02` pour une course le 2026-08-22 : 3 semaines, phases
  base → build → taper compressées. Aucun message ne prévient que le plan ne peut pas
  produire de progression sur une telle fenêtre.
- **Critère** : quand la fenêtre est inférieure au minimum utile, l'app l'explique et
  bascule sur un objectif réaliste (affûtage / maintien) au lieu de simuler une prépa.

## Audits transverses 2026-08-14 — 28 constats (retours, programme, gestion des séances)

Trois audits menés en parallèle sur le code confronté aux données de prod, en réponse au même
retour owner. Le diagnostic est convergent : **le moteur calcule beaucoup de choses justes, puis
rien ne vérifie ce qui sort**. Trois ruptures, chacune démontrée sur des données réelles.

1. **Entre le budget calculé et la charge émise.** Budget hebdo de 284 TSS (après ramp cap),
   plan émis à 367 — dont 202 en vélo pour un budget de 81. Le clamp de durée re-dérive le TSS
   depuis la durée clampée, et les planchers de `duration_bounds` fabriquent jusqu'à 2,5× la
   charge prescrite. Les trois ramp caps (10/15/20 %) sont franchis simultanément, sans qu'aucun
   test ne le voie.
2. **Entre la physiologie et les messages.** Les 4 ancres (FCmax, VMA, FTP, CSS) sont NULL et non
   résolues côté génération ; `activities.tss` vaut encore `durée × 50` ; `body_battery_high`
   reçoit la dernière valeur du jour au lieu du maximum. Le coach affirme des choses sur
   l'*effort* en ne mesurant que des *heures*.
3. **Entre ce qui est calculé et ce qui est affiché.** 34 % des jours sont des jours de repos et
   la carte de briefing y masque six blocs pourtant calculés et stockés ; le panneau Récupération
   inverse le sens du stress et de la FC de repos ; le markdown des séances s'affiche brut.

S'y ajoute une **rupture d'intention** : les `legs` de la course ne sont jamais transmis au
générateur, les vitesses de course sont des constantes de barème (épreuve estimée à 3 h 50 contre
~5 h réelles), et l'intensité est structurellement interdite dans les disciplines faibles.

**Issues créées** (toutes *Todo*, EPIC Coaching sur le Project #4) :

| Thème | P0 | P1 | P2 |
|---|---|---|---|
| Planner — charge et périodisation | #164 clamp vs budget, #165 intensité interdite, #166 grille jour de semaine, #167 TSB ignoré | #182 taper amputé, #183 vitesses non calibrées, #184 plafond 45 TSS/h, #185 jours sans espacement | #188 offsets écrasés, #189 périodisation courte, #190 semaine de référence |
| Génération de séances | #168 durées vs allures | #172 ancres non résolues, #173 fatigue gravée sur 7 jours, #175 workout jamais rafraîchi, #176 ajustement condamnant, #186 épreuve non transmise | — |
| Retours à l'athlète | #170 body battery, #171 readiness = volume | #177 briefing figé, #178 coach au futur, #179 jour de repos muet, #180 libellés inversés, #181 ajustement repos→repos | #192 rôle des séances |
| Données et charge | #169 multi-sport à moitié tarif | #187 markdown brut | #191 deux échelles de TSS |

**Ordre recommandé** : #170 et #169 d'abord (données fausses en entrée de tout le reste), puis
#164 et #167 (boucler la charge), puis #165 avec #155/#156, puis le lot front #179/#180/#187 qui
a le meilleur rapport valeur/effort.

## EPICs issus des retours owner (2026-06-21)

Trois EPICs regroupent les retours de l'owner du 21/06/2026. Les items détaillés
restent tracés dans les sections thématiques ci-dessous ; ces EPICs servent de cadrage
et de priorisation.

### EPIC E13 — Plan d'entraînement réaliste et individualisé

**Priorité : P0 — Statut : à planifier**

Le plan doit ressembler à ce qu'un vrai coach triathlon prescrit : séances de durée
crédible, adaptées au niveau de l'athlète par discipline, avec mobilité et vrais jours
de repos.

- **E13.1 P0 — Séances de durée réaliste — V1 livrée** : la régression « séances trop
  courtes » est corrigée. `coach/duration_bounds.py` définit des bornes plancher/plafond
  réalistes par `(discipline, type, phase)` (base/build/peak, taper→peak) et le planner
  clampe chaque durée dessus (`planner.py` via `clamp_duration_to_bounds`). Couvert par
  `tests/coach/test_duration_bounds.py`. Voir « Structure réaliste des séances générées ».
- **E13.2 P0 — Plan adaptatif par niveau de discipline** : **exploiter réellement le
  niveau par discipline déjà saisi à l'onboarding** (aujourd'hui sous-utilisé dans les
  recommandations) et adapter volume, charge, intensité et progression discipline par
  discipline. Owner confirmé : fort en vélo, plus faible en natation et course à pied.
  Voir « Adapter le plan au niveau par discipline ».
- **E13.3 P1 — Mobilité / renforcement dans le plan** : intégrer des séances de
  mobilité, souplesse et renfo (prehab) bien placées sans alourdir la charge.
- **E13.4 P1 — Repos = repos — V1 livrée** : un jour de repos est un vrai repos, sans
  compte rendu ni structure de séance côté UI. `/plan` rend le repos via une ligne sobre
  « Repos / Récupération planifiée » (variante repos de `SessionCard`, sans durée/TSS, sans
  bouton régénérer ni workout détaillé). La `BriefingCard` masque le badge readiness et la
  revue d'activités les jours de repos. Côté worker, `format_explanation_md` est conscient
  du repos et n'affiche plus « Bonne séance ! » un jour de repos. Voir « Repos = repos (UI) ».

### EPIC E14 — Visualisation pro et pédagogie des métriques

**Priorité : P1 — Statut : à planifier**

Élever la qualité des graphiques au niveau Garmin/Strava et rendre les métriques
compréhensibles pour un athlète non expert.

- **E14.1 P1 — Graphiques pro** : profil d'altitude, FC dans le temps, allure/vitesse,
  puissance, cadence, zones, splits/tours, distribution d'effort — lisibles, soignés,
  interactifs. S'appuyer sur `activity_samples`. ✅ **Régression lisibilité « courbe FC plate »
  (E14.1b) — V1 livrée (PR #74)** : `ActivitySamplesChart` refondu en panneaux empilés
  synchronisés (`syncId`), un axe Y réel par métrique (FC plus jamais plate), toggle
  temps/distance + chips de visibilité, axe allure inversé. Voir détail § « Graphiques pro et
  carte d'activité ». Reste E14.1 « graphiques pro » au sens large (splits/tours, distribution
  d'effort) et le tooltip combiné unique (suite post-V1).
- **E14.2 P1 — Carte d'activité** : afficher le tracé GPS dans `/history/[id]` avec
  dénivelé et survol corrélé FC/allure. Recoupe E9.5 et la spec E8a.
  Livrable B livré : vignettes SVG dans l'historique, trace colorée par métrique (FC/vitesse/altitude) sur le détail, heatmap globale sur /stats.
  Livrable C livré : survol corrélé FC/allure — survoler le graphique de métriques sur la
  fiche activité met en évidence le point correspondant sur la carte GPS (PR #100).
- **E14.3 P2 — Bulles explicatives** (rétrogradé P1 → P2 le 2026-06-28) : infobulles sur charge (CTL), forme (TSB),
  fatigue (ATL), HRV, TSS, zones, dérive cardio. Expliquer « c'est quoi » et « comment
  l'utiliser pour progresser » en langage simple, plus un glossaire accessible.

### EPIC E15 — Ingestion multi-source et quasi temps réel

**Priorité : P1 — Statut : E15.3/E15.4 livrées, volet Strava ⏸️ en pause (voir encadré)**

Récupérer les activités plus vite sans seulement augmenter la fréquence du polling.

> ## ⏸️ Tout le volet Strava est EN PAUSE (décision owner, 2026-07-26)
>
> **Raison** : l'accès à l'API Strava nécessaire pour ce projet suppose un abonnement Strava
> payant que l'owner ne prévoit pas de prendre. Le code livré (E15.1) **reste dans le repo**
> mais l'intégration est **désactivée par configuration** : sans les secrets `STRAVA_*`,
> les 4 endpoints worker répondent `404` (`_require_strava_enabled`, `worker/src/garmin_sync/main.py`)
> et `/profile` n'affiche plus la carte « Connecter Strava » (sauf pour un athlète déjà
> connecté). Réactivation = poser les secrets, rien à recoder.
>
> **Sont en pause** : E15.1 et toutes ses suites (dédup bidirectionnelle, TSS Strava,
> banner OAuth, loading state du bouton disconnect), E15.6 (positionnement « Strava suffit »),
> et le volet « activités Strava » de E15.5. **Ne sont pas en pause** : E15.2, E15.3, E15.4,
> et le volet Polar/wellness de E15.5.
>
> **Sécurité** : l'action owner « IP allowlisting Nginx sur `/strava/webhook` » est **annulée** —
> le garde-fou `404`-si-non-configuré supprime la surface d'attaque à la source (voir détail
> dans la suite E15.1 ci-dessous).

- **E15.1 P1 — Intégration Strava (compte lié + ingestion temps réel) — V1 livrée, ⏸️ EN PAUSE**
  (PR #101, désactivée par la PR « pause Strava ») : OAuth2 complet avec `athlete_strava_credentials`
  (refresh token chiffré Fernet, pattern SEC-1-hardened), profil utilisateur actualisé
  lors du connect. Front : écran « Connecter Strava » sur `/profile` (à côté de Garmin,
  pas en remplacement), avec états connected/not-connected/token-stale et bouton
  disconnect. Worker : 4 endpoints FastAPI (`POST /strava/connect`, `/strava/disconnect`,
  `GET /strava/webhook` validation challenge, `POST /strava/webhook` event dispatch).
  Webhook Strava déclenche un pull de l'activité créée/mise à jour/supprimée dans les
  secondes (sans polling). Mapping activité Strava → `activities` (mêmes colonnes que le
  transformer Garmin), `source = 'strava'` pour distinguer/dédupliquer si l'athlète a
  aussi Garmin → Strava actif côté Garmin Connect (cas fréquent). Dédup avec règle
  Garmin-priority (activité Strava ignorée si activité Garmin existe pour même
  user/sport dans ±5 min). Rate limiting app-wide (100 req/15 min, 1000/jour, via
  sliding window `strava_rate_limit.py`). Backfill 90 jours au connect (threaded
  async), token refresh transparent. Couvre activités de **toute marque qui synchro vers
  Strava** (Suunto/Coros/Wahoo/Apple Watch nativement ou via appli).
  
  Suite (hors scope V1) :
  - GPS samples/courbes détaillées pour activités Strava (`activity_samples` généralisation, E15.5).
  - Données wellness non-Garmin (Polar, E15.5).
  - Positionnement produit « Strava suffit » (E15.6).
  - **Dédup bidirectionnelle** : le dédup V1 est unidirectionnel (Strava → Garmin). Dans l'ordre
    courant Strava-then-Garmin, les deux lignes persévèrent. Ajouter un contrôle réciprocal dans
    le chemin Garmin (et vice-versa pour chaque source future E15.5) pour effacer un Strava/Polar
    existant quand un Garmin arrive. Scope : audit ordre arrivée, test multi-source, logique sync
    par source. Suite post-E15.1, avant multi-sources.
  - **Sécurisation webhook Strava (déauth + rate-limit DoS + thread exhaustion) — neutralisée
    par la pause (2026-07-26)** : l'endpoint `POST /strava/webhook` accepte TOUS les events
    (create/update/delete/deauth) sans HMAC signature ni vérification JWT. Trois vecteurs
    critiques : (1) POSTer `{authorized: 'false'}` supprime entièrement les credentials Strava
    de la victime ; (2) des events `create`/`update` forgés consomment la budget app-wide
    rate-limit (100 req/15 min, 1000/jour) pour TOUS les utilisateurs, causant une DoS
    silencieuse du backfill/webhook/token-refresh ; (3) chaque POST lance un unbounded daemon
    thread sans rate-limiting endpoint.
    **Traitement retenu** : `_require_strava_enabled()` fait répondre `404` aux 4 routes Strava
    tant que les secrets `STRAVA_*` sont absents — sur la prod actuelle (Strava en pause, pas de
    secrets) les trois vecteurs deviennent inatteignables, sans dépendre d'une allowlist au
    reverse-proxy. L'action owner « IP allowlisting Nginx » est donc **annulée**.
    **⚠️ À rouvrir si Strava est réactivé un jour** : dès que les secrets sont posés, les routes
    redeviennent live et les trois vecteurs reviennent — il faudra alors l'IP allowlisting Nginx
    (plages d'IPs webhook Strava) et/ou un rate-limit d'endpoint + borne sur les threads, AVANT de
    créer la souscription webhook. Spec technique détaillée en section E15.1 du spec design
    (webhook trust-model).
  - **TSS null pour activités Strava** : la transformation supporte HR-based TSS via
    `fc_max_bpm`/`ftp_watts` du profil, mais le call site ne passe pas ces paramètres — TSS reste
    null en V1 (décision scope validée). Conséquence : athlète Strava-seul a charge d'entraînement
    invisible au coach (CTL/ATL/TSB ignorent ces activités). Plumbing existe, c'est un petit
    wiring. Suite rapide post-V1 dès que readiness/briefing pour Strava devient prioritaire.
  - **Pas de banner confirmation/erreur OAuth** : route callback redirige vers `/profile?strava=connected`
    ou `?strava=error`, mais `app/(app)/profile/page.tsx` n'lit pas les `searchParams` — succès
    visible indirectement (card change), but erreur silencieuse. À câbler sur un toast/banner visible.
  - **`StravaDisconnectButton` sans loading/error state** : `disconnectStrava()` s'exécute async
    sans indicateur pending ni feedback d'erreur. À ajouter skeleton/disabled state pendant l'appel.
  
  Action owner — **⏸️ SANS OBJET tant que Strava est en pause** (aucune action à faire ;
  liste conservée pour une éventuelle réactivation) :
  
  **SETUP** (avant merge E15.1 pour que la merge ne break pas) :
  - Créer l'application Strava API à https://www.strava.com/settings/api pour obtenir
    `client_id`/`client_secret`. Définir « Authorization Callback Domain » au domaine apex
    de l'app (ex. `garmin-training-ia.vercel.app` — Strava n'accepte que le domaine nu).
  - Ajouter les secrets `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_WEBHOOK_VERIFY_TOKEN`
    (string aléatoire que vous générez une fois) au worker (`.env`/UNRAID `docker-compose.prod.yml`)
    et `STRAVA_CLIENT_ID` à Vercel (même valeur que le worker, non-secret).
  
  **APRÈS DEPLOY WORKER** (immédiatement, merge-coupled) :
  - Créer une fois la souscription webhook app-wide en POSTant à
    `https://www.strava.com/api/v3/push_subscriptions` avec `client_id`, `client_secret`,
    `callback_url=https://garmin-sync.tellebma.fr/strava/webhook`,
    `verify_token=<STRAVA_WEBHOOK_VERIFY_TOKEN>` que vous avez défini.
  - **🚨 SÉCURITÉ (à refaire uniquement si Strava est réactivé)** : configurer IP allowlisting
    au reverse-proxy Nginx (Nginx Proxy Manager UNRAID) pour que seules les plages d'IPs webhook
    Strava publiques puissent POSTer à `/strava/webhook`. Aujourd'hui **sans objet** : sans
    secrets `STRAVA_*`, la route répond `404`. Redevient obligatoire **avant** de poser les
    secrets et de créer la souscription webhook.
- **E15.2 P2 — Garmin officiel** : évaluer Garmin Health/Activity API (webhooks push) —
  réservé au programme partenaire, validation B2B. La lib `python-garminconnect`
  actuelle ne fait que du polling non officiel.
- **E15.3 P1 — Sync on-demand — V1 livrée** (PR #64) : sync `activities_only`
  déclenchée automatiquement à l'ouverture de l'app (silencieuse) et via un bouton manuel,
  bridée par un garde-fou anti-spam atomique. Le claim (`UPDATE ... RETURNING` via la RPC
  `try_claim_garmin_sync` SECURITY DEFINER) sur `garmin_credentials.last_sync_trigger_at`
  garantit qu'au plus une sync part par fenêtre (auto 30 min, manuel 5 min) et que deux
  ouvertures concurrentes n'en déclenchent qu'une. La sync tourne en thread daemon
  (réponse immédiate) et le gate porte sur la tentative, pas sur le succès. Chaîne :
  `SyncNowButton` → `triggerGarminSync` → `POST /garmin/sync` (JWT) → `run_ondemand_sync`.
  Reste à explorer : afficher « dernière synchro il y a X min » via `last_sync_at` (la copy
  cooldown actuelle dérive de `retry_after_seconds`).
- **E15.4 P0 — Pull au connect/reconnect Garmin — V1 livrée** : `start_connect_flow` et
  `resume_connect_flow` déclenchent désormais `_trigger_initial_sync(user_id)` après un
  `connected`. La sync tourne dans un thread daemon (réponse `connected` immédiate, pas de
  blocage de la Server Action) et réutilise `run_sync_for_user`, qui fait un backfill 90j au
  premier connect et un delta court au reconnect. L'échec de sync ne casse pas le connect
  (le cron rattrape) et le statut reste observable via `garmin_credentials.last_sync_status`.
- **E15.5 P2 — Données montre au-delà de Garmin, quand une API le permet** (volet Polar/wellness
  **non concerné par la pause Strava** ; en revanche « les activités passent par Strava » ne tient
  plus tant que E15.1 est désactivée — un athlète non-Garmin n'a aujourd'hui aucune source) :
  Strava (E15.1) couvrait les activités de quasi toutes les marques, mais pas le wellness. Pour
  les athlètes non-Garmin, brancher les APIs officielles qui exposent sommeil/HRV/FC
  repos quand elles existent en self-service :
  - **Polar AccessLink** : OAuth2 officiel, gratuit, en self-service (pas de programme
    partenaire) — sommeil, FC repos, activité continue. Candidat le plus réaliste après
    Strava ; même forme d'intégration que Garmin (credentials chiffrés, transformer dédié,
    cron ou webhook selon dispo).
  - **Coros / Wahoo** : API cloud existante mais réservée à un programme partenaire
    (validation B2B, délais) — pas de self-service, à réévaluer si un partenariat devient
    accessible. Pas de développement tant que l'accès n'est pas obtenu.
  - **Suunto** : pas d'API personnelle officielle solide ; dépend de Strava (E15.1) pour
    les activités, aucune source fiable pour le wellness à ce jour.
  - **Apple Watch** : aucune API cloud (les données vivent dans HealthKit sur l'iPhone) ;
    nécessiterait une appli compagnon ou un export tiers (ex. Health Auto Export vers un
    webhook) — hors scope tant qu'aucun athlète beta n'est demandeur.
  - Prérequis modèle de données : `activities`/`daily_metrics`/`sleep`/`hrv` ont déjà
    `user_id` mais sont pensées Garmin-only implicitement (un seul `garmin_credentials`
    par user) — généraliser vers un concept de « source » par table
    (`source: garmin|strava|polar`) avant d'ajouter une 2e source de wellness, pour
    éviter les collisions si un athlète a plusieurs sources actives.
  - Statut : aucune marque hors Garmin n'a d'implémentation ; à prioriser seulement s'il
    y a une demande beta concrète (aujourd'hui l'owner + tous les amis beta sont sur
    Garmin, cf profil onboarding).
- **E15.6 P2 — Positionnement produit : Strava suffit, la montre est optionnelle — ⏸️ EN PAUSE**
  (sans objet tant que Strava est désactivé : le message promettrait une source indisponible) :
  message à faire apparaître dans l'onboarding et sur `/profile` (écrans connexion
  Garmin/Strava) pour ne pas laisser croire qu'une montre compatible est requise pour
  utiliser l'app :
  - **Strava = base suffisante pour démarrer**, quelle que soit la marque de montre (ou
    même sans montre — appli téléphone) : couvre les activités et donc le plan/charge
    d'entraînement (CTL/ATL/TSB reposent sur les activités, pas sur le wellness).
  - **Connecter une montre compatible (Garmin aujourd'hui, Polar en E15.5) est une
    option en plus**, pas un prérequis : elle débloque des métriques avancées
    (sommeil, HRV, FC repos, composition corporelle) qui affinent le readiness/briefing
    quotidien mais ne conditionnent pas la génération du plan.
  - Éviter toute UI qui bloque ou dégrade l'usage si seul Strava est connecté ; un badge
    « débloquer le suivi récupération avancé » côté profil suffit, pas un mur.
  - Impact copy : écran de connexion (`/profile/garmin` et futur `/profile/strava`),
    onboarding step connexion source de données, et toute bulle explicative HRV/sommeil
    qui suppose aujourd'hui implicitement une source Garmin.

## Coaching sportif / performance

Objectif produit : les recommandations doivent se rapprocher d'un vrai coach
sportif, pas seulement d'un générateur de séances. Le système doit observer
l'historique, identifier les tendances, expliquer les risques et proposer des
ajustements concrets.

### EPIC E9 — Cockpit de performance et suivi longitudinal

**Priorité : P0 — Statut : en cours**

Regrouper les données Garmin, le plan et le ressenti de l'athlète dans un cockpit
qui répond chaque semaine à quatre questions : qu'est-ce qui a été réalisé,
comment la charge a été assimilée, où l'athlète progresse et quelle décision
prendre ensuite.

- **E9.1 P0 — Cockpit hebdomadaire — V1 livrée** : prévu vs réalisé, charge, durée,
  distance, dénivelé, assiduité, répartition par zones et équilibre intensité/récupération.
  Voir « Statut incrément 1 » ci-dessous (E9.1 V1). Reste-à-faire suivi via E9.4/E9.5/E9.6.
- **E9.2 P0 — Feedback subjectif — V1 livrée** : RPE post-séance, fatigue, douleurs,
  courbatures et humeur ; calcul de charge session-RPE et comparaison entre difficulté
  prévue et ressentie. Voir « Statut incrément 1 » ci-dessous (E9.2 V1).
- **E9.3 P1 — Récupération individualisée — V1 livrée** (PR #67) : baselines
  personnelles (médiane glissante 28j) pour HRV, FC repos, sommeil, stress et Body
  Battery, avec tendance orientée physiologiquement, confiance par couverture de données
  et fraîcheur. Module worker pur `recovery_baselines.py` matérialisé au sync (table
  `recovery_baselines`, RLS select-own, pattern E7). Le briefing score le readiness contre
  ces baselines (repli sur seuils absolus si confiance faible/absente, `readiness_score`
  inchangé) et le cockpit `/stats` expose un panneau `RecoveryPanel` en langage prudent
  (jamais de diagnostic). Suites notées : `sleep_excellent` encore en seuil absolu,
  gating confiance de la FC repos, affichage « dernière synchro… ».
- **E9.4 P0 — Progression par discipline** (remontée P0 le 2026-06-28) : détection de
  progression, stagnation, régression ou charge mal assimilée, discipline par discipline.
  **Spec écrite le 2026-07-26** : `docs/superpowers/specs/2026-07-26-e9.4-progression-discipline-design.md`
  (le backlog affirmait à tort « spec+plan prêts » : il n'existait qu'une section d'objectifs
  dans le design E9, ni spec dédiée ni plan). Plan d'implémentation à écrire.
  Correctifs de périmètre issus de l'inventaire des données réelles :
  - **La branche puissance vélo est non calculable** — 0 activité sur 29 porte une puissance
    (pas de capteur). FTP, puissance à FC comparable, NP, IF et VI sortent du périmètre tant
    qu'aucun capteur n'est ajouté ; ce n'est pas une omission mais une donnée inexistante.
  - `fc_max_bpm`, `vma_kmh`, `ftp_watts`, `css_per_100m_s` sont **NULL sur les 2 profils** →
    aucun filtre d'intensité en `% de FC max` n'est possible ; la spec le remplace par une
    garde sur l'écart de FC médiane entre fenêtres. Voir l'item « fc_max / VMA jamais
    remontés » ci-dessous.
  - Approche retenue : facteur d'efficacité (vitesse ajustée à la pente ÷ FC) et tendance sur
    médianes 28 j contre 62 j, croisée avec le CTL Banister pour distinguer stagnation et
    charge mal assimilée. L'appariement de parcours répétés (via la bbox de la PR #111) est
    noté comme suite.
  - Frontière : `discipline_level.py` (E13.2) couvre déjà le **niveau observé** (volume,
    régularité, TSS) ; E9.4 apporte la dimension **efficacité**, pas un doublon.

- **E9.5 P1 — Analyse avancée d'activité** : tours/intervalles, temps en zones,
  puissance normalisée, IF/VI, D+/D-, carte GPS et métriques Garmin spécialisées
  lorsqu'elles sont disponibles.
- **E9.6 P2 — Préparation objectif** : adéquation de l'entraînement aux exigences
  de la course, évolution de la préparation, stratégie de pacing et priorités de
  la semaine.

#### fc_max / VMA jamais remontés de Garmin — V1 livrée (découvert le 2026-07-26)

Découvert pendant la spec E9.4 : `fc_max_bpm` et `vma_kmh` étaient NULL sur tous les profils
depuis toujours, alors que le cron `profile_sync` réussissait. **Cause : deux hypothèses fausses
sur la forme des réponses Garmin**, pas un problème de capteur.

- `/userprofile-service/userprofile/user-settings` **imbrique les champs sous `userData`** —
  `garminconnect` fait lui-même `settings["userData"].get("measurementSystem")`. Le code lisait
  `userMaxHr` et `functionalThresholdPower` au niveau racine, donc toujours `None`.
- `/metrics-service/metrics/maxmet/daily/{start}/{end}` est un endpoint de **plage de dates** :
  il renvoie une **liste** d'entrées journalières, la VO2max nichée sous `generic`. Le code
  appelait `.get("vo2MaxValueRunning")` comme sur un dict plat.
- **Les tests ne pouvaient pas le voir** : ils mockaient un `user_profile` plat et un
  `max_metrics` dict, encodant la même hypothèse que le code. Leçon à retenir — un test qui
  mocke la forme supposée du payload ne prouve rien sur l'API réelle.
- Corrigé : lecture tolérante aux deux niveaux et aux formes inattendues (ce code tourne dans le
  cron et doit dégrader vers « aucune valeur écrite » plutôt que lever, car `_transform_profile`
  est appelé hors du `try/except` gardant les appels API), plus un log de la **forme** des
  payloads (clés uniquement, jamais les valeurs — ces payloads portent des données personnelles).
- **À vérifier après le prochain passage du cron** : les logs `profile-sync payload shapes`
  donnent la vérité terrain. Si `fc_max_bpm` reste NULL, le repli est de déduire la FC max de
  `max(activities.hr_max)` (51 activités renseignées, max observé 215 bpm — à filtrer des
  artefacts de capteur).
- `ftp_watts` restera vide pour un athlète sans capteur de puissance : c'est **correct**.
  `css_per_100m_s` n'est toujours **pas implémenté** dans `_transform_profile` — reste à faire.

Statut incrément 1 :

- E9.1 V1 : `/stats` devient un cockpit filtrable sur 7, 28 et 90 jours et par
  discipline, avec prévu/réalisé, assiduité, durée, TSS, activités hors plan,
  détail hebdomadaire et lecture coach déterministe.
- E9.2 V1 : migration RLS `activity_feedback`, saisie post-séance du RPE, fatigue,
  courbatures, douleur, humeur et difficulté perçue, plus calcul session-RPE et
  agrégation dans le cockpit.
- Suite immédiate : consommer le feedback subjectif dans le briefing et les
  ajustements, puis ajouter les baselines de récupération E9.3.

Garde-fous : aucune métrique isolée ne doit être présentée comme un diagnostic ou
une prédiction de blessure. Les recommandations combinent charge externe, charge
interne, tendance individuelle et ressenti, tout en indiquant les données absentes.

Spec et critères d'acceptation :
`docs/superpowers/specs/2026-06-19-e9-performance-cockpit-design.md`.

### EPIC E11 — Chat coach conversationnel (demande owner 2026-05-21)

**Priorité : P1 — Statut : lots A + B livrés (PR #206), livrés désactivés**

Donner à l'athlète un interlocuteur : poser une question en français sur son
entraînement (« pourquoi je suis rincé cette semaine ? », « je peux décaler ma
sortie longue ? ») et obtenir une réponse qui s'appuie sur ses propres données.

Approche retenue : **tool calling**, pas d'injection du contexte complet. Le LLM
demande les données dont il a besoin, outil par outil. Décidé pour deux raisons :
le coût (on ne paie que ce qui est lu) et la minimisation RGPD (une question sur
le sommeil ne fait pas sortir les tracés GPS). Le chat vit dans le **worker**, qui
réutilise les loaders existants de `coach/briefing.py`, le rate-limit atomique,
le suivi `llm_usage` et les feature flags.

Garde-fou n°1 — **cloisonnement des données**. Le worker attaque Supabase en
service role, donc RLS est court-circuité : aucun outil n'expose `user_id` dans
son schéma JSON, l'identité vient du JWT vérifié. Test d'évasion de tenant
obligatoire à chaque ajout d'outil.

Garde-fou n°2 — **coût borné côté serveur, jamais dans le prompt**. Quota exprimé
en dollars et non en appels ($1,50/mois/athlète, $20/mois global avec coupure
automatique), 5 tours de tool calling maximum, historique tronqué à 8 messages,
allowlist de modèles (luna $0,20/$1,20 contre sol $5/$30, soit ×25 sur une simple
erreur de configuration).

- **E11.A P1 — Socle chat — V1 livrée (PR #206)** : tables `coach_conversations` /
  `coach_messages` avec RLS, RPC `coach_activity_profile` et `coach_llm_spend_usd`,
  module `worker/src/garmin_sync/coach/chat/` (outils, handlers, agent, store,
  budget), endpoint `POST /coach/chat`, page `/coach` + Server Action + entrée de
  navigation. 57 tests.
- **E11.B P1 — Sécurité et budget — V1 livrée (PR #206)** : indissociable du socle.
  Injection de l'identité depuis le JWT, kill switch `chat_enabled`, quotas en
  dollars, allowlist de modèles, plafonds de tours et d'historique.
- **E11.C P1 — Réponses en streaming** : le chat répond aujourd'hui d'un bloc après
  plusieurs secondes. Le streaming SSE impose un **Route Handler Next.js** (les
  Server Actions ne savent pas streamer) — entorse assumée à la convention du
  projet. Estimé 1-2 j.
- **E11.D P2 — Export du compte-rendu** : le markdown est déjà stocké en base ;
  générer le document à la demande. **Décision owner (2026-08-21) : PDF seul, via
  WeasyPrint.** Le DOCX (qui imposerait Pandoc, ~250 Mo sur l'image worker) n'est
  ajouté que si le besoin utilisateur se manifeste. Estimé 2 j.
- **E11.E P2 — Observabilité fine** : coût et latence par conversation, taux de
  tours de tool calling saturés, questions restées sans réponse. Estimé 0,5 j.

⚠️ **Trois actions owner avant activation** (le flag est créé à `false`) :
appliquer la migration (automatique au merge sur `main`), **re-puller l'image
worker sur UNRAID**, puis basculer `chat_enabled` à `true`.

⚠️ Si le prompt caching est activé un jour, corriger `coach/llm_pricing.py` en même
temps : il ne modélise pas l'input mis en cache (« on sur-compte légèrement
l'input ») et les alertes budget se déclencheraient à tort.

Specs : `docs/superpowers/specs/2026-08-19-e11-chat-coach-faisabilite.md` et
`docs/superpowers/specs/2026-08-19-e11-chat-couts-garde-fous.md`.

### P0 — Recommandations sportives sourcées et auditables

- Formaliser un référentiel de règles coach avec niveau de confiance, domaine
  d'application et sources scientifiques ou consensus d'entraînement.
- Séparer clairement les recommandations robustes (progressivité de charge,
  alternance intensité/récupération, sommeil/HRV comme signal de prudence) des
  hypothèses à faible confiance.
- Ajouter dans le worker une trace `evidence_key` ou `rule_id` sur les décisions
  importantes : allègement, repos conseillé, garde-fou séance dure, progression
  hebdomadaire limitée.
- Côté UI, afficher une explication simple plutôt qu'une citation académique brute :
  "on protège la récupération car charge + HRV sont défavorables".
- Critère coach : toute recommandation impactant charge, intensité ou repos doit
  être justifiable par une règle lisible et reliée à une source ou un principe
  d'entraînement reconnu.
- Suite : créer `docs/superpowers/specs/coach-evidence.md` avec les règles V1,
  leurs sources, leurs seuils et leurs limites.

### P0 — Revue des activités précédentes avant recommandation — V1 livrée

- Analyser les 7, 28 et 90 derniers jours avant de générer ou ajuster une séance.
- Détecter : charge récente, régularité, dérive cardio, séances manquées, séances
  trop intenses, longues sorties, pics de D+, fatigue accumulée, reprise après pause.
- Sortie attendue côté app : "Ce que ton coach retient de tes dernières activités"
  avec 3-5 constats actionnables, pas un résumé brut Garmin.
- Sortie attendue côté worker : objet typé `activity_review` consommable par
  `/coach/daily-briefing`, `/coach/generate-plan` et `/coach/ensure-sessions`.
- Critère coach : aucune recommandation importante ne devrait ignorer ce qui vient
  d'être réellement fait par l'athlète.
- Statut V1 : intégré au briefing quotidien via `activity_review` avec signaux de
  charge récente, grosse séance, reprise après pause, régularité, D+ et déséquilibre
  de disciplines.
- Statut V1 action 2 : `activity_review` est maintenant réutilisé dans
  `/coach/generate-plan`, `/coach/ensure-sessions` et `/coach/regenerate-session`.
- Suite : enrichir les règles avec une comparaison prévu vs réalisé sur plusieurs
  séances, pas seulement la dernière activité.

### P0 — Recommandations coach contextualisées — V1 livrée

- Transformer le briefing quotidien en vraie décision coach : maintenir, alléger,
  remplacer par récupération, déplacer une séance, ou ajouter endurance facile.
- Donner une justification courte : "pourquoi aujourd'hui", "ce qu'on protège",
  "ce qu'on cherche à développer".
- Inclure des consignes terrain : intensité, durée, RPE, zones, nutrition/hydratation
  si séance longue, signaux d'arrêt si fatigue.
- Critère coach : la recommandation doit être actionnable sans relire tout le plan.
- Statut V1 : le briefing expose `coach_recommendation` avec une action claire
  (`maintain`, `ease`, `rest`, `caution`), un rationnel et une consigne terrain.

### P0 — Structure réaliste des séances générées

- Corriger les règles d'échauffement et de retour au calme pour qu'elles soient
  proportionnelles à la durée, au sport et au type de séance.
- Ne jamais générer un workout structuré pour un jour de repos : repos = pas
  d'échauffement, pas de corps de séance, pas de retour au calme.
- Éviter les séances où échauffement + retour au calme prennent une part excessive
  du temps total. Exemple à corriger : 45min vélo avec 15min échauffement, 18min
  de travail réel et 12min retour au calme.
- Définir des bornes coach :
  - récupération courte : échauffement minimal ou progressif intégré au bloc facile ;
  - endurance : bloc principal majoritaire ;
  - seuil/intervalles : échauffement suffisant, mais le travail ciblé reste central ;
  - long : échauffement/retour au calme inclus dans la progressivité, pas isolés de
    façon artificielle.
- Ajouter une validation post-LLM côté worker : durée totale proche de la cible,
  ratio minimum de travail principal, et rejet/réparation des structures absurdes.
- Adapter le prompt OpenAI et les tests `workout_schema` / `openai_client`.
- Critère coach : une séance doit ressembler à ce qu'un entraîneur ferait faire sur
  le terrain, pas à un découpage fixe imposé par le format JSON.
- Statut V1 : le worker ignore les jours de repos et les séances sans durée positive,
  le prompt LLM interdit les découpages fixes irréalistes, et `Workout` rejette les
  séances dont le corps principal représente moins de 55% ou dont la durée totale
  s'éloigne trop de la cible.
- **Régression (2026-06-21, retour owner) — corrigée (E13.1 V1)** : les séances étaient
  systématiquement trop courtes et irréalistes (ex. sortie vélo d'endurance à 45min au lieu
  de 1h30-3h). Corrigé via `coach/duration_bounds.py` : bornes plancher/plafond réalistes par
  `(discipline, type, phase)` (vélo endurance base 90-180min, long base 120-210min, etc.,
  taper→peak), clampées dans le planner par `clamp_duration_to_bounds`. Couvert par
  `tests/coach/test_duration_bounds.py`.
  - Suite éventuelle : vérifier que la charge hebdo agrège bien ces durées crédibles et
    étendre les cas de tests `workout_schema` / `openai_client` par discipline et phase.
- **Régression (2026-06-29, logs prod) — corrigée (PR #76, mergée 2026-07-02)** : la validation post-LLM (E13.1)
  rejetait massivement les workouts (`warmup exceeds cap`, `main work below 80/90%`,
  `duration too far from target`) et faisait **échouer durement** la génération — un seul
  tirage invalide laissait la séance sans `workout` (NULL), le cron suivant ré-échouant
  pareil. Causes : (1) le prompt ne communiquait pas les bornes chiffrées que le validateur
  applique (le petit modèle volait à l'aveugle) ; (2) aucun retry. Corrigé sans assouplir les
  garde-fous : `describe_session_envelope` injecte l'enveloppe numérique exacte de la séance
  dans le prompt, et `generate_workout_for_session` ré-essaie avec feedback correctif
  (`openai_max_attempts`, défaut 3) avant d'échouer. Couvert par `test_openai_client.py` /
  `test_workout_schema.py`.
- **Repos = repos (UI) — V1 livrée (E13.4)** : un jour de repos affiche un message de
  repos clair côté briefing / `/today` / `/plan`, **pas un compte rendu ni une structure de
  séance**. Variante repos de `SessionCard` sur `/plan`, masquage badge readiness + revue
  d'activités dans `BriefingCard`, et wording worker `format_explanation_md` adapté au repos.

### P1 — Détection des signaux de progression et stagnation

- Suivre l'évolution de FTP/VMA/FC max estimée, allure à FC constante, puissance
  normalisée, TSS hebdo, CTL/ATL/TSB, sommeil/HRV.
- Détecter plateau, sous-entraînement, surcharge, manque de récupération, discipline
  faible qui ne progresse pas.
- Reco coach : "on augmente le volume", "on garde la charge", "on ajoute du seuil",
  "on réduit l'intensité cette semaine".
- Les **courses passées** comptent comme jalons de référence dans ces signaux (temps, splits,
  écart à l'objectif) — voir E23.4.

### P1 — Analyse discipline par discipline

- Swim : régularité, volume, focus technique, endurance continue vs séries.
- Bike : puissance/FTP, D+, longues sorties, tempo/seuil, fatigue résiduelle.
- Run : progressivité, risque blessure, intensité trop fréquente, allure/FC.
- Brick : pertinence à l'approche de la course, charge cumulée, placement dans la semaine.

### P0 — Adapter le plan au niveau par discipline (E13.2)

- **V1 livrée (PR #75, mergée 2026-07-02)** : gaps A + B — niveau effectif par discipline
  dans la régénération de séances, biais progressif de volume vers la discipline faible,
  garde-fou ramp cap hebdo par sport, rebond post-deload autorisé au-delà du cap.
- **Problème principal** : le niveau par discipline est déjà déclaré par l'athlète à
  l'onboarding, mais cette métrique est **insuffisamment prise en compte** dans la
  génération du plan et des recommandations. La première action est de la brancher
  réellement sur le moteur (planner + prompt LLM + ajustements), pas d'inventer une
  nouvelle donnée.
- Croiser ce niveau déclaré avec l'historique réel (volume, allure/puissance,
  régularité, progression) pour le confirmer/affiner.
- Adapter la répartition de volume et de charge : sécuriser/maintenir la discipline
  forte, investir davantage sur les disciplines faibles sans créer de surcharge.
- Ajuster intensité et progression discipline par discipline plutôt qu'un plan uniforme.
- Critère coach : le plan doit refléter que l'athlète n'a pas le même niveau dans les
  trois disciplines.
- Cas owner confirmé : fort en vélo, plus faible en natation et en course à pied.

### P1 — Séances de mobilité / renforcement dans le plan (E13.3)

- Intégrer des séances de mobilité, souplesse et renforcement (prévention blessure,
  prehab), pas uniquement nage/vélo/course.
- Les placer intelligemment : jours faciles, autour des grosses séances, en complément
  sans alourdir la charge globale.
- Adapter durée et contenu au niveau de l'athlète et à la phase.
- Critère coach : un vrai plan triathlon inclut du travail de mobilité/renfo, pas
  seulement les trois disciplines.

### P1 — Activités hors triathlon (musculation, marche, yoga…) (demande owner 2026-06-28)

- **Demande owner** : prendre en charge les activités autres que nage/vélo/course —
  **musculation** en premier, mais aussi marche, randonnée, yoga, etc. — pour que la pratique
  réelle de l'athlète soit reflétée.
- **Bonne nouvelle — l'ingestion fonctionne déjà** : `_normalize_sport`
  (`worker/src/garmin_sync/transformers/activities.py`) mappe les 5 sports canoniques
  (swim/bike/run/brick/race) et **retourne les sports inconnus tels quels** (`strength_training`,
  `walking`, `hiking`, `yoga`…). La colonne `activities.sport` n'a **aucune contrainte `CHECK`**,
  donc ces activités sont déjà stockées avec leur `typeKey` Garmin. Rien à ajouter côté sync.
- **Ce qui manque réellement** :
  1. **Charge / fatigue (P1, coach)** : ces activités n'entrent pas dans la distribution TSS
     swim/bike/run et `compute_tss` ne les modélise pas. Décider comment elles contribuent à la
     fatigue/charge (ex. charge via FC/durée pour la muscu, ou TSS estimé) pour que le briefing
     et les garde-fous récup tiennent compte d'une grosse séance de muscu la veille.
  2. **Affichage dédié (P2, polish — différé)** : labels FR lisibles + icônes par type
     (haltère pour muscu, etc.) à la place de l'icône générique, et métriques pertinentes
     (durée, FC, calories ; pas d'allure/distance pour la muscu). Recoupe le polish UX différé.
  3. **Prescription par le coach (lien E13.3)** : si le coach doit **prescrire** de la muscu/renfo
     dans le plan, c'est l'item « Séances de mobilité / renforcement dans le plan (E13.3) ».
     Le présent item couvre l'**observation** (ce que l'athlète fait déjà), E13.3 la **prescription**.
- **À cadrer à l'implémentation** : liste des types à supporter explicitement (vs « autre »
  fourre-tout), modèle de charge pour la muscu (pas de puissance/allure), et si on filtre/groupe
  les « autres activités » dans `/history` et `/stats`.
- **Priorité au sein de l'item** : le volet **charge/fatigue** (P1) prime ; l'affichage dédié
  (P2) suit la lentille polish différée.
- **Critère produit** : une séance de musculation faite par l'athlète apparaît dans l'historique
  avec un rendu correct et est prise en compte par le coach pour la récupération du lendemain.

### P1 — Charge musculaire dans les ajustements coach (entraînement concurrent) (demande owner 2026-06-28)

- **Idée owner** : une séance de muscu ciblant un groupe musculaire (ex. **jambes**) doit
  influencer les séances suivantes qui sollicitent les mêmes muscles (grosse sortie vélo,
  CAP). Pas en réécrivant le plan, mais en **suggérant** un allègement (choix owner :
  Accepter/Ignorer, pas de réécriture auto).
- **Faisabilité (vérifiée)** : `get_activity_exercise_sets(activity_id)` de
  `python-garminconnect` (endpoint `/activity/{id}/exerciseSets`) expose les **séries** d'une
  séance de force : **catégorie d'exercice** (`SQUAT`, `BENCH_PRESS`, `DEADLIFT`…), reps,
  poids, volume. Le worker **ne l'appelle pas encore** (seulement `get_activity_details`).
  ⚠️ Garmin ne donne **pas** les muscles en clair → **table de mapping
  `catégorie → groupes musculaires`** à maintenir côté worker (squat → jambes/fessiers, etc.).
- **À faire** :
  - **Worker / ingestion** : appeler `get_activity_exercise_sets` pour les activités de type
    force, stocker les séries (table dédiée ou `raw`/`activity_samples`), dériver les groupes
    musculaires via le mapping. Dépend de l'item « Activités hors triathlon » (charge muscu).
  - **Coach** : estimer une **charge musculaire récente par groupe** (ex. jambes) et l'injecter
    dans le garde-fou **`next_session_adjustment`** existant — grosse séance jambes récente +
    séance vélo/CAP dure planifiée → proposer un allègement (Accepter/Ignorer), comme les
    garde-fous E9.
  - **Garde-fou** : suggestion uniquement, jamais de réécriture auto ; pas de diagnostic,
    cohérent avec les garde-fous E9.
- **À cadrer à l'implémentation** : granularité des groupes (jambes / haut du corps / core
  suffit-il ?), modèle de charge muscu (volume = reps × poids ? durée × RPE ?), fenêtre de
  récupération par groupe.
- **Lien** : recoupe « Activités hors triathlon » (ingestion) et E13.3 (prescription).
- **Critère** : après une grosse séance jambes, le coach **propose** (sans imposer) d'alléger
  la prochaine grosse sortie vélo/CAP.

### P2 — Carte musculaire (muscles sollicités) (demande owner 2026-06-28, polish UX différé)

- **Idée owner** : un graphique **« carte du corps »** montrant les muscles sollicités (sur une
  séance et/ou agrégé sur la semaine), façon apps de muscu, pour visualiser ce qui est travaillé
  et ce qui est négligé.
- **Dépend de** l'ingestion des `exerciseSets` + mapping `catégorie → muscles` (voir item
  « Charge musculaire dans les ajustements coach » ci-dessus).
- **P2** — relève de la **dataviz / polish UX** (lentille différée le 2026-06-28). À traiter
  **après** le volet coach.
- **À cadrer** : SVG carte musculaire (face/dos), échelle d'intensité par groupe, vue séance
  vs vue semaine.
- **Critère** : l'athlète visualise d'un coup d'œil quels groupes il a travaillés et lesquels
  sont négligés.

### P1 — Feedback post-séance — V1 livrée

- Après chaque activité, comparer prévu vs réalisé : durée, TSS, distance, D+,
  intensité, sport, respect de la séance.
- Afficher une note de coach : "bien exécuté", "trop intense pour l'objectif",
  "volume insuffisant", "séance à récupérer", "à ne pas compenser demain".
- Utiliser ce feedback pour ajuster les prochaines séances plutôt que générer un
  plan figé.
- Statut V1 : le briefing compare la dernière activité récente à la séance prévue
  du même jour (`last_session_feedback`) et applique un impact readiness en cas
  de séance trop intense, trop longue, jour de repos non respecté ou sport différent.
- Statut V1 action 2 : `activity_review` est utilisé dans `/coach/ensure-sessions`
  et `/coach/regenerate-session` pour enrichir le contexte LLM, et dans
  `/coach/generate-plan` pour alléger la première semaine en cas de signal de risque.

### P1 — Fiche activité coach dans l'historique

- Permettre d'ouvrir une activité depuis l'historique et d'obtenir une analyse
  complète, orientée efficacité de l'entraînement.
- Afficher les métriques clés disponibles : durée, distance, allure/vitesse,
  dénivelé positif/négatif, FC moyenne/max, zones cardio, puissance si disponible,
  cadence, calories, TSS/charge estimée, dérive cardio, intensité, régularité,
  segments montée/descente/plat et comparaison avec les activités similaires.
- Ajouter des graphes lisibles : profil d'altitude, fréquence cardiaque dans le
  temps, allure/vitesse, puissance, cadence, zones cardio, distribution d'effort et
  corrélation effort vs dénivelé.
- Produire une lecture coach : objectif probable de la séance, exécution réelle,
  points forts, points à corriger, risque fatigue/blessure, impact sur les prochaines
  séances.
- Donner des recommandations terrain pour les prochaines séances, par exemple :
  ralentir dans les montées, rester autour d'une cible cardio, mieux lisser l'effort,
  mieux gérer la nutrition/hydratation, ou conserver une intensité facile si la
  séance devait être de récupération.
- Comparer prévu vs réalisé quand une séance planifiée existe le même jour :
  durée, sport, intensité, charge, respect des blocs et dérive par rapport à
  l'objectif initial.
- Critère coach : l'utilisateur doit comprendre si l'activité l'a fait progresser,
  l'a fatigué inutilement, ou doit modifier la prochaine séance.
- Statut V1 : les activités de `/history` sont ouvrables via `/history/[id]`.
  La fiche affiche les métriques disponibles, une analyse coach déterministe,
  des recommandations pour les prochaines séances, la comparaison à la séance
  planifiée du même jour et une comparaison graphique avec les activités similaires.
- Statut V1 action 2 : le worker récupère les détails Garmin manquants via
  `get_activity_details`, stocke les samples dans `activity_samples`, et la fiche
  activité affiche les courbes temporelles quand les samples sont disponibles.
- Statut V1 action 3 : la fiche activité calcule désormais les zones cardio à partir
  des samples et segmente l'effort en montée / plat / descente avec distance, pente,
  FC moyenne et vitesse moyenne. Les recommandations coach utilisent ces signaux
  pour pointer une intensité trop élevée ou une montée prise trop haut en cardio.
- Statut V1 action 4 : la fiche activité détecte la dérive cardio entre première et
  seconde moitié, affiche l'évolution FC/vitesse et mesure la variabilité de vitesse
  par terrain pour signaler un pacing irrégulier.
- Statut V1 action 5 : la fiche activité relie les signaux détaillés aux prochaines
  séances planifiées et propose maintien, allègement, récupération active ou repos
  protégé selon le coût observé.
- Statut V1 action 6 : le briefing quotidien expose maintenant
  `next_session_adjustment` avec statut visible, séance ciblée et adaptation
  proposée avant toute modification réelle du plan.
- Statut V1 action 7 : les générations et régénérations de séance reçoivent le
  signal d'ajustement coach dans leur contexte LLM pour produire une séance plus
  facile quand les activités récentes rendent une séance dure risquée.
- Statut V1 action 8 : le briefing affiche des actions Accepter / Ignorer. La séance
  stockée n'est modifiée qu'après acceptation utilisateur, avec effacement du workout
  existant pour relancer une génération cohérente.
- Statut V1 action 9 : les acceptations/refus sont persistés dans
  `coach_adjustment_decisions`, et le briefing ne repropose plus le même ajustement
  pour une séance déjà traitée.
- Statut V1 action 10 : le profil expose maintenant l'historique des dernières
  décisions coach acceptées ou ignorées, avec la séance concernée, l'adaptation
  proposée et la date d'enregistrement.
- Statut V1 action 11 : le briefing applique un garde-fou explicite quand une
  séance dure tombe sur un signal de récupération défavorable (HRV, sommeil, TSB,
  charge récente ou feedback de séance), ce qui pousse l'ajustement vers une séance
  allégée avant d'empiler de l'intensité.
- Suite : enrichir ces garde-fous avec une analyse de progression hebdomadaire par
  discipline, en particulier pour limiter les hausses trop rapides en course à pied.

### P2 — Carte « Dernière activité » de /today : cliquable + micro-verdict coach (retour owner 2026-06-27, rétrogradé P2 le 2026-06-28 — polish UX différé)

- **Problème** : sur `/today`, la carte « Dernière activité » (`ActivityRow` dans
  `app/(app)/_components/activity-row.tsx`, rendue par `app/(app)/today/page.tsx`) est une
  info statique. Elle a un effet `hover:bg-accent/30` trompeur mais **n'est pas cliquable**
  et ne donne aucune lecture coach — elle n'apporte aujourd'hui qu'un récap brut
  (sport, date, durée·distance·TSS).
- **Plus-value retenue (owner) — cliquable + micro-verdict coach** :
  1. **Cliquable** : la carte devient un lien vers la fiche détaillée existante
     `/history/[id]` (analyse coach, courbes, comparaison prévu/réalisé), avec une
     affordance claire (chevron, focus clavier, `role`/`aria` corrects). Pas de nouvelle
     vue à créer — la fiche est déjà riche.
  2. **Micro-verdict coach inline** : afficher un retour rapide sur la carte (badge +
     phrase courte type « ✅ Bien exécuté — charge ok », « ⚠ Un peu long », « dérive
     cardio »), en **réutilisant la logique déjà calculée** (`last_session_feedback` du
     briefing et/ou `lib/coach/activity-analysis.ts`) plutôt que de recalculer.
- **À cadrer à l'implémentation** : d'où vient le verdict (réutiliser `last_session_feedback`
  du briefing déjà chargé sur `/today` vs un calcul léger dédié), et le comportement quand
  aucune séance n'était planifiée le même jour (verdict neutre/exécution seule, pas de
  comparaison prévu/réalisé forcée).
- **Critère produit** : depuis `/today`, l'utilisateur comprend en un coup d'œil si sa
  dernière activité s'est bien passée, et accède à la fiche complète en un clic.
- **Garde-fou coach** : le micro-verdict reste prudent (jamais un diagnostic), cohérent
  avec les garde-fous E9 (charge externe + interne + ressenti, pas de métrique isolée).

### P1 — Garde-fous santé/performance

- Détecter les progressions hebdo trop rapides, en particulier en course à pied.
- Éviter deux séances dures rapprochées si HRV/sommeil/TSB sont défavorables.
- Prévenir l'utilisateur quand le plan recommande repos ou récupération pour réduire
  le risque de blessure, avec une formulation coach claire.

### P2 — Objectifs de course plus coachables

- Ajouter une analyse spécifique de l'objectif : profil D+, durée probable, points
  critiques, exigences par discipline.
- Adapter les blocs d'entraînement : côtes, endurance longue, seuil, transitions,
  nutrition, pacing.
- Produire une note "priorités de la semaine" liée à la course.

### P2 — Reco hebdomadaire de coach

- Générer chaque début de semaine une synthèse : bilan semaine passée, objectif de
  la semaine, séance clé, point de vigilance, conseil récupération.
- Utiliser le ton d'un coach : concret, sobre, encourageant, jamais culpabilisant.

### P2 — Explicabilité du plan

- Pour chaque séance, afficher la raison sportive : développer l'endurance, absorber
  la charge, travailler discipline faible, préparer D+, entretenir la vitesse.
- Permettre à l'utilisateur de comprendre pourquoi une séance est allégée ou déplacée.

## Qualité / plateforme

### EPIC E18 — Console d'administration & ouverture au public

**Priorité : P1 — Statut : V1 livrée** (PR #90 console + flags + allowlist, #93 cron
`billing_sync` + format réel de l'API OpenAI, #95 lien Admin dans la nav, #105 fix
`admin_overview()` `jsonb_agg` order-by). E18.1 → E18.5 sont livrés ; seule la « Suite »
ci-dessous reste ouverte.

Vue `/admin` réservée à l'owner qui regroupe tout ce qui touche l'ouverture de l'app à
des utilisateurs externes : adoption, **coût IA réel**, **feature flags** (kill switch
IA, mode maintenance, inscription ouverte temporaire) et **gestion de l'allowlist**
depuis l'UI. Le besoin structurant côté finops : la conso de tokens IA n'est tracée nulle
part aujourd'hui (`openai_client.py` jette `resp.usage`), donc l'EPIC est en plusieurs
temps — instrumenter, puis afficher. Périmètre élargi le 2026-07-08 (feature flags +
allowlist UI + inscription ouverte, initialement en « Suite »). Spec :
`docs/superpowers/specs/2026-07-08-e18-console-admin-ouverture-publique-design.md`
(remplace `docs/superpowers/specs/2026-06-28-e18-admin-console-design.md`).

- **E18.1 P1 — Instrumentation conso LLM — V1 livrée** : nouvelle table `llm_usage` (un row par appel
  OpenAI, RLS deny-all), capture de `resp.usage` dans `openai_client.py`, tarif versionné
  en code (`MODEL_PRICING`) pour calculer `cost_usd`, helper `record_llm_usage` branché sur
  tous les sites d'appel LLM (séances + briefing). Best-effort : ne casse jamais la
  génération. Prérequis de E18.2/E18.3.
- **E18.1bis P1 — Vérité terrain OpenAI — V1 livrée** : table `openai_billing_snapshot`, cron worker
  quotidien (`billing_sync.py`) qui pull l'OpenAI Costs API (clé admin dédiée, worker-only)
  et affiche le coût facturé à côté du coût estimé par `llm_usage`.
- **E18.2 P1 — Agrégats admin — V1 livrée** : RPC `admin_overview()` `security definer` (garde via
  `is_admin_caller()`) renvoyant users (total + actifs 7j), activités (total + 7j), tokens
  + `cost_usd` estimé et facturé 7j, santé sync (succès/échecs derniers crons), série
  coût/jour 7j.
- **E18.3 P1 — Page `/admin` — V1 livrée** : route Next.js gardée par email owner, panneaux finops +
  feature flags + allowlist, graphe coût IA/jour (réutilise charts E14.1), UI dark
  existante.
- **E18.4 P1 — Feature flags — V1 livrée** : table générique `feature_flags` (expiration optionnelle
  évaluée à la lecture, pas de cron), flags `llm_generation_enabled` (kill switch),
  `maintenance_mode`, `public_registration_enabled` (bypass temporaire de l'allowlist à
  l'inscription, expiration obligatoire).
- **E18.5 P1 — Gestion allowlist UI — V1 livrée** : RPCs `admin_list/add/remove_allowed_email`,
  panneau d'ajout/liste/retrait. Le retrait bloque uniquement une future inscription, ne
  révoque pas un compte déjà actif (hors scope).
- **Suite (Todo séparés)** : détail par utilisateur, alerting/budget cap IA, multi-admin
  (flag `is_admin` généralisé), affichage du coût converti en €, bannissement d'un compte
  déjà actif, ciblage de feature flag par utilisateur.

### EPIC E19 — Lien cliquable vers l'historique depuis /today

**Priorité : P2 — Statut : V1 livrée** (PR #103)

Sur `/today`, la carte "Dernière activité" n'est pas cliquable alors que le même composant
(`ActivityRow`) l'est déjà sur `/history`. Fix ciblé : envelopper la carte dans un `Link`
vers `/history/[id]` (route déjà existante). Spec :
`docs/superpowers/specs/2026-07-12-e19-lien-derniere-activite-today-design.md`.

### EPIC E20 — Cols gravis sur la fiche activité

**Priorité : P2 — Statut : V1 livrée** (PR #103)

`col_crossings` (E9, 2026-07-08) a déjà un `garmin_activity_id`, permettant de lier les cols
franchis à une activité précise. Nouvelle section "Cols gravis" sur `/history/[id]` (nom +
altitude des cols franchis pendant cette activité), affichée uniquement si ≥1 col — widget
isolé avec son propre `Suspense` (pas dans le `Promise.all` bloquant de la page, cf. retour
owner sur "Mes cols"). Spec :
`docs/superpowers/specs/2026-07-12-e20-cols-gravis-fiche-activite-design.md`.

### EPIC E21 — Notifications de nouveautés (changelog interne)

**Priorité : P2 — Statut : V1 livrée** (PR #103 ; suite : PR #107 embarque
`docs/nouveautes.md` dans le bundle serverless Vercel)

Badge "nouveautés" (cloche) dans la nav, alimenté par un nouveau fichier éditorial
`docs/nouveautes.md` (distinct du `CHANGELOG.md` technique semantic-release) — 1-3 puces FR
par version. État lu/non-lu stocké sur `athlete_profiles.last_seen_changelog_version`. Rappel
de mise à jour ajouté à `CLAUDE.md`. Spec :
`docs/superpowers/specs/2026-07-12-e21-notifications-nouveautes-design.md`.

### EPIC E22 — Calques PNG partageables (story Instagram) (demande owner 2026-07-30)

**Priorité : P2 — Statut : V1 livrée (PR #119)**

Sur `/history/[id]`, section « Partager en story » qui génère un **sticker PNG** (fond
transparent par défaut) avec la trace GPS et les métriques principales, à superposer sur sa
photo dans Instagram / WhatsApp / Snapchat. Style validé par l'owner sur référence des calques
de partage Strava : composition **centrée et compacte**, sans marque tierce.

Cinq gabarits (tracé + métriques, métriques + tracé, profil + métriques, métriques seules,
tracé seul), deux formats (story 9:16, carré 1:1), trois fonds (transparent / dégradé /
sombre), cinq couleurs d'accent, 3 à 4 métriques sélectionnables selon le gabarit, titre et
signature désactivables. Export par téléchargement, ou feuille de partage native
(`navigator.share({ files })`) quand le navigateur le supporte.

Rendu 100 % Canvas côté client, sans nouvelle dépendance et sans fond de carte (les tuiles
externes « taint » le canvas et empêchent `toBlob()`). Spec :
`docs/superpowers/specs/2026-07-30-e22-calques-png-partage-activite-design.md`.

**Suite possible (Todo)** : coloration du tracé par métrique (FC / vitesse) comme sur la carte
MapLibre ; icône de sport dessinée sur le sticker (`Path2D`) ; bouton de partage direct depuis
la liste `/history` ; comparaison « vs sortie similaire » sur le calque.

#### E22.1 P2 — Calque multisport : distinguer les 3 disciplines (demande owner 2026-08-20)

**Statut : V1 livrée (PR #207)**

Livré : table `activity_segments` (une ligne par discipline et par transition, alimentée par
le worker depuis les activités enfants Garmin, marquée par `activities.segments_checked_at`
pour ne jamais ré-interroger deux fois la même épreuve) ; gabarit de calque « Par discipline »
(une ligne par discipline avec durée / distance / allure, plus le total sous la pile) ; tracé
GPS colorié discipline par discipline via le temps écoulé des points ; pictogrammes de
discipline dessinés en `Path2D`, désactivables. Le typeKey Garmin `multi_sport`, jusque-là non
reconnu, est désormais normalisé en `brick` comme `multisport`.

Reste ouvert : la décomposition n'a pas pu être vérifiée sur une vraie épreuve (aucun
multisport dans les données de dev) — les extracteurs acceptent plusieurs formes de payload
faute de pouvoir en confirmer une. À revalider sur le premier triathlon synchronisé.

Contexte d'origine :

Aujourd'hui le calque traite une activité multisport (triathlon / duathlon / aquathlon) comme
une sortie unique : `_normalize_sport` (`worker/src/garmin_sync/transformers/activities.py`)
écrase `multisport`/`transition` en un seul sport `brick`, et `buildStoryMetrics`
(`lib/share/story-layout.ts`) calcule des métriques globales sur cette ligne agrégée. Résultat
partagé : une distance et une allure moyennes qui mélangent nage, vélo et course — donc sans
signification pour l'owner comme pour ses lecteurs.

Objectif : sur une activité multisport, le calque **présente chaque discipline séparément**
(nage / vélo / course, plus les transitions), avec pour chacune ses propres métriques (durée,
distance, allure ou vitesse, FC moyenne), en plus du total de l'épreuve.

- **Données (prérequis)** : le modèle actuel n'a aucune notion de segment — `activities` porte
  une ligne par activité et `activity_samples` n'a pas de colonne discipline. Il faut ingérer
  la décomposition Garmin d'une activité multisport (activités enfants via `childIds` /
  `parentId`, ou à défaut les splits) et la persister : soit des lignes `activities` enfants
  rattachées au parent, soit une table `activity_segments` (ordre, sport, durée, distance,
  dénivelé, FC, allure). Décision à trancher en spec — l'option « activités enfants » recoupe
  la question déjà ouverte de savoir si le worker doit ou non compter ces enfants dans le TSS
  (risque de double comptage avec le parent).
- **Rendu du calque** : un gabarit « multisport » qui empile 3 blocs de métriques (un par
  discipline) plutôt que la grille 3-4 métriques actuelle ; le tracé GPS colorié par segment
  (une teinte par discipline) ; le total de l'épreuve conservé en en-tête. Contrainte E22
  inchangée : rendu 100 % Canvas côté client, pas de fond de carte (tuiles externes → canvas
  « tainted », `toBlob()` bloqué).
- **Option logos de discipline** (demande owner, activable/désactivable) : icône nage / vélo /
  course à côté de chaque bloc. Le composant React `app/(app)/_components/sport-icon.tsx`
  n'est pas réutilisable tel quel dans un canvas — dessiner les glyphes en `Path2D` (recoupe
  la « suite possible » E22 déjà notée) plutôt que charger un SVG externe.
- **Cas dégradés à couvrir** : activité multisport sans enfants exploitables (fallback sur le
  rendu agrégé actuel), enchaînement à 2 disciplines (duathlon / aquathlon), transitions
  absentes ou de durée nulle.

Dépendance : cet EPIC bénéficie au partage mais la décomposition par discipline sert aussi la
fiche `/history/[id]` et le coach (E9.4 progression par discipline) — la spec doit décider si
la donnée est produite pour le seul calque ou exposée plus largement.
### EPIC E24 — Exclure une activité de son historique (demande owner 2026-08-24)

**Priorité : P1 — Statut : V1 livrée (PR #209)** — spec
`docs/superpowers/specs/2026-08-24-e24-exclure-activite-design.md`, plan
`docs/superpowers/plans/2026-08-24-e24-exclure-activite.md`.

Cas vécu par l'owner le jour de sa course : compteur GPS du vélo lancé **en mode activité** en
plus de la montre, pour avoir les métriques sous les yeux pendant l'épreuve. Résultat : deux
activités pour un seul effort, donc TSS compté deux fois, volume gonflé, charge (CTL/ATL/TSB)
faussée, et une vue course qui additionne deux fois le même vélo.

Il faut pouvoir **retirer une activité** de son historique et de ses statistiques.

- **E24.1 P1 — Exclusion réversible plutôt que suppression sèche — V1 livrée** : une suppression physique
  serait **annulée au sync suivant** — l'activité existe toujours chez Garmin et l'upsert la
  recréerait. L'exclusion est donc portée par une colonne (`activities.excluded_at`) que le sync
  ne réécrit jamais : l'activité reste en base, cesse de compter, et peut être restaurée.
- **E24.2 P1 — L'exclusion vaut partout — V1 livrée** : charge et Banister, volumes, cockpit, briefing,
  revue d'activités, niveau par discipline, plan, chat coach, vue course, dernière activité de
  `/today`, historique. Un seul point d'entrée dans le code (helper de portée) pour que le filtre
  ne s'oublie pas au prochain écran.
- **E24.3 P1 — Bouton et restauration — V1 livrée** : depuis `/history/[id]`, bouton de suppression avec sa
  conséquence annoncée ; les activités exclues restent listables et restaurables depuis
  `/history` (filtre dédié), pour qu'une erreur ne soit jamais définitive.
- **E24.5 P1 — Recalcul automatique de la charge — V1 livrée (PR #210)** : supprimer une
  activité corrige le TSS du jour, donc CTL/ATL/TSB. Attendre le cron de 05:00 UTC afficherait
  une forme fausse à l'athlète qui vient précisément de corriger la donnée. L'app appelle donc
  `POST /coach/recompute-state` sur le worker juste après la suppression **et** la restauration.
  Best effort : si le worker ne répond pas, l'exclusion reste acquise, l'écran le dit et le cron
  rattrape.
- **E24.4 P2 — Détection de doublon (Todo)** : signaler deux activités qui se chevauchent (même
  créneau, même sport) et proposer d'en exclure une, au lieu d'attendre que l'athlète le
  remarque. La fenêtre de recouvrement de `dedup.py` (±5 min) est réutilisable telle quelle.

**Livré en V1** : colonne `activities.excluded_at` (+ `excluded_reason`) jamais réécrite par le
sync, RPC `set_activity_excluded`, helpers de portée `counted()` (worker) et `countedActivities()`
(front) appliqués à toutes les lectures qui alimentent une métrique, bouton de suppression avec
confirmation sur `/history/[id]`, onglet « Supprimées » et restauration sur `/history`.

### EPIC E23 — Vue course : détection, débrief et jalon de progression (demande owner 2026-08-24)

**Priorité : P1 — Statut : V1 livrée (PR #208)** — spec
`docs/superpowers/specs/2026-08-24-e23-vue-course-design.md`, plan
`docs/superpowers/plans/2026-08-24-e23-vue-course.md`.

Aujourd'hui une course n'existe que comme **objectif** (`race_goals` + séance `race` du jour J,
livrée par la PR #174). Une fois l'épreuve passée, elle redevient une activité d'historique
ordinaire : rien n'indique que c'était une course, le résultat n'est comparé ni à l'objectif ni
aux épreuves précédentes, et les données propres à la course (temps par segment, transitions,
classement officiel) n'existent nulle part.

Objectif : faire de la course un **objet de première classe** — détectée, tagguée, débriefée, et
prise en compte dans les progressions.

- **E23.1 P1 — Détection et tag « course » — V1 livrée** : au sync, si une activité tombe le jour d'une
  `race_goals.race_date` (fenêtre ±1 jour, cohérence sport/distance avec les `legs`), la rattacher
  à la course (`activities.race_goal_id` + flag `is_race`). Prévoir le tag **manuel**
  (marquer/démarquer une activité comme course depuis `/history/[id]`) et la création d'une course
  **rétroactive** pour une épreuve jamais saisie comme objectif. Cas multi-activités le même jour
  (triathlon découpé par Garmin en plusieurs fichiers + transitions) : les regrouper sous une seule
  course — recoupe la décomposition multisport d'E22.1.
- **E23.2 P1 — Page course dédiée — V1 livrée** : une vue distincte de la fiche activité standard
  (`/history/[id]` en mode course, ou `/history/race/[id]`) : bandeau épreuve (nom, lieu, date,
  discipline, distances par leg), temps total, **splits par segment** (natation / T1 / vélo / T2 /
  course à pied), allure et FC par segment, D+, **objectif vs réalisé**
  (`race_goals.target_time_seconds`), carte du parcours.
- **E23.3 P1 — Débrief coach de course — V1 livrée** : lecture coach spécifique à l'épreuve — ce qui a bien
  marché, points d'amélioration, gestion de l'allure et de la FC segment par segment, comparaison à
  la préparation réellement effectuée (charge, séances clés, affûtage), enseignements pour la
  prochaine course. Complété par un **ressenti athlète** (champ libre, comme le feedback
  post-séance) et des données subjectives non mesurées par la montre : nutrition, météo, matériel,
  incidents.
- **E23.4 P1 — La course compte dans les progressions — V1 livrée** : une course devient un **jalon de
  référence** — repère sur les courbes de progression (`/stats`, progression par discipline E9.4),
  comparaison entre deux épreuves de même format (« 2e triathlon S : −4 min, T1 −40 s »), et signal
  d'entrée pour la détection progression/stagnation. Le plan d'après-course doit en tenir compte
  (récupération post-épreuve, bascule vers l'objectif suivant).
- **E23.5 P2 — Stats externes de course (officielles ou non) — V1 manuelle livrée** : enrichir la vue avec ce que Garmin
  ne fournit pas — classement scratch et catégorie, temps officiels et temps de transition, dossard,
  nombre de partants, lien vers les résultats, photos. **V1 = saisie manuelle** d'un jeu de champs
  structurés ; **V2 = import** depuis les plateformes de chronométrage (Njuko, Sporkrono,
  ChronoRace, Livetrail, FFTri…) via URL de résultats ou API quand elle existe, derrière un
  adaptateur par fournisseur — aucune de ces sources n'est standardisée, donc périmètre à cadrer
  fournisseur par fournisseur.
- **E23.6 P2 — Vue « souvenir » / première course — V1 minimale livrée** : traitement éditorial particulier pour les
  épreuves marquantes, en premier lieu le **premier triathlon** — récit de la course, chiffres clés
  mis en avant, chemin parcouru depuis le début de la préparation (volume total, nombre de séances,
  progression par discipline), export partageable (recoupe E22 / E22.1).

**Cas d'usage de référence (owner)** : son premier triathlon — la vue doit **raconter** la course
autant que la mesurer.

**Livré en V1** : détection au sync + backfill (`garmin_sync.coach.race_tagging`,
`backfill_races`), tag manuel et course rétroactive (RPC `set_activity_race` /
`clear_activity_race`), page `/history/race/[id]` (splits, transitions, objectif vs réalisé,
débrief déterministe, comparaison à la course précédente, « chemin parcouru », badge
« Première course »), saisie des résultats officiels (`race_results`), badge Course dans
`/history` et widget « Mes courses » sur `/stats`.

**Suite (Todo)** :

- **E23.5 V2 — import automatique des résultats** depuis les plateformes de chronométrage
  (Njuko, Sporkrono, ChronoRace, Livetrail, FFTri) par URL de résultats, un adaptateur par
  fournisseur, alimentant les colonnes déjà en place.
- **E23.6 complet — récit de course et export partageable** (recoupe E22 / E22.1).
- **Repères de course dans les graphiques** Banister et volume (`ReferenceLine`), à traiter
  avec E14.
- **Action owner** : lancer `python -m garmin_sync.coach.backfill_races` sur le worker après
  déploiement pour rattacher les épreuves déjà passées.

### EPIC E17 — Déploiement automatisé des migrations Supabase

**Priorité : P1 — Statut : V1 livrée (auto-apply, sans gate)**

Avant E17 les migrations (`supabase/migrations/*.sql`) étaient appliquées **à la main**
dans le dashboard : aucune automatisation CI, pas de `config.toml`, pas de `db push`.
Ce pas manuel était un footgun récurrent — un merge qui ajoute une migration pouvait partir
en prod sans que le schéma soit à jour, cassant le worker (écriture sur colonne absente)
ou la fiche activité. Cas vécu : la migration `20260624000000_carto_gps.sql` (livrable A
cartes GPS) restée à appliquer manuellement après le merge de la PR #57.

Objectif : un merge sur `main` qui contient une migration l'applique de façon **tracée
et reproductible**.

- **E17.1 P1 — Job CI `supabase db push` sur `main` — V1 livrée** : workflow
  `.github/workflows/supabase-migrations.yml` (trigger `push main` + `paths
  supabase/migrations/**`), `supabase/setup-cli` → `supabase link --project-ref
  peiyrqplymdlmlpsbqzu` → `supabase db push` (idempotent), `concurrency` pour éviter deux
  push simultanés. Secrets : `SUPABASE_ACCESS_TOKEN`, `SUPABASE_DB_PASSWORD`. `config.toml`
  ajouté (`project_id`).
- **E17.2 — Gate `production` avec required reviewer — abandonnée (choix owner)** : owner a
  tranché pour l'**auto-apply** sur `main` (pas de pause/approbation manuelle avant DDL). La
  gate Environment reste réactivable plus tard si besoin (1 ligne `environment: production`).
- **E17.3 P1 — Contrat de migration backward-compatible (expand/contract) — V1 livrée** :
  documenté dans `QUALITY_GATES.md` (§ Déploiement des migrations Supabase) et rappelé dans
  le template de PR (`.github/pull_request_template.md`). Neutralise la **course avec le deploy
  Vercel** (front + migration en parallèle sur merge). Les migrations actuelles respectent déjà
  ce contrat (toutes additives).
- **E17.4 P2 — Smoke check post-migration + runbook** : à faire — vérification automatique que
  les objets attendus existent après push, et procédure de rollback/correction documentée.
- **E17.5 P2 — Génération des types Supabase post-push** : à faire — enchaîner la génération des
  types `Database` depuis les migrations (recoupe « Générer les types Supabase » ci-dessous).

Action owner restante (manuelle, hors repo) : créer les 2 secrets GitHub
`SUPABASE_ACCESS_TOKEN` (https://supabase.com/dashboard/account/tokens) et
`SUPABASE_DB_PASSWORD` (Project Settings → Database) **avant le premier merge** contenant
une migration.

Critère : plus aucune migration oubliée ; l'application du schéma est standardisée et auditée.

### P1 — Skeleton & rendu progressif — V1 livrée

- Objectif owner (2026-06-22) : afficher chaque information dès qu'elle est disponible
  plutôt que d'attendre toutes les données, pour améliorer la perception de vitesse.
- Statut V1 : primitive `Skeleton` partagée (`components/ui/skeleton.tsx`, respecte
  `prefers-reduced-motion`) + wrapper accessible `LoadingRegion` (`role="status"`).
  Streaming Suspense par section sur `/profile` (l'appel worker `/coach/discipline-levels`
  15 s ne bloque plus la page), `/today` (briefing), `/stats` (corps cockpit) et
  `/history/[id]` (analyse + samples). `loading.tsx` reconstruits (today, plan, stats,
  history) + ajoutés (profile, history/[id], profile/garmin). Spec
  `docs/superpowers/specs/2026-06-22-skeleton-streaming-design.md`, plan
  `docs/superpowers/plans/2026-06-22-skeleton-streaming.md`.
- Suite éventuelle : skeletons par section pour `/plan` et `/history` (listes) si besoin,
  empreinte de fraîcheur pour invalider finement.

### EPIC E26 — Après-course : célébration et choix du cap (demande owner 2026-08-25)

**Priorité : P1 — Statut : spec + plan écrits, implémentation à faire** — spec
`docs/superpowers/specs/2026-08-25-e26-apres-course-design.md`, plan
`docs/superpowers/plans/2026-08-25-e26-apres-course.md`. Dépend d'E23 (détection et débrief
livrés) et **se livre après E27** : sans le moteur, « maintenir » et « progresser » enregistrent
une intention sans effet.

E23 a fait de la course un objet de première classe **jusqu'au débrief**. Ce qui vient
**après** n'existe pas : rien ne félicite l'athlète, rien ne lui demande ce qu'il veut faire
ensuite, et `generate_plan` renvoie `race_in_past` dès le lendemain
(`planner.py:1304`) — l'app cesse purement et simplement de proposer des séances. Le seul
moyen de repartir aujourd'hui est d'aller créer un objectif à la main, sans y être invité.

Objectif : transformer la ligne d'arrivée en **point de bascule guidé** — un mot sur la course,
puis un choix de cap explicite, qu'on peut remettre à plus tard sans que l'app se fige.

- **E26.1 P1 — État du prompt post-course** : colonnes sur `race_goals`
  (`post_race_prompt_status` ∈ `pending`/`snoozed`/`answered`/`dismissed`,
  `post_race_prompt_snoozed_until`, `post_race_choice`, `post_race_answered_at`) plutôt qu'une
  table générique — une ligne par course, RLS déjà en place. RPC `security definer` pour
  enregistrer le choix ou le report, gardée comme les autres.
- **E26.2 P1 — Déclenchement fiable** : la modale s'arme quand une activité est **rattachée**
  à une course (au sync, donc J+1 au plus tôt : les splits et le débrief ne sont exploitables
  qu'après), et s'ouvre à la première connexion suivante. Trois garde-fous, sans quoi elle se
  déclenche à tort : **une seule fois par `race_goal`** et non par activité (un triathlon
  arrive en 5 fichiers Garmin) ; **fenêtre de fraîcheur** (course de moins de ~14 jours) pour
  qu'un backfill ou un tag rétroactif n'ouvre pas un « Bravo ! » sur une épreuve de 2024 ;
  activité **exclue** (E24) ignorée.
- **E26.3 P1 — Le mot sur la course, déterministe** : comme le reste du débrief E23, **aucun
  LLM** — trois tons dérivés des données. *Célébration* si le temps tient la cible
  (`target_time_seconds`) ou bat la course précédente de même format ; *factuel positif* si
  l'épreuve est terminée sans cible de temps ; *attentionné* si la distance reste très en deçà
  des `legs` (abandon) ou l'écart est massif. Une phrase, un chiffre, un lien vers le débrief
  complet — le silence n'est pas une option, une journée difficile mérite un mot.
- **E26.4 P1 — Choix du cap** : trois voies plus un report. **Nouvel objectif** → formulaire
  course (celui de l'onboarding), l'ancienne course passe `is_primary = false` dans la même
  transaction pour ne pas violer `race_goals_one_primary_per_user`. **Maintenir l'état actuel**
  et **progresser sans objectif** → basculent `training_mode` (E27). **Plus tard** → report.
  Le choix reste modifiable à tout moment depuis le profil : ce n'est pas un one-shot.
- **E26.5 P1 — Report et relance dégressive** : skip = report à **J+2**, puis **J+5**, puis
  plus aucune interruption — une **bannière discrète et permanente** sur `/today` prend le
  relais jusqu'au choix. Trois modales au maximum ; reproposer à chaque connexion agacerait,
  surtout pendant une coupure post-course.
- **E26.6 P1 — Défaut si l'athlète ne répond jamais** : **semaine de récupération imposée**
  (E27.1), puis bascule automatique en **maintien**. L'app ne reste jamais vide en attendant
  une réponse — c'est le trou actuel.
- **E26.7 P2 — Une seule interruption par session** : règle de priorité entre la modale
  post-course et le badge de nouveautés (E21), pour ne jamais empiler deux sollicitations à
  l'ouverture de l'app.

**Forme** : `Sheet` bas d'écran (cohérent avec la cloche E21, meilleur en PWA mobile) plutôt
qu'un `Dialog` centré. La modale reste courte — mot + chiffre + lien débrief + trois boutons
de cap + « plus tard » ; « nouvel objectif » enchaîne vers la page de formulaire, jamais un
wizard imbriqué dans la modale.

**Points à trancher à la spec** : largeur exacte de la fenêtre de fraîcheur ; formulation des
trois tons ; comportement quand deux courses sont détectées coup sur coup (week-end à deux
épreuves) ; place de la bannière permanente dans la hiérarchie de `/today`.

### EPIC E27 — Entraînement sans objectif : maintien et progression continue (demande owner 2026-08-25)

**Priorité : P1 — Statut : spec + plan écrits, implémentation à faire** — spec
`docs/superpowers/specs/2026-08-25-e27-entrainement-sans-objectif-design.md`, plan
`docs/superpowers/plans/2026-08-25-e27-entrainement-sans-objectif.md`. Prérequis fonctionnel
d'E26.4 et E26.6, **à livrer en premier**.

Tout le moteur de plan dérive d'une `race_date` : ancre de préparation, phases, rampes, taper,
séance du jour J. Sans course future, `_load_plan_inputs` renvoie `no_race_goal` ou
`race_in_past` et **rien n'est généré**. Un athlète entre deux objectifs, ou qui s'entraîne
sans en viser aucun, n'a donc aucun plan — alors que c'est l'état le plus courant hors saison.

Objectif : un **mode d'entraînement sans course**, aussi sérieux que la préparation d'épreuve —
horizon roulant, périodisation cyclique, charge pilotée par une CTL cible.

- **E27.1 P1 — Semaine de récupération post-course** : quel que soit le cap choisi, la semaine
  qui suit une course est une semaine de récup, imposée avant tout nouveau bloc — y compris si
  l'athlète enchaîne immédiatement sur un nouvel objectif. Volume et intensité dérivés de la
  durée et de la charge de l'épreuve.
- **E27.2 P1 — Mode d'entraînement explicite** : `athlete_profiles.training_mode`
  (`race` / `maintain` / `improve`) + `training_mode_since`. **Une seule source de vérité** :
  créer un objectif force `training_mode = 'race'` dans la même transaction, pour ne jamais
  avoir à arbitrer entre la colonne et l'existence d'un `race_goal` primaire.
- **E27.3 P1 — Générateur à horizon roulant** : sans date d'arrivée, il n'y a plus d'ancre —
  le plan devient un **horizon glissant de 4 semaines** régénéré chaque semaine, en cycles
  3 semaines de charge + 1 de décharge, sans taper ni pic. La rotation des disciplines et des
  types de séance réutilise l'existant (`pick_session_types_for_phase`, budgets de charge).
- **E27.4 P1 — Charge pilotée par CTL cible** : en **maintien**, CTL cible constante au niveau
  atteint post-course (le budget hebdo se règle pour tenir la CTL, pas pour la faire monter) ;
  en **progression**, rampe modérée (ordre de +3 à +5 %/semaine, à caler sur les rampes
  existantes) avec décharge cyclique. Le garde-fou de fatigue (TSB) reste celui du mode course.
- **E27.5 P1 — Cohérence de l'interface sans course** : `/today` et `/plan` affichent le mode
  courant au lieu du J-N, la page objectif permet de changer de cap, et les écrans qui
  supposent une course à venir dégradent proprement.
- **E27.6 P2 — Transition entre modes** : passer de `maintain` à `race` en cours de route ne
  doit pas repartir de zéro — la CTL atteinte devient le point de départ de la préparation
  (recoupe `_ensure_prep_anchor` et le multiplicateur prudent de reprise).

**Points à trancher à la spec** : valeur exacte de la rampe de progression et son plafond ;
comment fixer la CTL cible de maintien (valeur post-course figée, ou moyenne glissante) ;
longueur de l'horizon roulant (4 semaines par défaut) ; ce que devient un plan `race` déjà
généré quand l'athlète bascule en `maintain`.

### EPIC E16 — Chargement et rendu progressif des pages (sujet transversal) (owner 2026-06-27)

**Priorité : P1 — Statut : V1 partielle, audit ci-dessous**

Sujet dédié au-dessus de l'item « Skeleton & rendu progressif » : poser un **standard de
chargement** appliqué à **toutes** les pages — afficher la coquille de page immédiatement,
puis chaque section dès que sa donnée est prête, avec un skeleton pour ce qui n'est pas
encore là. Objectif : la page apparaît tout de suite, jamais d'écran blanc bloqué sur la
requête la plus lente.

**Standard cible** :
- Distinguer deux mécanismes : `loading.tsx` (skeleton pendant la **navigation** vers la
  route) vs `<Suspense>` intra-page (**rendu progressif** : shell + données rapides affichés
  pendant que les sections lentes streament). Le « afficher dès que dispo » repose sur le
  second.
- Toute page avec une dépendance lente (appel worker, agrégat) doit isoler cette section
  dans un `<Suspense>` avec fallback skeleton, et ne jamais bloquer le reste de la page
  dessus.
- Chaque route a un `loading.tsx` cohérent avec sa structure réelle (pas un spinner
  générique).

**Audit de l'existant (statique, 2026-06-27 — comptage Suspense/await, pas une mesure
runtime)** :
- ✅ **Rendu progressif en place** (Suspense intra-page) : `/today` (briefing), `/stats`
  (corps cockpit), `/profile` (discipline-levels worker ~15 s), `/history/[id]` (analyse +
  samples). Ce sont les pages à dépendance worker lente — le streaming y est justifié et fait.
- ⚠️ **Pages bloquantes** : `/plan` et `/history` (listes) `await` toutes leurs données
  avant de rendre (0 `<Suspense>`). Enjeu **modéré** car ce ne sont que des requêtes
  Supabase rapides, mais à uniformiser pour la cohérence et la robustesse si les listes
  grossissent. (C'est la « suite éventuelle » de l'item Skeleton ci-dessus.)
- ⚠️ **`/onboarding`** : bloquant **et** sans `loading.tsx` — à doter au moins d'un
  `loading.tsx`.
- ✅ `/profile/garmin` : client component avec `loading.tsx`, OK.
- 🔴 **Coût auth redondant (transversal, prioritaire)** : `app/(app)/layout.tsx` fait déjà
  `supabase.auth.getUser()`, puis **chaque page rappelle `requireOnboarded()`
  (`lib/onboarding/guard.ts`) qui refait `auth.getUser()` + une requête `athlete_profiles`**.
  Résultat : ≥2 allers-retours auth en série **avant** que le moindre streaming démarre, sur
  toutes les pages protégées. C'est le plafond de latence partagé le plus impactant. Piste :
  mémoïser/partager le résultat auth (React `cache()`), ou remonter la garde onboarding dans
  le layout, pour ne payer l'auth qu'une fois par requête.

**Actions** :
- **E16.1 P0 — Supprimer le double appel auth (layout + `requireOnboarded`) — V1 livrée**
  (PR #99) :
  `lib/supabase/current-user.ts` expose un `getCurrentUser()` unique, enveloppé par
  React `cache()` (mémoïsation par requête App Router — « Request Memoization »,
  distincte de `unstable_cache`). `app/(app)/layout.tsx`, `lib/onboarding/guard.ts`
  (`requireOnboarded`) et `lib/admin/guard.ts` (`requireAdmin`) appellent tous cette même
  fonction au lieu de refaire chacun `supabase.auth.getUser()` — un seul aller-retour
  réseau auth par requête, dans l'arbre layout + page, avant que le rendu/streaming
  démarre. Le recheck intentionnel `is_admin_caller()` dans `requireAdmin()` (defense-in-
  depth documentée) est inchangé, seul l'appel `auth.getUser()` sous-jacent est partagé.
  Pas de middleware Next.js introduit (cf. piège documenté dans `CLAUDE.md`).
- E16.2 P2 — Passer `/plan` et `/history` en sections `<Suspense>` + skeletons dédiés.
- E16.3 P2 — Ajouter un `loading.tsx` à `/onboarding`.
- E16.4 P2 — Empreinte de fraîcheur des données pour invalider finement (déjà listé comme
  suite de l'item Skeleton et du cache briefing).
- E16.5 P2 — (Optionnel) mesurer réellement (Lighthouse/Speed Insights) le TTFB et le LCP
  par page pour prioriser sur des chiffres plutôt qu'un audit statique.

**Critère produit** : chaque page protégée affiche sa coquille quasi immédiatement, chaque
bloc apparaît dès que sa donnée est prête, et aucune page n'attend sa requête la plus lente
pour montrer quoi que ce soit.

### P2 — Identité numérique et style graphique coach (rétrogradé P0 → P2 le 2026-06-28 — polish UX différé)

- Définir une identité visuelle stable : personnalité de marque, ton éditorial,
  palette, typographies, iconographie, densité d'information, états d'alerte et
  style des graphiques.
- Orienter l'app vers une expérience "coach de performance" : sobre, précise,
  crédible, orientée décision, avec des signaux visuels clairs pour charge,
  récupération, progression et risque.
- Produire un document `docs/superpowers/DESIGN.md` servant de référence avant tout
  ajout UI : composants, couleurs sémantiques, cartes, badges, graphiques,
  wording et règles responsive.
- Harmoniser `/today`, `/history/[id]`, `/plan`, `/profile`, `/stats` autour de ce
  langage visuel pour éviter une accumulation de blocs fonctionnels sans identité.
- Critère produit : l'utilisateur doit reconnaître une application de coaching
  sportif sérieuse, pas un dashboard générique Garmin-like.

### P1 — Graphiques pro et carte d'activité (E14.1 / E14.2)

- Élever la qualité visuelle des graphiques au niveau Garmin/Strava : profil
  d'altitude, fréquence cardiaque dans le temps, allure/vitesse, puissance, cadence,
  zones, splits/tours, distribution d'effort — lisibles, interactifs, soignés.
- Afficher la carte GPS du parcours dans la fiche activité (`/history/[id]`) avec le
  tracé, le dénivelé et un survol corrélé FC/allure si possible.
- S'appuyer sur les samples déjà stockés (`activity_samples`) et compléter via
  `get_activity_details` quand le tracé GPS manque.
- Lien : recoupe E9.5 (analyse avancée d'activité) et la spec E8a parcours géolocalisés.
- Critère produit : un athlète habitué à Garmin/Strava doit trouver les graphes au
  moins aussi clairs et complets.
- **P0 — Lisibilité des « Courbes d'activité » : axe Y unique → courbes écrasées
  (retour owner 2026-06-27) — V1 livrée (E14.1b, PR #74)** : panneaux empilés synchronisés,
  un axe Y réel par métrique, curseur partagé, toggle temps/distance, chips de visibilité,
  axe allure inversé. Détail de la solution conservé ci-dessous pour mémoire :
  - **Problème** : dans `app/(app)/_components/charts/activity-samples-chart.tsx`, les 5
    métriques (FC, altitude, puissance, cadence, allure) sont tracées sur **un seul axe Y
    partagé**. Comme leurs échelles sont incompatibles (FC ~120-180 bpm, altitude des
    centaines de m, puissance 0-400 W…), l'axe s'étire sur la plus grande amplitude et les
    métriques à faible plage — la FC en particulier — apparaissent comme un trait quasi
    plat, illisible.
  - **Intention owner** : un rendu **type Strava** où l'on lit **les vraies valeurs** de
    chaque métrique (pas seulement les fluctuations relatives). L'owner a évoqué la
    « normalisation », mais une normalisation 0-100 % pure va à l'encontre de cet objectif
    (elle aplatit tout sur une échelle abstraite et masque les unités sur l'axe).
  - **Solution recommandée — panneaux empilés synchronisés** : un mini-graphe par métrique,
    empilés verticalement, alignés sur le même axe X (temps/distance), chacun avec son
    propre axe Y aux unités réelles, et un curseur/tooltip partagé qui affiche toutes les
    valeurs à l'abscisse survolée. C'est exactement le comportement Strava et il satisfait
    « rendu Strava + lecture des valeurs réelles ».
  - **Repli léger acceptable** : multi-axes Y (un `yAxisId` recharts par métrique) sur un
    graphe superposé, avec un sélecteur des métriques affichées pour éviter la surcharge
    d'axes. Conserve les valeurs réelles mais reste moins lisible à 4-5 séries.
  - **À ne pas faire seul** : normalisation 0-100 % sur axe commun — perd les valeurs à la
    lecture directe (ne répond pas à l'intention owner). Tolérable uniquement comme mode
    de comparaison de formes en plus des panneaux, jamais en remplacement.
  - **Critère d'acceptation** : sur une activité avec FC + altitude + puissance, chaque
    courbe est lisible avec sa propre amplitude, la FC n'est plus un trait plat, et
    l'utilisateur peut lire la valeur réelle de chaque métrique à un instant donné.
- **P2 — Vitesse/allure natation dans la courbe d'activité piscine — V1 livrée (E14.1b, PR #74)** :
  la natation affiche désormais l'allure en **min/100m** via le helper central
  `formatSpeedForSport`, la courbe vitesse n'apparaît que si `speed_m_s` est présent.
  _(englobé par l'item « Convention d'unités par discipline » et la refonte multi-panneaux)_
  - **Problème** : `app/(app)/_components/charts/activity-samples-chart.tsx` convertit
    systématiquement `speed_m_s` en **allure min/km** (label « Allure min/km »), une unité
    inadaptée à la natation où la métrique standard est l'**allure min/100m**. Le composant
    ne connaît pas le sport de l'activité, donc la piscine n'a pas de courbe de vitesse
    lisible.
  - **Donnée déjà disponible** : `speed_m_s` est extrait côté worker
    (`worker/src/garmin_sync/transformers/activities.py`, `_SPEED_KEYS`) et stocké dans
    `activity_samples` — donc présent dès que Garmin le fournit pour la natation. Rien à
    ajouter côté ingestion ; c'est un travail de rendu.
  - **Solution** : passer le `sport` de l'activité à `ActivitySamplesChart` et adapter la
    série vitesse selon le sport — pour la natation, afficher l'**allure min/100m** (ou la
    vitesse) avec le bon label et la bonne échelle, **uniquement si `speed_m_s` est présent**
    (« si disponible » = courbe masquée sinon, pas de série vide ni absurde).
  - **À cadrer** : unité natation à retenir — **allure min/100m** (convention nageur,
    recommandée) vs vitesse km/h ; l'owner a parlé de « vitesse », à confirmer au moment de
    l'implémentation.
  - **Lien** : recoupe l'item « Lisibilité des courbes d'activité » ci-dessus (E14.1) — la
    série natation aurait son propre panneau/axe dans la refonte multi-échelles. **Désormais
    couvert par l'item « Convention d'unités vitesse/allure par discipline » ci-dessous**
    (natation = min/100m), à traiter via le helper central plutôt qu'en local.
  - **Critère** : sur une activité piscine avec données de vitesse, l'utilisateur voit une
    courbe d'allure/vitesse dans une unité pertinente pour la natation ; aucune courbe
    trompeuse quand la donnée manque.

### P1 — Convention d'unités vitesse/allure par discipline (Strava-like) — V1 livrée (E14.1b, PR #74)

> **Statut V1** : helper central `lib/dashboard/format.ts` (`formatSpeedForSport`,
> `formatTargetForSport`, `paceUnitForSport`, `speedToSportValue`) appliquant **vélo km/h,
> course min/km, natation min/100m**, propagé aux courbes d'activité, à la fiche
> `/history/[id]` (vitesse moyenne + tableau terrain) et aux **cibles de séance des plans**
> (course passait en km/h → désormais min/km). Worker laissé en km/h pour la VMA (légitime).
> Suite éventuelle : propager au briefing / `/stats` si de nouveaux affichages vitesse y apparaissent.


- **Demande owner** : normaliser l'affichage de la vitesse/allure selon la discipline,
  comme sur Strava (unités auxquelles la plupart des athlètes sont habitués) :
  - **Vélo → km/h**
  - **Course à pied → min/km** (allure)
  - **Natation → min/100m** (allure)
- **Problème actuel** : pas de helper central (rien dans `lib/dashboard/format.ts`), chaque
  surface reformate seule et de façon incohérente. Cas concret signalé : les **plans
  d'entraînement** affichent les cibles de course en **km/h** (`lib/coach/session-templates.ts`
  `fmtTarget`, ligne ~53-54 : `${t.pace_low_kmh} km/h`), peu lisible pour un coureur qui
  raisonne en min/km. La courbe d'activité (`activity-samples-chart.tsx`) convertit aussi
  `speed_m_s` en min/km sans tenir compte du sport.
- **Solution** : créer un formateur centralisé du type `formatPaceForSport(sport, speed_m_s)`
  / `formatTargetForSport(...)` dans `lib/dashboard/format.ts`, appliquant la convention
  ci-dessus, et le **réutiliser partout** : courbes d'activité, fiche `/history/[id]`,
  cartes de séance / plans (`session-card.tsx`, `session-templates.ts`), briefing, stats.
- **À cadrer côté données** : le modèle `IntervalTarget` stocke `pace_low_kmh`/`pace_high_kmh`
  (km/h) — la conversion en min/km et min/100m est un travail d'affichage. Vérifier aussi le
  rendu markdown côté worker (génération séances E5, `format_explanation_md` et templates) pour
  que les plans soient cohérents quel que soit le point de génération (front vs worker).
- **Priorité au sein de l'item** : le sous-cas **plans d'entraînement** (course en min/km,
  natation en min/100m) est le plus irritant et devrait être traité en premier.
- **Lien** : englobe l'item « Vitesse/allure natation dans la courbe d'activité piscine »
  ci-dessus et recoupe « Lisibilité des courbes d'activité » (E14.1).
- **Critère produit** : un athlète habitué à Strava retrouve partout ses unités familières
  (km/h vélo, min/km course, min/100m natation), y compris dans les séances du plan.

### P2 — Pédagogie des métriques (bulles explicatives) (E14.3) (rétrogradé P1 → P2 le 2026-06-28 — polish UX différé)

- Ajouter des bulles/infobulles explicatives sur les graphiques et métriques clés :
  charge (CTL), forme (TSB), fatigue (ATL), HRV, TSS, zones, dérive cardio.
- Expliquer en langage simple « c'est quoi » et « comment l'utiliser pour progresser »
  (ex. sur le graphe charge/forme : lire la fraîcheur et maximiser le progrès).
- Prévoir un glossaire accessible et des micro-explications contextuelles, pas un cours
  théorique.
- Critère UX : un athlète non expert comprend ce qu'il regarde sans connaissance
  préalable de la science de l'entraînement.

### P1 — Ingestion quasi temps réel (Strava / Garmin officiel) (E15)

Détail complet et à jour (Strava OAuth+webhooks, Garmin officiel, sync on-demand, pull
au connect, données montre multi-marques) sous § « EPIC E15 — Ingestion multi-source et
quasi temps réel » en tête de fichier (E15.1 à E15.5).

### P0 — Cache et chargement rapide du briefing quotidien

- Éviter de recalculer le briefing à chaque ouverture de `/today`.
- Ajouter un cache métier par `user_id + date` pour le briefing quotidien, avec
  payload, date de calcul, version de logique coach et empreinte des données source
  si nécessaire.
- Retourner immédiatement le briefing du jour en cache quand il est encore valide.
- Invalider ou recalculer après une nouvelle sync Garmin, une nouvelle activité, une
  mise à jour sommeil/HRV, un changement de séance planifiée ou une régénération de
  plan.
- Mettre en place un comportement stale-while-revalidate : afficher vite le dernier
  briefing fiable, puis rafraîchir en arrière-plan si les données ont changé.
- Optimiser `/today` en lançant le chargement du briefing en parallèle des autres
  requêtes Supabase, pour éviter de bloquer toute la page sur l'appel worker.
- Critère UX : l'ouverture de la page du jour doit être quasi immédiate, même si le
  recalcul coach prend plus de temps.
- Statut V1 : cache Supabase `coach_daily_briefings` par utilisateur/date/version,
  retour cache avant rate limit, calcul + upsert en cas de miss, et chargement du
  briefing en parallèle des autres données de `/today`.
- Suite : ajouter une empreinte des données sources pour invalider finement après
  nouvelle activité, sommeil/HRV ou modification de séance planifiée.

### P0 — Débloquer la suite de tests worker

- `TestClient(app)` bloque actuellement sur `tests/test_main.py::test_health_ok`
  quand le lifespan FastAPI démarre le scheduler.
- Piste : factory `create_app(enable_scheduler=True)` ou désactivation scheduler
  en `ENV=test`, puis timeout explicite en CI.
- Diagnostic complémentaire : le blocage se reproduit aussi avec une app FastAPI
  minimale et `TestClient`, donc vérifier la compatibilité FastAPI / Starlette /
  httpx avant de refactorer l'app.
- Statut V1 : suite worker complète débloquée localement. `main.py` expose
  `create_app(enable_scheduler=...)`, désactive le scheduler par défaut en
  `ENV=test`, et `tests/test_main.py` utilise `httpx.ASGITransport` car
  `fastapi.testclient.TestClient` bloque dans la pile de dépendances actuelle.

### P0 — Aligner documentation, CI et runtime

- README annonce Node 20+ alors que la CI utilise Node 22.
- README worker mentionne encore le timer systemd 05:00 UTC alors que le code utilise
  APScheduler embarqué avec plusieurs jobs UTC.
- Statut V1 : README racine aligné sur Node 22+ / pnpm 11+, README worker mis à
  jour avec le scheduler APScheduler embarqué et les horaires UTC réels.

### P1 — Rendre les générations async observables

- Remplacer les fire-and-forget silencieux par un statut de job visible : pending,
  running, failed, done, retryable.
- L'utilisateur doit savoir si son plan ou sa séance est en génération, en erreur,
  ou repris par le cron.

### P1 — Durcir la frontière Next.js -> worker

- Valider les réponses worker avec des schémas typés.
- Mapper proprement les statuts HTTP non-OK, timeouts, rate limits et erreurs
  inattendues.

### P0 — Worker : filtrer le plan actif sur les lectures `planned_sessions` (avant E9) (remontée P1 → P0 le 2026-06-28 — correctness multi-users à l'ouverture beta)

Contexte : le frontend (`/today`, `/plan`, historique) lit les `planned_sessions`
avec `training_plans!inner(status)` + `status='active'` + `order(created_at desc)` +
`limit(1)`. Le worker, lui, lit par `(user_id, date)` sans filtre de statut ni tri :
`_load_planned_session`, `_load_planned_session_for_date` (`coach/briefing.py`) et la
requête de génération dans `coach/sessions.py` (`ensure_sessions`).

Impact aujourd'hui : **nul** — 1 seul objectif de course, 1 plan actif, 0 date en
double, sessions des plans archivés purgées à la régénération. Mais la régénération ne
nettoie que les plans du **même `race_goal_id`** : dès qu'un user aura **plusieurs
objectifs de course** avec des plages de plan qui se chevauchent, il y aura ≥2 lignes
pour une même date → `.maybe_single()` lèvera une erreur (briefing/`/today` en échec)
et `ensure_sessions` générera des séances en double.

À faire (PR dédiée, avant l'ouverture beta multi-users E9) :
- Aligner les 3 lectures worker sur le filtre `status='active'` + `order(created_at desc)`
  + `limit(1)`, comme le frontend.
- Ajouter un index unique partiel sur `planned_sessions(user_id, date)` restreint aux
  plans actifs, pour rendre les doublons impossibles côté DB.
- Tests : cas multi-objectifs / multi-plans-actifs sur une même date.
- Découvert pendant le fix du feedback post-séance périmé (PR #59).

### P1 — Générer les types Supabase

- Ajouter les types `Database` générés depuis les migrations.
- Typer les clients Supabase et réduire les casts dans les pages dashboard.

### P0 — Observabilité production (remontée P1 → P0 le 2026-06-28 — visibilité des erreurs beta)

- **V1 worker livrée (PR #77, mergée 2026-07-02)** : module `observability.py`
  (`init_sentry`, `new_error_id`, `capture`, `report_endpoint_error`). Sentry s'active dès
  que `SENTRY_DSN` est défini (off en dev/test), initialisé au boot FastAPI (`create_app`) et
  dans l'entrée cron `__main__`. **Capture aux points d'échec auparavant silencieux** :
  génération de séance (`ensure_sessions`, le bug du retry), jobs du scheduler, crons sync /
  profile par-user, recomputes Banister post-sync. Les 8 endpoints reportent via
  `report_endpoint_error` avec l'`error_id` partagé entre la réponse navigateur et le tag
  Sentry. Config : `SENTRY_TRACES_SAMPLE_RATE`.
- **Alerting Discord livré (2026-06-30, même branche)** : module `alerting.py`
  (`notify_discord_error`), branché dans le funnel `capture()` — chaque erreur capturée
  envoie un embed Discord (titre `type — where`, message, tags env/user_id/session_id…) via
  webhook. Actif dès que `DISCORD_WEBHOOK_URL` est défini (off sinon), découplé de Sentry,
  ne lève jamais (échecs avalés + log warning). Push proactif sur le téléphone de l'owner.
- **Reste à faire** :
  - **Frontend** : SDK Sentry Next.js (client + server + edge) pour les erreurs Server Actions
    et navigateur (P2).
  - **Cron health / dead-man's switch** : check-in à chaque run (Sentry Cron Monitoring ou
    Healthchecks.io) pour détecter « le cron ne s'est pas lancé du tout » (P3).
  - **Logs structurés + métriques** : durée sync, coût/tokens OpenAI (recoupe E18 `llm_usage`),
    taux d'échec génération (P4).
  - **Affiner l'alerting** : règles email Sentry + dédup/seuils si le volume Discord devient
    bruyant (actuellement 1 message par erreur, OK pour la beta).

### P1 — Rate-limit auth non falsifiable (suite audit SEC-2 du 2026-07-26)

- **Problème** : `check_and_log_auth_rate_limit(p_ip, p_action, p_max_count, p_window_seconds)`
  est appelable par `anon` via `/rest/v1/rpc/...` avec des paramètres entièrement choisis par
  l'appelant. Deux conséquences : (1) on peut saturer le compteur d'une **IP tierce** et la
  verrouiller hors du login ; (2) le plafond n'est pas autoritaire côté serveur (c'est
  l'appelant qui passe `p_max_count`), donc le RPC ne protège que le flow UI, pas un appel
  direct.
- **Pourquoi ce n'est pas un simple `revoke`** : le grant à `anon` est structurel —
  `app/(auth)/_actions/auth.ts` appelle ce RPC avec le client anon **avant** toute
  authentification (register / login / mot de passe oublié). Le révoquer casse l'auth.
- **Pistes** : appeler le rate-limit depuis la Server Action avec un client **service-role**
  (le secret ne quitte pas le serveur, l'IP vient des headers Next.js et non du client), ou
  déplacer le compteur derrière un endpoint worker ; dans les deux cas figer `max_count` /
  `window_seconds` côté serveur au lieu de les passer en paramètres. Recoupe la piste
  « Vercel Firewall / WAF » de `SECURITY.md` (Roadmap étape 5).
- **Lien** : `SECURITY.md` § « Audit 2026-07-26 — SEC-2 ». Même famille que le risque
  d'énumération d'emails déjà arbitré en SEC-1 (`is_email_allowed` / `email_needs_signup`).
- **Critère** : un appel REST direct au rate-limit ne peut ni verrouiller un tiers ni
  contourner le plafond.

### P2 — Généraliser le `revoke execute … from public` sur les futures fonctions

- L'audit SEC-2 a montré que la cause racine est systémique : Postgres accorde `EXECUTE` à
  `PUBLIC` par défaut, donc `grant execute … to service_role` seul ne restreint **rien**.
  Toute nouvelle fonction `security definer` doit désormais faire son `revoke` explicite
  (patron correct : `try_claim_garmin_sync`, `20260627000000`).
- À faire : ajouter la vérification à la checklist du template de PR et/ou un lint dans
  `.github/workflows/supabase-migrations.yml` (une migration qui crée une fonction
  `security definer` sans `revoke execute … from public` échoue).

### P2 — Élargir E2E et Lighthouse aux parcours réels

- Ajouter parcours authentifié seedé ou mocké : onboarding, Garmin mocké, `/today`,
  `/plan`, `/profile`, `/stats`.
- Étendre Lighthouse au-delà de `/login`.

## Bugs et incidents connus (constatés le 2026-06-27)

Erreurs relevées en production (logs worker + données Supabase) lors d'une revue.

### P0 — Worker déployé périmé : `/garmin/sync` renvoie 404 (E15.3 inactif en prod)

- Symptôme logs : `POST /garmin/sync?trigger=auto HTTP/1.1 404 Not Found` (16:01 et 20:58).
- Cause : l'endpoint on-demand existe dans le code sur `main` (`worker/src/garmin_sync/main.py`,
  route `@router.post("/garmin/sync")`, livré par #64) mais le container worker sur UNRAID
  tourne une **image Docker antérieure à #64**. Piège déjà documenté dans CLAUDE.md
  (« l'image reste old tant que les changements ne sont pas redéployés »).
- Impact : la sync on-demand (auto à l'ouverture + bouton manuel) ne fait rien ;
  `garmin_credentials.last_sync_trigger_at` reste `null`. Seul le cron remplit les données.
- Fix : redéployer le worker (`docker pull tellebma/garmin-sync:latest` + restart du container),
  puis vérifier que `/garmin/sync?trigger=manual` renvoie `started` / `cooldown`.

### P1 — Génération de séances LLM en échec répété (workouts hors bornes)

- Symptôme logs : `OpenAI returned unrealistic workout` en boucle pour plusieurs séances :
  `main work below 80% for endurance`, `warmup 600s exceeds cap 300s`,
  `warmup 1200s exceeds cap 900s`, `cooldown 900s exceeds cap 600s`.
- Cause : `validate_workout_for_session` (`coach/workout_schema.py`) rejette la sortie LLM
  qui viole les bornes ; `generate_workout_for_session` relève l'erreur et l'appel échoue.
  À chaque `/coach/ensure-sessions` les mêmes séances sont re-tentées et re-échouent →
  certaines séances n'obtiennent **jamais** de workout.
- Impact : séances sans workout détaillé pour l'athlète, surcoût d'appels OpenAI répétés.
- Pistes : retry borné avec feedback de l'erreur au prompt (reprompt « respecte ces bornes »),
  réparation déterministe (clamp warmup/cooldown/main aux bornes) ou fallback workout simple
  si le LLM échoue N fois ; éviter de re-tenter indéfiniment les séances en échec persistant.

### P1 — Données d'activité grossières/tronquées pour les longues sorties

- Constat données : `activity_samples` plafonne à ~2000 points quelle que soit la durée
  (run 31 min = 1906 samples, vélo 2h54 = 1758) — c'est le downsampling Garmin par défaut.
- Deux plafonds à relever **ensemble** sous peine de tracé partiel :
  - worker : `get_activity_details(...)` est appelé sans params → `maxchart=2000` /
    `maxpoly=4000` par défaut ;
  - frontend : `.limit(2000)` sur `activity_samples` dans `app/(app)/history/[id]/page.tsx`.
- Aujourd'hui complet (activités < 2000 samples) mais une sortie de 6h serait grossière, et
  relever `maxchart` sans relever `.limit` reproduirait un tracé partiel (boucle non fermée).
- Chantier dédié en cours (voir spec « données complètes longues sorties »).

### P2 — Samples GPS « nus » potentiellement écartés

- `transform_activity_samples` ne conserve un sample que s'il porte un signal
  distance/altitude/FC/puissance/cadence/vitesse (`_has_sample_signal`) ; un point GPS
  sans aucune de ces métriques (rare : début/fin, pause) serait écarté du tracé.
- Impact marginal aujourd'hui (chaque point GPS porte vitesse/distance), à garder en tête.

### P2 — Widget « Mes cols » sur /stats — V1 livrée (PR #87)

- Domicile calculé automatiquement (médiane des départs GPS, réutilise
  `athlete_profiles.lat`/`lon`), référentiel de cols OpenStreetMap Overpass (rayon
  50km, cache 30j / déplacement 5km), détection de franchissement par proximité GPS
  (150m) calculée dans le cron worker quotidien. Widget `/stats` avec chargement
  async isolé (Suspense dédié, ne bloque jamais le reste de la page).
- Spec : `docs/superpowers/specs/2026-07-08-cols-stats-widget-design.md`.
  Plan : `docs/superpowers/plans/2026-07-08-cols-widget.md`.
- Suite (hors scope V1, notée pendant le brainstorming) : édition manuelle de la
  liste des cols par l'utilisateur, distinction montée stricte vs simple passage,
  mini-carte visuelle des cols.

### P2 — Sommets (natural=peak) dans le widget cols — V1 livrée (PR #102, #106)

- Le widget « Mes cols » ne référence que `mountain_pass=yes` (OSM) : les sommets
  hors col routier (ex. Crêt d'Arjoux, natural=peak) sont invisibles quelle que soit
  leur pertinence locale. Comparaison faite avec ColQuest (chasse aux cols/sommets
  via matching Strava) qui suit un modèle proche de la détection par proximité GPS
  déjà en place ici.
- Extension de la table `cols` existante (colonne `type` col/peak, pas de nouvelle
  table), requête Overpass combinée (`mountain_pass=yes` + `natural=peak`), filtre
  d'altitude ≥ 500m sur les sommets uniquement. Widget renommé « Mes cols & sommets »,
  deux sections triées séparément.
- Spec : `docs/superpowers/specs/2026-07-12-cols-sommets-peaks-design.md`.
- Plan : `docs/superpowers/plans/2026-07-12-cols-sommets-peaks.md`.
- Statut V1 : livré tel que spécifié (PR #102) ; PR #106 a déplacé le bouton « voir plus »
  en pied de chaque section avec compteur.

### P1 — Détection des cols partout (bbox d'activité) — V1 livrée

- Bug vécu (2026-07-25) : le col du Chaussy gravi en Maurienne n'apparaissait pas —
  le référentiel Overpass ET le matching étaient limités à 50 km du domicile, et le
  curseur `col_matching_cursor` ne rejouait jamais les activités déjà scannées.
- Refonte livrée : Overpass fetch + matching par bounding box de chaque activité GPS
  (les cols gravis en déplacement sont détectés où qu'ils soient), couverture dédupliquée
  par zone pendant un run + cooldown 1s entre appels Overpass, curseur qui s'arrête avant
  une activité en échec (retry au cron suivant), reset one-shot du curseur en migration
  pour rejouer tout l'historique. Affichage : cols gravis toujours visibles (peu importe
  la distance), cols à 0 passage limités au rayon de 50 km, plafond de 30 résultats par
  section (10 visibles + dépliage).
- Le refresh Overpass domicile-50 km est conservé : il alimente les cols « à explorer ».

## Post-MVP technique

- Requête `cols` non bornée spatialement : `ColsWidgetLoader` (`app/(app)/stats/page.tsx`)
  fait un `select` complet de la table `cols` (partagée entre tous les users) et filtre le
  rayon de 50km côté JS (`lib/dashboard/cols.ts`). Comportement préexistant au widget cols,
  amplifié par l'ajout des sommets (`natural=peak` bien plus dense que `mountain_pass=yes`
  en zone montagneuse). Acceptable à l'échelle MVP (owner + quelques amis, une région), à
  borner (préfiltre lat/lon ou requête spatiale PostGIS/RPC) avant l'ouverture beta à
  plusieurs régions. Identifié lors de la revue finale de branche
  `feat/e-post-mvp-cols-sommets` (2026-07-13).
- Custom SMTP Supabase (Resend gratuit 100/jour) — rate limits du SMTP intégré.
- Vercel Speed Insights pour monitoring perf prod.
- Script `scripts/sync-email-templates.ts` qui pousse les templates depuis le repo
  via Supabase Management API (vs sync manuel actuellement).
- Migrer `_pending_mfa` (in-memory) vers Redis ou table Supabase quand le worker
  scale horizontalement (E2 single-instance pour MVP).
- Activer Captcha sur Supabase Auth quand on ouvre publiquement.
- Configurer HIBP (Leaked password protection) — Pro plan only.
- SonarQube Quality Gate custom (coverage 95% on new code) à finaliser dans la UI.
