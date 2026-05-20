'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepPerf, syncGarminProfile } from '@/app/(app)/onboarding/actions'
import type { PerfInput } from '@/lib/onboarding/schemas'

interface Props {
  initial: PerfInput & { garmin_synced_at: string | null }
}

export function PerfEditForm({ initial }: Readonly<Props>) {
  const [edit, setEdit] = useState(false)
  const [ftp, setFtp] = useState<string>(initial.ftp_watts?.toString() ?? '')
  const [vma, setVma] = useState<string>(initial.vma_kmh?.toString() ?? '')
  const [fcmax, setFcmax] = useState<string>(initial.fc_max_bpm?.toString() ?? '')
  const [syncedAt, setSyncedAt] = useState<string | null>(initial.garmin_synced_at)
  const [syncing, setSyncing] = useState(false)
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  function handleCancel() {
    setEdit(false)
    setFtp(initial.ftp_watts?.toString() ?? '')
    setVma(initial.vma_kmh?.toString() ?? '')
    setFcmax(initial.fc_max_bpm?.toString() ?? '')
    setErrors({})
  }

  async function handleSyncGarmin() {
    setSyncing(true)
    const r = await syncGarminProfile()
    setSyncing(false)
    if (r.status === 'ok') {
      const fetchedAny =
        r.fetched.ftp_watts !== undefined ||
        r.fetched.vma_kmh !== undefined ||
        r.fetched.fc_max_bpm !== undefined
      if (r.fetched.ftp_watts) setFtp(r.fetched.ftp_watts.toString())
      if (r.fetched.vma_kmh) setVma(r.fetched.vma_kmh.toString())
      if (r.fetched.fc_max_bpm) setFcmax(r.fetched.fc_max_bpm.toString())
      setSyncedAt(new Date().toISOString())
      if (fetchedAny) {
        toast.success('Données Garmin synchronisées')
      } else {
        toast.warning(
          'Garmin n’a renvoyé aucune valeur (FTP / VMA / FCmax). Renseigne-les manuellement ou configure-les dans Garmin Connect.'
        )
      }
    } else if (r.status === 'rate_limited') {
      toast.warning('Garmin a temporisé — retente plus tard.')
    } else if (r.status === 'auth_failed') {
      toast.error('Connexion Garmin expirée — reconnecte depuis /profile.')
    } else if (r.status === 'no_credentials') {
      toast.error('Aucun compte Garmin connecté.')
    } else {
      toast.error('Erreur lors de la synchronisation Garmin.')
    }
  }

  const fmtSynced = syncedAt
    ? new Date(syncedAt).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
    : null

  if (!edit) {
    return (
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Performance</h2>
          <Button
            variant="outline"
            size="sm"
            onClick={() => {
              setEdit(true)
            }}
          >
            Modifier
          </Button>
        </div>
        <dl className="text-muted-foreground grid grid-cols-3 gap-x-4 text-sm">
          <div>
            <dt className="text-xs tracking-wide uppercase">FTP</dt>
            <dd className="text-foreground">{ftp ? `${ftp} W` : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs tracking-wide uppercase">VMA</dt>
            <dd className="text-foreground">{vma ? `${vma} km/h` : '—'}</dd>
          </div>
          <div>
            <dt className="text-xs tracking-wide uppercase">FC max</dt>
            <dd className="text-foreground">{fcmax ? `${fcmax} bpm` : '—'}</dd>
          </div>
        </dl>
        {fmtSynced && (
          <p className="text-xs text-emerald-600 dark:text-emerald-400">
            Synchronisé de Garmin le {fmtSynced}
          </p>
        )}
      </section>
    )
  }

  async function handleSave() {
    setLoading(true)
    setErrors({})
    const r = await saveStepPerf({
      ftp_watts: ftp ? Number.parseInt(ftp, 10) : undefined,
      vma_kmh: vma ? Number.parseFloat(vma) : undefined,
      fc_max_bpm: fcmax ? Number.parseInt(fcmax, 10) : undefined,
    })
    setLoading(false)
    if (!r.success) {
      if ('errors' in r) setErrors(r.errors as Record<string, string[]>)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    setEdit(false)
    toast.success('Sauvegardé')
  }

  return (
    <section className="space-y-4 rounded-lg border p-6">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Performance</h2>
        <Button
          variant="outline"
          size="sm"
          onClick={() => {
            void handleSyncGarmin()
          }}
          disabled={syncing || loading}
        >
          {syncing ? 'Sync...' : '↻ Sync Garmin'}
        </Button>
      </div>

      {syncing && <p className="text-muted-foreground text-sm">↻ Récupération depuis Garmin...</p>}
      {fmtSynced && !syncing && (
        <p className="text-xs text-emerald-600 dark:text-emerald-400">
          Synchronisé de Garmin le {fmtSynced}
        </p>
      )}
      <p className="text-muted-foreground text-xs">
        Tous facultatifs — ta montre Garmin te donne ces valeurs dans Performance &gt; Statistiques.
      </p>

      <div className="space-y-2">
        <Label htmlFor="perf-ftp">FTP (watts)</Label>
        <Input
          id="perf-ftp"
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
        <Label htmlFor="perf-vma">VMA (km/h)</Label>
        <Input
          id="perf-vma"
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
        <Label htmlFor="perf-fcmax">FC max (bpm)</Label>
        <Input
          id="perf-fcmax"
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

      <div className="flex gap-2">
        <Button
          onClick={() => {
            void handleSave()
          }}
          disabled={loading || syncing}
        >
          {loading ? 'Sauvegarde...' : 'Enregistrer'}
        </Button>
        <Button variant="outline" onClick={handleCancel} disabled={loading || syncing}>
          Annuler
        </Button>
      </div>
    </section>
  )
}
