# Backlog — Garmin Training Coach

Ce fichier est la source de vérité du backlog post-MVP. Les specs détaillées
restent dans `docs/superpowers/specs/` et les plans d'exécution dans
`docs/superpowers/plans/`.

## Coaching sportif / performance

Objectif produit : les recommandations doivent se rapprocher d'un vrai coach
sportif, pas seulement d'un générateur de séances. Le système doit observer
l'historique, identifier les tendances, expliquer les risques et proposer des
ajustements concrets.

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
- Suite : ingérer les samples Garmin détaillés pour produire de vrais graphes
  temporels altitude / FC / allure / puissance / cadence et des analyses par segment.
- Statut V1 action 2 : le worker récupère les détails Garmin manquants via
  `get_activity_details`, stocke les samples dans `activity_samples`, et la fiche
  activité affiche les courbes temporelles quand les samples sont disponibles.
- Statut V1 action 3 : la fiche activité calcule désormais les zones cardio à partir
  des samples et segmente l'effort en montée / plat / descente avec distance, pente,
  FC moyenne et vitesse moyenne. Les recommandations coach utilisent ces signaux
  pour pointer une intensité trop élevée ou une montée prise trop haut en cardio.
- Suite : détecter la dérive cardio et le pacing irrégulier par segment pour produire
  des conseils encore plus proches d'un retour d'entraîneur après séance.

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

### P1 — Générer les types Supabase

- Ajouter les types `Database` générés depuis les migrations.
- Typer les clients Supabase et réduire les casts dans les pages dashboard.

### P1 — Observabilité production

- Initialiser Sentry côté worker.
- Ajouter logs structurés et métriques : durée sync, erreurs Garmin, erreurs OpenAI,
  jobs scheduler, rate limits, génération de plan/séance.

### P2 — Élargir E2E et Lighthouse aux parcours réels

- Ajouter parcours authentifié seedé ou mocké : onboarding, Garmin mocké, `/today`,
  `/plan`, `/profile`, `/stats`.
- Étendre Lighthouse au-delà de `/login`.

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
