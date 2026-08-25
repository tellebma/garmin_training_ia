'use client'

import { useState, useTransition } from 'react'
import { useRouter } from 'next/navigation'
import { RotateCcw, Trash2, TriangleAlert } from 'lucide-react'
import { deleteActivity, restoreActivity } from '@/app/actions/activity-visibility'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'

interface Props {
  readonly activityId: string
  readonly excludedAt: string | null
  readonly excludedReason: string | null
}

/**
 * Supprimer une activité — cas type : le compteur vélo lancé en plus de la montre,
 * qui fait compter deux fois le même effort. La suppression est réversible : le
 * bandeau de restauration reste accessible depuis l'onglet « Supprimées ».
 */
export function ActivityDeleteForm({ activityId, excludedAt, excludedReason }: Readonly<Props>) {
  const router = useRouter()
  const [pending, startTransition] = useTransition()
  const [confirming, setConfirming] = useState(false)
  const [reason, setReason] = useState('')
  const [error, setError] = useState<string | null>(null)

  function run(action: () => Promise<{ success: boolean }>, redirectTo?: string): void {
    setError(null)
    startTransition(async () => {
      const result = await action()
      if (!result.success) {
        setError('Action impossible pour le moment.')
        return
      }
      setConfirming(false)
      if (redirectTo) router.push(redirectTo)
      else router.refresh()
    })
  }

  if (excludedAt) {
    return (
      <section className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-4">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <TriangleAlert size={16} /> Activité supprimée
        </p>
        <p className="text-muted-foreground mt-1 text-sm">
          Elle ne compte plus dans tes statistiques ni dans l’historique
          {excludedReason ? ` — motif : ${excludedReason}` : ''}.
        </p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3"
          disabled={pending}
          onClick={() => {
            run(() => restoreActivity(activityId))
          }}
        >
          <RotateCcw size={14} /> Restaurer cette activité
        </Button>
        {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
      </section>
    )
  }

  return (
    <section className="rounded-lg border p-4">
      <p className="text-sm font-semibold">Supprimer cette activité</p>
      <p className="text-muted-foreground mt-1 text-sm">
        Utile quand un même effort a été enregistré deux fois (montre + compteur, par exemple). Elle
        disparaît de l’historique et cesse de compter dans la charge et les statistiques ; elle
        reste restaurable depuis l’onglet « Supprimées ».
      </p>

      {confirming ? (
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-muted-foreground text-xs">
            <span className="block">Motif (facultatif)</span>
            <Input
              className="mt-1"
              maxLength={200}
              placeholder="doublon compteur vélo"
              value={reason}
              onChange={(event) => {
                setReason(event.target.value)
              }}
            />
          </label>
          <Button
            type="button"
            variant="destructive"
            size="sm"
            disabled={pending}
            onClick={() => {
              run(() => deleteActivity({ activityId, reason }), '/history')
            }}
          >
            <Trash2 size={14} /> Confirmer la suppression
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="sm"
            disabled={pending}
            onClick={() => {
              setConfirming(false)
            }}
          >
            Annuler
          </Button>
        </div>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="mt-3"
          onClick={() => {
            setConfirming(true)
          }}
        >
          <Trash2 size={14} /> Supprimer cette activité
        </Button>
      )}

      {error && <p className="mt-2 text-sm text-red-500">{error}</p>}
    </section>
  )
}
