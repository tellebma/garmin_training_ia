# E9 — Cockpit de performance et suivi longitudinal

**Statut :** en cours, incrément 1 livré sur la branche E9
**Priorité :** P0
**Dépendances livrées :** synchronisation Garmin, plan Banister, briefing coach,
fiche activité détaillée, samples d'activité et décisions d'ajustement.

## Vision

Transformer les écrans de métriques en un véritable outil de décision coach.
L'application ne doit pas chercher à afficher toutes les valeurs disponibles :
elle doit relier entraînement prévu, travail réalisé, réponse physiologique,
ressenti et progression vers l'objectif.

Le cockpit doit répondre simplement à quatre questions :

1. Qu'est-ce qui a réellement été fait par rapport au plan ?
2. Comment l'athlète semble-t-il assimiler cette charge ?
3. Quels signaux montrent une progression, une stagnation ou un besoin de repos ?
4. Quelle action concrète est recommandée pour les prochaines séances ?

## Principes coach

- Comparer chaque métrique à la baseline individuelle et à une période pertinente.
- Croiser charge externe, charge interne et ressenti avant de recommander un
  maintien, une progression ou un allègement.
- Afficher la tendance et le contexte plutôt qu'une valeur quotidienne isolée.
- Expliquer les recommandations avec des faits observables et un niveau de confiance.
- Ne jamais présenter CTL, TSB, HRV, Body Battery ou une hausse de charge comme une
  prédiction certaine de blessure, de maladie ou de performance.
- Conserver une expérience utile quand certaines données Garmin sont absentes.

## Périmètre fonctionnel

### E9.1 — Cockpit hebdomadaire — P0

Faire de `/stats` un cockpit de suivi avec sélecteur 7, 28 et 90 jours et filtres
par discipline.

Indicateurs principaux :

- séances prévues, réalisées, manquées et ajoutées hors plan ;
- taux d'assiduité global et par discipline ;
- durée, distance, D+ et TSS prévus vs réalisés ;
- charge hebdomadaire et évolution par rapport aux semaines précédentes ;
- temps passé dans les zones cardio, puis puissance quand disponible ;
- répartition facile, modérée et intense ;
- espacement des séances exigeantes et jours de récupération ;
- séance clé de la semaine et statut de réalisation ;
- résumé coach : acquis, point de vigilance et prochaine décision.

Les graphiques doivent permettre un accès direct aux activités qui expliquent une
variation, sans multiplier les cartes décoratives.

### E9.2 — Feedback subjectif post-séance — P0

Ajouter après une activité un formulaire volontaire et rapide :

- RPE global de 1 à 10 ;
- fatigue générale de 1 à 5 ;
- courbatures de 1 à 5 ;
- douleur ou gêne de 0 à 5, avec zone et commentaire facultatifs ;
- humeur ou motivation de 1 à 5 ;
- séance perçue comme plus facile, conforme ou plus difficile que prévu.

Calculer la charge interne `durée en minutes × RPE`, sans remplacer TSS ou TRIMP.
Le briefing et les ajustements doivent pouvoir utiliser ce ressenti, notamment si
la difficulté perçue diverge plusieurs fois de la charge prévue.

Modèle de données pressenti : une table RLS `activity_feedback` unique par
`user_id + activity_id`, conservant les réponses, la date et la version du schéma.

### E9.3 — Récupération individualisée — P1

Créer une vue récupération fondée sur les tendances disponibles :

- HRV RMSSD et écart à la baseline glissante ;
- FC au repos et écart à la baseline ;
- durée, score, régularité et phases du sommeil ;
- stress moyen et Body Battery bas/haut ;
- charge récente, TSB et feedback subjectif ;
- fraîcheur de chaque source et indice de confiance du résumé.

Le score synthétique éventuel doit rester explicable. L'interface doit montrer les
facteurs favorables, défavorables et inconnus qui ont conduit à la recommandation.

### E9.4 — Progression par discipline — P1

Course :

- allure à fréquence cardiaque comparable et fréquence cardiaque à allure comparable ;
- dérive cardio, cadence, régularité et évolution sur parcours comparables ;
- progressivité du volume, de la durée et du D+.

Vélo :

- puissance à fréquence cardiaque comparable ;
- puissance normalisée, Intensity Factor et Variability Index si les samples et
  une FTP fiable sont disponibles ;
