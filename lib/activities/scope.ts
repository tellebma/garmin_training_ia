/**
 * Portée des activités qui comptent (E24).
 *
 * Une activité peut être supprimée par l'athlète — cas vécu : compteur vélo lancé
 * en plus de la montre le jour de la course, donc deux lignes pour un seul effort.
 * La suppression est réversible (`activities.excluded_at`), et l'activité exclue ne
 * doit plus apparaître dans l'historique ni peser sur les statistiques.
 *
 * Le risque n'est pas de poser le filtre, c'est de l'oublier au prochain écran :
 * toute lecture d'`activities` qui alimente un écran ou une métrique passe par
 * `countedActivities()`, un seul point greppable. Deux exceptions volontaires : la
 * fiche `/history/[id]`, qui doit pouvoir ouvrir une activité supprimée pour la
 * restaurer, et la liste des supprimées elle-même (`excludedActivities`).
 */

interface ExclusionFilterable<T> {
  is: (column: string, value: null) => T
  not: (column: string, operator: string, value: null) => T
}

/** Restreint une requête `activities` aux activités qui comptent. */
export function countedActivities<T extends ExclusionFilterable<T>>(query: T): T {
  return query.is('excluded_at', null)
}

/** L'inverse : uniquement les activités supprimées (écran de restauration). */
export function excludedActivities<T extends ExclusionFilterable<T>>(query: T): T {
  return query.not('excluded_at', 'is', null)
}
