'use server'

import { createClient } from '@/lib/supabase/server'
import { workerChat, type ChatResult } from '@/lib/worker'

export type AskCoachResult =
  | { success: true; conversationId: string; answer: string; toolsUsed: string[] }
  | { success: false; error: string }

/**
 * Traduit les statuts du worker en messages destinés à l'athlète.
 *
 * Un quota atteint n'est pas une panne : le message doit dire quoi faire, pas
 * afficher une erreur technique.
 */
function toUserMessage(result: Exclude<ChatResult, { status: 'ok' }>): string {
  switch (result.status) {
    case 'chat_disabled':
      return 'Le coach est momentanément indisponible. Réessaie plus tard.'
    case 'budget_exceeded':
      return 'Tu as atteint ton quota de questions pour ce mois-ci. Il se réinitialise le 1er.'
    case 'rate_limited':
      return 'Tu as posé beaucoup de questions coup sur coup. Laisse passer quelques minutes.'
    case 'conversation_not_found':
      return 'Cette conversation est introuvable. Démarres-en une nouvelle.'
    default:
      return "Le coach n'a pas pu répondre. Réessaie dans un instant."
  }
}

export async function askCoach(question: string, conversationId?: string): Promise<AskCoachResult> {
  const trimmed = question.trim()
  if (!trimmed) return { success: false, error: 'Pose une question.' }

  const supabase = await createClient()
  const { data } = await supabase.auth.getSession()
  const jwt = data.session?.access_token
  if (!jwt) return { success: false, error: 'Session expirée, reconnecte-toi.' }

  try {
    const result = await workerChat(jwt, trimmed, conversationId)
    if (result.status !== 'ok') return { success: false, error: toUserMessage(result) }
    return {
      success: true,
      conversationId: result.conversation_id,
      answer: result.answer,
      toolsUsed: result.tools_used,
    }
  } catch {
    // Le détail technique reste côté serveur (error_id dans les logs worker).
    return { success: false, error: "Le coach n'a pas répondu à temps. Réessaie." }
  }
}