- évolution FTP, cadence, D+ et longues sorties.

Montée et trail :

- VAM, vitesse, FC et puissance par classe de pente ;
- régularité d'effort entre montée, plat et descente.

Natation :

- allure par 100 m, fréquence et nombre de mouvements, SWOLF et CSS lorsque les
  payloads Garmin permettent une ingestion fiable.

Chaque tendance doit préciser la fenêtre d'analyse, le nombre d'activités comparées
et les éventuels facteurs qui limitent la comparaison.

### E9.5 — Analyse avancée d'activité — P1

Compléter la fiche activité existante avec :

- tours, splits et intervalles ;
- respect des cibles de chaque bloc planifié ;
- temps et distribution dans les zones cardio et puissance ;
- D+ et D- ;
- puissance normalisée, IF et VI ;
- carte GPS si les coordonnées peuvent être stockées et exposées proprement ;
- température, respiration, Training Effect, VO2max et dynamiques spécifiques au
  sport selon la montre et la disponibilité Garmin.

Les champs Garmin non normalisés doivent être inventoriés avant d'étendre le schéma.
Une métrique absente ne doit jamais être simulée ou remplacée silencieusement.

### E9.6 — Préparation objectif — P2

Relier les tendances aux exigences de la prochaine course : volume, D+, durée
estimée, disciplines, transitions et spécificité des séances. Produire une synthèse
hebdomadaire avec progression observée, séance clé, manque principal, priorité de
récupération et recommandation de pacing ou nutrition quand elle est justifiée.

## Parcours et hiérarchie UI

- `/today` reste centré sur la décision du jour et reprend au maximum quatre
  signaux du cockpit.
- `/stats` devient la vue longitudinale principale, avec résumé hebdomadaire,
  filtres temporels et discipline, puis tendances détaillées.
- `/history/[id]` explique une activité et son impact sur la suite du plan.
- Le feedback post-séance est accessible depuis la fiche activité et proposé sans
  bloquer la consultation.
- Les couleurs représentent des états cohérents : favorable, attention, action
  requise et donnée inconnue. Elles ne reposent jamais seules sur la couleur.

## Contrat de recommandation

Chaque insight coach important expose :

- le constat ;
- les métriques et périodes utilisées ;
- la décision proposée ;
- le bénéfice recherché ;
- le niveau de confiance ;
- les données manquantes ou limites connues ;
- une `rule_id` reliée au référentiel de preuves quand la décision modifie charge,
  intensité ou récupération.

## Critères d'acceptation de l'epic

- L'utilisateur peut comparer le prévu et le réalisé sur 7, 28 et 90 jours.
- Le cockpit affiche charge, assiduité, intensité, récupération et progression sans
  exiger que toutes les métriques Garmin soient disponibles.
- Un feedback RPE peut être saisi, modifié et utilisé par le briefing coach.
- Les tendances sportives reposent sur des activités comparables et indiquent la
  taille de l'échantillon.
- Toute recommandation d'allègement ou de progression est expliquée et auditée.
- Les états chargement, vide, partiel, erreur et données anciennes sont couverts.
- Les calculs métier ont des tests unitaires avec cas limites et données absentes.
- Les parcours `/today`, `/stats` et `/history/[id]` sont couverts par des tests
  d'intégration ou E2E ciblés.
- Les graphiques restent lisibles sur mobile et desktop et n'altèrent pas les
  performances de chargement des pages.

## Ordre de livraison recommandé

1. Inventaire des données Garmin normalisées et disponibles dans `raw`.
2. Modèle `activity_feedback`, RLS, formulaire et charge session-RPE.
3. Agrégats prévu/réalisé et cockpit hebdomadaire E9.1.
4. Baselines et synthèse récupération E9.3.
5. Indicateurs course et vélo E9.4, puis natation selon les données réelles.
6. Tours, zones, carte et métriques avancées E9.5.
7. Préparation objectif E9.6 et synthèse hebdomadaire coach.

## Hors périmètre

- diagnostic médical ou détection automatique d'une pathologie ;
- prédiction garantie de blessure, surentraînement ou résultat de course ;
- recommandations nutritionnelles médicalisées ;
- score opaque agrégeant des données sans explication ;
- ajout d'une métrique uniquement parce qu'elle existe dans un payload Garmin.
