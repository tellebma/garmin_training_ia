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
  (Sentry — voir les erreurs des amis), E9.4 (progression par discipline, spec+plan prêts).
  E13.2 (déjà P0) est **V1 livrée** (PR #75, mergée 2026-07-02).
- **Rétrogradés en P2** (polish UX différé) : « Identité numérique / `DESIGN.md` »
  (était P0), E14.3 bulles explicatives, carte « dernière activité » de `/today`.
- Inchangés : E15.1 Strava (P1, plus gros chantier), E18 admin/coût IA (P1).

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
- **E14.3 P2 — Bulles explicatives** (rétrogradé P1 → P2 le 2026-06-28) : infobulles sur charge (CTL), forme (TSB),
  fatigue (ATL), HRV, TSS, zones, dérive cardio. Expliquer « c'est quoi » et « comment
  l'utiliser pour progresser » en langage simple, plus un glossaire accessible.

### EPIC E15 — Ingestion multi-source et quasi temps réel

**Priorité : P1 — Statut : à planifier**

Récupérer les activités plus vite sans seulement augmenter la fréquence du polling.

- **E15.1 P1 — Intégration Strava** : OAuth + webhooks (push à chaque activité),
  gratuit en usage perso. Point d'ingestion unifié quasi temps réel
  (Garmin -> Strava -> app). Chemin recommandé.
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
- **E9.4 P0 — Progression par discipline** (remontée P0 le 2026-06-28) : efficacité allure/FC en course,
  puissance/FC et FTP à vélo, performance en montée, métriques natation et
  détection de progression, stagnation ou charge mal assimilée.
- **E9.5 P1 — Analyse avancée d'activité** : tours/intervalles, temps en zones,
  puissance normalisée, IF/VI, D+/D-, carte GPS et métriques Garmin spécialisées
  lorsqu'elles sont disponibles.
- **E9.6 P2 — Préparation objectif** : adéquation de l'entraînement aux exigences
  de la course, évolution de la préparation, stratégie de pacing et priorités de
  la semaine.

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

### EPIC E18 — Console d'administration & observabilité beta

**Priorité : P1 — Statut : à planifier**

Vue `/admin` réservée à l'owner pour superviser la beta privée d'un coup d'œil :
adoption, volume de données synchronisées, santé des syncs et **coût IA réel**. Le besoin
structurant : la conso de tokens IA n'est tracée nulle part aujourd'hui
(`openai_client.py` jette `resp.usage`), donc l'EPIC est en deux temps — instrumenter,
puis afficher. Spec : `docs/superpowers/specs/2026-06-28-e18-admin-console-design.md`.

- **E18.1 P1 — Instrumentation conso LLM** : nouvelle table `llm_usage` (un row par appel
  OpenAI, RLS deny-all), capture de `resp.usage` dans `openai_client.py`, tarif versionné
  en code (`MODEL_PRICING`) pour calculer `cost_usd`, helper `record_llm_usage` branché sur
  tous les sites d'appel LLM (séances + briefing). Best-effort : ne casse jamais la
  génération. Prérequis de E18.2/E18.3.
- **E18.2 P1 — Agrégats admin** : RPC `admin_overview()` `security definer` (garde owner
  interne) renvoyant users (total + actifs 7j), activités (total + 7j), tokens + `cost_usd`
  7j, santé sync (succès/échecs derniers crons), série coût/jour 7j.
- **E18.3 P1 — Page `/admin`** : route Next.js gardée par email owner, cartes de stats +
  graphe coût IA/jour (réutilise charts E14.1), lecture seule, UI dark existante.
- **Suite (Todo séparés)** : détail par utilisateur, alerting/budget cap IA, gestion de
  l'allowlist depuis l'UI, multi-admin (flag `is_admin`), affichage du coût converti en €.

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
- E16.1 P0 — Supprimer le double appel auth (layout + `requireOnboarded`) via `cache()` ou
  garde unique au layout. Gain transversal sur le TTFB de toutes les pages.
  (Remontée P0 le 2026-06-28 — plafond de latence partagé, fix court.)
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

- Objectif : récupérer les activités plus vite sans seulement augmenter la fréquence du
  cron de polling.
- Strava : API publique OAuth + webhooks (push à chaque nouvelle activité), gratuite en
  usage perso/petit volume. Beaucoup d'athlètes poussent déjà Garmin -> Strava, donc
  Strava peut servir de point d'ingestion unifié quasi temps réel.
- Garmin officiel : Garmin Health/Activity API propose des webhooks push mais réservée
  au programme partenaire (validation B2B, pas instantané). La lib actuelle
  `python-garminconnect` est non officielle et ne fait que du polling.
- Piste court terme sans nouvelle intégration : déclencher une sync à l'ouverture de
  l'app (pull-to-refresh / on-demand) en plus du cron, pour réduire la latence perçue.
- **Pull au connect/reconnect (P0, quick win) — V1 livrée** : `connect.py` déclenche une sync
  immédiate (thread daemon non bloquant) après chaque `connected` (connexion ou MFA réussie)
  via `_trigger_initial_sync`. L'athlète qui vient de lier son compte voit ses données sans
  attendre le cron. Voir E15.4 ci-dessus.
- À trancher : Strava webhooks (recommandé, réaliste) vs attente du programme Garmin.

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

### P2 — Widget « Mes cols » sur /stats — V1 en revue (PR #87)

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

## Post-MVP technique

- Custom SMTP Supabase (Resend gratuit 100/jour) — rate limits du SMTP intégré.
- Vercel Speed Insights pour monitoring perf prod.
- Script `scripts/sync-email-templates.ts` qui pousse les templates depuis le repo
  via Supabase Management API (vs sync manuel actuellement).
- Migrer `_pending_mfa` (in-memory) vers Redis ou table Supabase quand le worker
  scale horizontalement (E2 single-instance pour MVP).
- Activer Captcha sur Supabase Auth quand on ouvre publiquement.
- Configurer HIBP (Leaked password protection) — Pro plan only.
- SonarQube Quality Gate custom (coverage 95% on new code) à finaliser dans la UI.
