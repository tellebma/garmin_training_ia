'use client'

import { useEffect, useState } from 'react'
import { submitGarminMfa } from '@/app/actions/garmin-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'

interface Props {
  challengeId: string
  onConnected: () => void
  onCancel: () => void
}

function formatCooldown(seconds: number): string {
  if (seconds >= 60) {
    const m = Math.ceil(seconds / 60)
    return `${String(m)} min`
  }
  return `${String(seconds)}s`
}

function buttonLabel(args: {
  loading: boolean
  onCooldown: boolean
  remainingSec: number
}): string {
  if (args.loading) return 'Vérification...'
  if (args.onCooldown) return `Réessaye dans ${formatCooldown(args.remainingSec)}`
  return 'Valider'
}

export function MfaForm({ challengeId, onConnected, onCancel }: Readonly<Props>) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)
  const [cooldownUntil, setCooldownUntil] = useState<number | null>(null)
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    if (cooldownUntil === null) return
    const id = setInterval(() => {
      setNow(Date.now())
    }, 1000)
    return () => {
      clearInterval(id)
    }
  }, [cooldownUntil])

  const remainingSec =
    cooldownUntil !== null ? Math.max(0, Math.ceil((cooldownUntil - now) / 1000)) : 0
  const onCooldown = remainingSec > 0

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    if (onCooldown) return
    setLoading(true)
    try {
      const result = await submitGarminMfa(challengeId, code)
      switch (result.status) {
        case 'connected':
          toast.success('Compte Garmin connecté !')
          onConnected()
          break
        case 'invalid_code': {
          const retry = result.retry_after_seconds ?? 60
          setCooldownUntil(Date.now() + retry * 1000)
          toast.error(`Code MFA invalide — patiente ${formatCooldown(retry)}`)
          break
        }
        case 'challenge_expired':
          toast.error('Challenge expiré, réessaye depuis le début')
          onCancel()
          break
        case 'challenge_user_mismatch':
          toast.error('Challenge invalide pour cet utilisateur')
          onCancel()
          break
        case 'rate_limited': {
          const retry = result.retry_after_seconds ?? 30 * 60
          setCooldownUntil(Date.now() + retry * 1000)
          toast.error(`Garmin nous a rate-limités. Réessaye dans ${formatCooldown(retry)}.`, {
            duration: 15_000,
          })
          break
        }
        case 'garmin_error':
          toast.error(`Garmin a renvoyé une erreur (${result.type}). Code: ${result.error_id}`, {
            duration: 15_000,
          })
          break
        case 'unexpected_error':
          console.error('Garmin MFA unexpected error:', result)
          toast.error(
            `Erreur inattendue (${result.type}). Code: ${result.error_id} — partage ce code pour debug.`,
            { duration: 15_000 }
          )
          break
      }
    } catch (err) {
      toast.error(`Erreur: ${(err as Error).message}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="w-full max-w-sm space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="mfa-code">Code à 6 chiffres reçu par email/SMS</Label>
        <Input
          id="mfa-code"
          inputMode="numeric"
          maxLength={8}
          value={code}
          onChange={(e) => {
            setCode(e.target.value)
          }}
          required
          disabled={loading || onCooldown}
        />
      </div>
      <div className="flex gap-2">
        <Button
          type="submit"
          disabled={loading || onCooldown || code.length < 4}
          className="flex-1"
        >
          {buttonLabel({ loading, onCooldown, remainingSec })}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
          Annuler
        </Button>
      </div>
    </form>
  )
}
