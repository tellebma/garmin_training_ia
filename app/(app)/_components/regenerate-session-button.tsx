'use client'

import { useState, useTransition } from 'react'
import { Button } from '@/components/ui/button'
import { regenerateSession } from '@/app/actions/sessions'

interface Props {
  sessionId: string
}

export function RegenerateSessionButton({ sessionId }: Readonly<Props>) {
  const [pending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)

  function handleClick(): void {
    setError(null)
    startTransition(async () => {
      const r = await regenerateSession(sessionId)
      if (!r.success) setError(r.error)
    })
  }

  return (
    <div>
      <Button variant="outline" size="sm" onClick={handleClick} disabled={pending}>
        {pending ? 'Régénération…' : 'Régénérer'}
      </Button>
      {error !== null && <p className="text-destructive mt-1 text-xs">{error}</p>}
    </div>
  )
}
