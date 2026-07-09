'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { Button } from '@/components/ui/button'
import { setFeatureFlag } from '../actions'
import { isFlagActive, type FeatureFlagRow } from '@/lib/admin/types'

const DURATIONS: { label: string; hours: number }[] = [
  { label: '1h', hours: 1 },
  { label: '24h', hours: 24 },
  { label: '7j', hours: 24 * 7 },
]

export function FeatureFlagsList({ flags }: { readonly flags: FeatureFlagRow[] }) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [durationHours, setDurationHours] = useState<number>(24)

  function toggle(flag: FeatureFlagRow) {
    const requiresExpiry = flag.key === 'public_registration_enabled'
    const nextEnabled = !isFlagActive(flag)
    startTransition(async () => {
      const expiresAt =
        requiresExpiry && nextEnabled
          ? new Date(Date.now() + durationHours * 3_600_000).toISOString()
          : null
      await setFeatureFlag({ key: flag.key, enabled: nextEnabled, expiresAt })
      router.refresh()
    })
  }

  return (
    <ul className="divide-y rounded-md border">
      {flags.map((flag) => {
        const active = isFlagActive(flag)
        return (
          <li key={flag.key} className="flex items-center justify-between gap-4 p-4">
            <div>
              <p className="text-sm font-medium">{flag.key}</p>
              <p className="text-muted-foreground text-xs">{flag.description}</p>
            </div>
            <div className="flex items-center gap-2">
              {flag.key === 'public_registration_enabled' && !active && (
                <select
                  aria-label="Durée d'activation"
                  className="bg-background rounded border px-2 py-1 text-xs"
                  value={durationHours}
                  onChange={(e) => {
                    setDurationHours(Number(e.target.value))
                  }}
                >
                  {DURATIONS.map((d) => (
                    <option key={d.label} value={d.hours}>
                      {d.label}
                    </option>
                  ))}
                </select>
              )}
              <Button
                size="sm"
                variant={active ? 'destructive' : 'default'}
                disabled={pending}
                onClick={() => {
                  toggle(flag)
                }}
              >
                {active ? 'Désactiver' : 'Activer'}
              </Button>
            </div>
          </li>
        )
      })}
    </ul>
  )
}
