'use client'

import { useState, useTransition } from 'react'
import { Button } from '@/components/ui/button'
import { applySessionAdjustment } from '@/app/actions/sessions'

interface Props {
  readonly sessionId: string
  readonly suggestedSessionType: string
}

export function NextSessionAdjustmentActions({ sessionId, suggestedSessionType }: Readonly<Props>) {
  const [pending, startTransition] = useTransition()
  const [status, setStatus] = useState<'idle' | 'accepted' | 'ignored'>('idle')
  const [error, setError] = useState<string | null>(null)

  function accept(): void {
    setError(null)
    startTransition(async () => {
      const result = await applySessionAdjustment(sessionId, suggestedSessionType)
      if (!result.success) {
        setError(result.error)
        return
      }
      setStatus('accepted')
    })
  }

  function ignore(): void {
    setError(null)
    setStatus('ignored')
  }

  if (status === 'accepted') {
    return <p className="text-muted-foreground mt-2 text-xs">Ajustement appliqué.</p>
  }
  if (status === 'ignored') {
    return <p className="text-muted-foreground mt-2 text-xs">Suggestion ignorée pour le moment.</p>
  }

  return (
    <div className="mt-3 flex flex-wrap items-center gap-2">
      <Button size="sm" onClick={accept} disabled={pending}>
        {pending ? 'Application...' : 'Accepter'}
      </Button>
      <Button size="sm" variant="outline" onClick={ignore} disabled={pending}>
        Ignorer
      </Button>
      {error !== null && <p className="text-destructive w-full text-xs">{error}</p>}
    </div>
  )
}
