'use client'

import { useRef, useState, useTransition } from 'react'
import { Send } from 'lucide-react'
import { askCoach } from '@/app/actions/coach-chat'
import { Button } from '@/components/ui/button'
import { cn } from '@/lib/utils'

interface ChatMessage {
  id: number
  role: 'user' | 'assistant' | 'error'
  content: string
  toolsUsed?: string[]
}

const SUGGESTIONS = [
  'Suis-je prêt pour ma prochaine course ?',
  'Pourquoi je me sens fatigué en ce moment ?',
  'Comment gérer mon effort sur ma prochaine sortie longue ?',
] as const

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [draft, setDraft] = useState('')
  const [conversationId, setConversationId] = useState<string | undefined>()
  const [isPending, startTransition] = useTransition()
  const nextId = useRef(0)

  function send(question: string) {
    const trimmed = question.trim()
    if (!trimmed || isPending) return

    const userMessage: ChatMessage = { id: nextId.current++, role: 'user', content: trimmed }
    setMessages((prev) => [...prev, userMessage])
    setDraft('')

    startTransition(async () => {
      const result = await askCoach(trimmed, conversationId)
      setMessages((prev) => [
        ...prev,
        result.success
          ? {
              id: nextId.current++,
              role: 'assistant',
              content: result.answer,
              toolsUsed: result.toolsUsed,
            }
          : { id: nextId.current++, role: 'error', content: result.error },
      ])
      if (result.success) setConversationId(result.conversationId)
    })
  }

  return (
    <div className="flex flex-col gap-4">
      {messages.length === 0 && (
        <div className="border-border bg-card rounded-lg border p-4">
          <p className="text-muted-foreground text-sm">
            Pose une question sur ton entraînement. Le coach lit tes données Garmin — charge,
            récupération, séances passées et à venir — au moment où il te répond.
          </p>
          <ul className="mt-3 flex flex-col gap-2">
            {SUGGESTIONS.map((suggestion) => (
              <li key={suggestion}>
                <button
                  type="button"
                  onClick={() => {
                    send(suggestion)
                  }}
                  disabled={isPending}
                  className="border-border hover:bg-accent w-full rounded-md border px-3 py-2 text-left text-sm transition-colors disabled:opacity-50"
                >
                  {suggestion}
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}

      <ol className="flex flex-col gap-3">
        {messages.map((message) => (
          <li
            key={message.id}
            className={cn(
              'rounded-lg px-4 py-3 text-sm',
              message.role === 'user' && 'bg-primary text-primary-foreground ml-auto max-w-[85%]',
              message.role === 'assistant' && 'border-border bg-card border',
              message.role === 'error' && 'border-destructive/40 bg-destructive/10 border'
            )}
          >
            {/* Le markdown est affiché tel quel : le rendu enrichi arrive avec le
                streaming (lot C). Le texte brut reste lisible entre-temps. */}
            <p className="whitespace-pre-wrap">{message.content}</p>
            {message.toolsUsed && message.toolsUsed.length > 0 && (
              <p className="text-muted-foreground mt-2 text-xs">
                Données consultées : {[...new Set(message.toolsUsed)].join(', ')}
              </p>
            )}
          </li>
        ))}
        {isPending && (
          <li className="border-border bg-card text-muted-foreground rounded-lg border px-4 py-3 text-sm">
            Le coach consulte tes données…
          </li>
        )}
      </ol>

      <form
        onSubmit={(event) => {
          event.preventDefault()
          send(draft)
        }}
        className="sticky bottom-20 flex gap-2 md:bottom-4"
      >
        <textarea
          value={draft}
          onChange={(event) => {
            setDraft(event.target.value)
          }}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && !event.shiftKey) {
              event.preventDefault()
              send(draft)
            }
          }}
          placeholder="Ta question…"
          rows={2}
          maxLength={2000}
          disabled={isPending}
          className="border-input bg-background focus-visible:ring-ring flex-1 resize-none rounded-md border px-3 py-2 text-sm focus-visible:ring-2 focus-visible:outline-none disabled:opacity-50"
        />
        <Button type="submit" disabled={isPending || draft.trim().length === 0} size="icon">
          <Send className="size-4" />
          <span className="sr-only">Envoyer</span>
        </Button>
      </form>
    </div>
  )
}
