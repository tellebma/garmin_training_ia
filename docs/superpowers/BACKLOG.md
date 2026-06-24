# Backlog — Garmin Training Coach

Ce fichier est la source de vérité du backlog post-MVP. Les specs détaillées
restent dans `docs/superpowers/specs/` et les plans d'exécution dans
`docs/superpowers/plans/`.

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
  interactifs. S'appuyer sur `activity_samples`.
- **E14.2 P1 — Carte d'activité** : afficher le tracé GPS dans `/history/[id]` avec
  dénivelé et survol corrélé FC/allure. Recoupe E9.5 et la spec E8a.
- **E14.3 P1 — Bulles explicatives** : infobulles sur charge (CTL), forme (TSB),
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
- **E15.3 P1 — Sync on-demand** : déclencher une sync à l'ouverture de l'app
  (pull-to-refresh) en plus du cron, pour réduire la latence perçue immédiatement.
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

- **E9.1 P0 — Cockpit hebdomadaire** : prévu vs réalisé, charge, durée, distance,
  dénivelé, assiduité, répartition par zones et équilibre intensité/récupération.
- **E9.2 P0 — Feedback subjectif** : RPE post-séance, fatigue, douleurs,
  courbatures et humeur ; calcul de charge session-RPE et comparaison entre
  difficulté prévue et ressentie.
- **E9.3 P1 — Récupération individualisée** : tendances HRV, FC au repos,
  sommeil, stress et Body Battery comparées à la baseline personnelle, avec
  fraîcheur et niveau de confiance des données.
- **E9.4 P1 — Progression par discipline** : efficacité allure/FC en course,
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

### EPIC E17 — Déploiement automatisé des migrations Supabase

**Priorité : P1 — Statut : à planifier**

Aujourd'hui les migrations (`supabase/migrations/*.sql`) sont appliquées **à la main**
dans le dashboard : aucune automatisation CI, pas de `config.toml`, pas de `db push`.
Ce pas manuel est un footgun récurrent — un merge qui ajoute une migration peut partir
en prod sans que le schéma soit à jour, cassant le worker (écriture sur colonne absente)
ou la fiche activité. Cas vécu : la migration `20260624000000_carto_gps.sql` (livrable A
cartes GPS) reste à appliquer manuellement après le merge de la PR #57.

Objectif : un merge sur `main` qui contient une migration l'applique de façon **tracée,
validée et reproductible**, sans abandonner le contrôle humain sur la prod.

- **E17.1 P1 — Job CI `supabase db push` sur `main`** : un job GitHub Actions
  (`supabase link --project-ref peiyrqplymdlmlpsbqzu` puis `supabase db push`, idempotent)
  déclenché sur push `main`. Secrets à ajouter : `SUPABASE_ACCESS_TOKEN`, project-ref,
  mot de passe DB.
- **E17.2 P1 — Gate `production` avec required reviewer** : envelopper le job dans un
  GitHub Environment `production` exigeant une approbation manuelle avant tout DDL.
  Justification : pas de staging, le `db push` va *directement* en prod, on garde donc
  un clic humain de validation.
- **E17.3 P1 — Contrat de migration backward-compatible (expand/contract)** : documenter
  et faire respecter que toute migration soit additive d'abord (les suppressions de colonnes
  arrivent une version après le déploiement du code qui ne les lit plus). Neutralise la
  **course avec le deploy Vercel** : le merge déclenche le deploy front *en parallèle* du
  job migration, donc le nouveau code ne doit jamais lire une colonne avant qu'elle existe.
  Les migrations actuelles respectent déjà ce contrat (toutes additives).
- **E17.4 P2 — Smoke check post-migration + runbook** : vérification automatique que les
  objets attendus existent après push, et procédure de rollback/correction documentée.
- **E17.5 P2 — Génération des types Supabase post-push** : enchaîner la génération des types
  `Database` depuis les migrations (recoupe « Générer les types Supabase » ci-dessous).

Alternative légère (si jugé trop lourd pour un MVP solo) : pas de CI, mais un script
`pnpm db:push` + rappel dans le template de PR — moins sûr, zéro secret CI à gérer.

Critère : plus aucune migration oubliée ; l'application du schéma est standardisée,
auditée et validée avant d'atteindre la prod.

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

### P0 — Identité numérique et style graphique coach

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

### P1 — Pédagogie des métriques (bulles explicatives) (E14.3)

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
