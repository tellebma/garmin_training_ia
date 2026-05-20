'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepPerf, syncGarminProfile } from '../actions'
import type { PerfInput } from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: PerfInput & { garmin_synced_at: string | null }
  onDone: (nextStep: Step | null) => void
}

export function StepPerfForm({ defaultValues, onDone }: Readonly<Props>) {
  const [ftp, setFtp] = useState<string>(defaultValues.ftp_watts?.toString() ?? '')
  const [vma, setVma] = useState<string>(defaultValues.vma_kmh?.toString() ?? '')
  const [fcmax, setFcmax] = useState<string>(defaultValues.fc_max_bpm?.toString() ?? '')
  const [syncedAt, setSyncedAt] = useState<string | null>(defaultValues.garmin_synced_at)
  const [syncing, setSyncing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  // Auto-fetch only on first visit (garmin_synced_at IS NULL)
  useEffect(() => {
    if (syncedAt !== null) return
    // Use object so the async IIFE can observe the mutation across the await boundary
    const guard = { cancelled: false }
    void (async () => {
      setSyncing(true)
      const r = await syncGarminProfile()
      if (guard.cancelled) return
      setSyncing(false)
      if (r.status === 'ok') {
        if (r.fetched.ftp_watts) setFtp(r.fetched.ftp_watts.toString())
        if (r.fetched.vma_kmh) setVma(r.fetched.vma_kmh.toString())
        if (r.fetched.fc_max_bpm) setFcmax(r.fetched.fc_max_bpm.toString())
        setSyncedAt(new Date().toISOString())
      } else if (r.status === 'rate_limited') {
        toast.warning('Garmin a temporisé — remplis manuellement ou retente plus tard.')
        setSyncedAt(new Date().toISOString()) // mark to avoid re-trigger loop
      } else if (r.status === 'auth_failed') {
        toast.error('Connexion Garmin expirée — reconnecte depuis /profile.')
      }
    })()
    return () => {
      guard.cancelled = true
    }
  }, [syncedAt])

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const result = await saveStepPerf({
      ftp_watts: ftp ? Number.parseInt(ftp, 10) : undefined,
      vma_kmh: vma ? Number.parseFloat(vma) : undefined,
      fc_max_bpm: fcmax ? Number.parseInt(fcmax, 10) : undefined,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) {
        setErrors(result.errors as Record<string, string[]>)
        toast.error('Corrige les erreurs avant de continuer.')
      } else {
        toast.error('Erreur de sauvegarde, réessaye.')
      }
      return
    }
    onDone(result.nextStep)
  }

  const fmtSynced = syncedAt
    ? new Date(syncedAt).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
    : null

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
      noValidate
    >
      {syncing && <p className="text-muted-foreground text-sm">↻ Récupération depuis Garmin...</p>}
      {fmtSynced && !syncing && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400">
          ↻ Synchronisé de Garmin le {fmtSynced}
        </p>
      )}
      <p className="text-muted-foreground text-xs">
        Tous facultatifs. Si tu ne sais pas, laisse vide — ta montre Garmin te donne ces valeurs
        dans Performance &gt; Statistiques.
      </p>

      <div className="space-y-2">
        <Label htmlFor="ftp">
          FTP (watts){' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="ftp"
          type="number"
          min={50}
          max={600}
          value={ftp}
          onChange={(e) => {
            setFtp(e.target.value)
          }}
          placeholder="ex: 245"
        />
        {errors.ftp_watts?.[0] && <p className="text-destructive text-xs">{errors.ftp_watts[0]}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="vma">
          VMA (km/h){' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="vma"
          type="number"
          step="0.1"
          min={5}
          max={30}
          value={vma}
          onChange={(e) => {
            setVma(e.target.value)
          }}
          placeholder="ex: 16.5"
        />
        {errors.vma_kmh?.[0] && <p className="text-destructive text-xs">{errors.vma_kmh[0]}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="fcmax">
          FC max (bpm){' '}
          <span className="text-muted-foreground ml-1 text-xs font-normal">(optionnel)</span>
        </Label>
        <Input
          id="fcmax"
          type="number"
          min={100}
          max={230}
          value={fcmax}
          onChange={(e) => {
            setFcmax(e.target.value)
          }}
          placeholder="ex: 188"
        />
        {errors.fc_max_bpm?.[0] && (
          <p className="text-destructive text-xs">{errors.fc_max_bpm[0]}</p>
        )}
      </div>

      <Button type="submit" disabled={loading || syncing} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}
