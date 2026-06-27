'use client'

import { useEffect, useState } from 'react'
import { triggerGarminSync } from '@/app/actions/garmin-sync'

type Feedback = { kind: 'info' | 'muted'; text: string } | null

export function SyncNowButton() {
  const [pending, setPending] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)

  // Auto sync on mount: fire-and-forget, silent on cooldown.
  useEffect(() => {
    void triggerGarminSync('auto').catch(() => {
      // Silent: the cron is the safety net.
    })
  }, [])

  async function onManual() {
    setPending(true)
    setFeedback(null)
    try {
      const result = await triggerGarminSync('manual')
      if (result.status === 'started') {
        setFeedback({ kind: 'info', text: 'Synchronisation lancée' })
      } else if (result.status === 'cooldown') {
        const minutes = Math.max(1, Math.ceil(result.retry_after_seconds / 60))
        setFeedback({ kind: 'muted', text: `Déjà à jour, réessaie dans ${String(minutes)} min` })
      } else if (result.status === 'no_credentials') {
        setFeedback({ kind: 'muted', text: 'Connecte ton compte Garmin pour synchroniser' })
      } else {
        setFeedback({ kind: 'muted', text: 'Synchronisation indisponible' })
      }
    } catch {
      setFeedback({ kind: 'muted', text: 'Synchronisation indisponible, réessaie' })
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="flex items-center gap-3">
      <button
        type="button"
        onClick={() => void onManual()}
        disabled={pending}
        className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
      >
        {pending ? 'Synchronisation...' : 'Synchroniser'}
      </button>
      {feedback ? (
        <output className={feedback.kind === 'info' ? 'text-sm' : 'text-muted-foreground text-sm'}>
          {feedback.text}
        </output>
      ) : null}
    </div>
  )
}
