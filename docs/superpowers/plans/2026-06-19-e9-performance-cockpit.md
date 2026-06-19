# Plan d'exécution E9 — Cockpit de performance

Ce plan suit l'epic décrite dans
`docs/superpowers/specs/2026-06-19-e9-performance-cockpit-design.md`.

## Incrément 1 — Fondations et cockpit V1

- [x] Inventorier les données Garmin normalisées et les métriques déjà affichées.
- [x] Ajouter `activity_feedback` avec validation, RLS et trigger `updated_at`.
- [x] Ajouter la saisie RPE, fatigue, courbatures, douleur, humeur et difficulté
  perçue dans la fiche activité.
- [x] Calculer la charge session-RPE sans remplacer TSS.
- [x] Apparier séances planifiées et activités par date et discipline.
- [x] Calculer assiduité, séances manquées, activités hors plan, durée, TSS, D+ et
  détail par discipline.
- [x] Recomposer `/stats` avec filtres 7/28/90 jours et discipline.
- [x] Couvrir les calculs, l'action serveur et le formulaire par des tests unitaires.
- [ ] Appliquer la migration `20260619000000_activity_feedback.sql` sur Supabase.

## Incrément 2 — Ressenti utilisé par le coach

- [ ] Charger les feedbacks récents dans le worker.
- [ ] Ajouter au `activity_review` la charge session-RPE, la difficulté perçue et
  les signaux répétés de fatigue, douleur ou séance plus dure que prévu.
- [ ] Utiliser ces signaux dans `/coach/daily-briefing` et les ajustements proposés.
- [ ] Exposer les faits et la confiance de la recommandation dans l'UI.

## Incrément 3 — Récupération individualisée

- [ ] Calculer les baselines glissantes HRV et FC au repos.
- [ ] Ajouter durée, régularité et phases du sommeil.
- [ ] Croiser stress, Body Battery, charge récente et ressenti.
- [ ] Afficher fraîcheur, données manquantes et niveau de confiance.

## Incrément 4 — Progression par discipline

- [ ] Course : allure/FC, FC/allure, cadence et dérive sur activités comparables.
- [ ] Vélo : puissance/FC, puissance normalisée, IF et VI avec FTP fiable.
- [ ] Trail : VAM et régularité par classe de pente.
- [ ] Natation : inventorier puis normaliser allure/100 m, mouvements, SWOLF et CSS.

## Incrément 5 — Activité avancée et objectif

- [ ] Ingérer tours, splits, intervalles et zones puissance.
- [ ] Ajouter D-, carte GPS et métriques Garmin spécialisées disponibles.
- [ ] Relier la progression aux exigences de la prochaine course.
- [ ] Produire la synthèse hebdomadaire coach et les priorités de la semaine.
