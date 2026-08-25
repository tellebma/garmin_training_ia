/**
 * La question « et maintenant ? » posée après une course (E26).
 *
 * Choix structurant : cet état est **dérivé**, jamais poussé. Le rattachement d'une
 * activité à une course arrive par trois chemins — le sync, le backfill sur tout
 * l'historique, et le tag manuel — et les trois auraient dû penser à armer un prompt.
 * Pire : `backfill_races` aurait ouvert une modale « Bravo ! » sur le premier triathlon
 * de 2024. Une requête à la lecture supprime le problème, et le tag manuel rétroactif
 * d'une course récente déclenche la question gratuitement.
 */

export type PostRacePromptSurface = 'sheet' | 'banner'

/** Au-delà, on n'interrompt plus : la bannière prend le relais. */
export const MAX_PROMPT_INTERRUPTIONS = 2

/** Une course plus ancienne que ça n'a plus rien à demander. */
export const PROMPT_FRESHNESS_DAYS = 14

export interface PostRacePromptRow {
  readonly id: string
  readonly race_date: string
  readonly name: string | null
  readonly post_race_choice: string | null
  readonly post_race_prompt_count: number | null
  readonly post_race_prompt_snoozed_until: string | null
}

function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10)
}

/** Bornes de la fenêtre de fraîcheur, incluses. */
export function promptWindow(today: Date): { readonly from: string; readonly to: string } {
  const from = new Date(today)
  from.setUTCDate(from.getUTCDate() - PROMPT_FRESHNESS_DAYS)
  return { from: isoDay(from), to: isoDay(today) }
}

/**
 * Comment poser la question pour cette course — ou pas du tout.
 *
 * `null` couvre tout ce qui ne doit rien déclencher : question déjà répondue, report non
 * échu, course hors fenêtre. La présence d'au moins une activité rattachée **non exclue**
 * (E24) est vérifiée par l'appelant, au moment de la requête : c'est elle qui distingue
 * « la course a eu lieu » de « la course était prévue ».
 */
export function postRacePromptSurface(
  race: PostRacePromptRow,
  today: Date = new Date()
): PostRacePromptSurface | null {
  if (race.post_race_choice) return null

  const { from, to } = promptWindow(today)
  if (race.race_date < from || race.race_date > to) return null

  const count = race.post_race_prompt_count ?? 0
  // Trois interruptions au maximum. Ensuite la question reste posée, mais elle attend
  // qu'on vienne à elle : reproposer une modale à chaque connexion pendant la coupure
  // post-course serait le comportement le plus agaçant possible.
  if (count >= MAX_PROMPT_INTERRUPTIONS) return 'banner'

  const snoozed = race.post_race_prompt_snoozed_until
  if (snoozed && snoozed > isoDay(today)) return null

  return 'sheet'
}
