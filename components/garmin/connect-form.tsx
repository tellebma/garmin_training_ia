'use client'

import { useEffect, useState } from 'react'
import { connectGarmin } from '@/app/actions/garmin-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'

interface Props {
  onMfaRequired: (challengeId: string) => void
  onConnected: () => void
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
  if (args.loading) return 'Connexion...'
  if (args.onCooldown) return `Réessaye dans ${formatCooldown(args.remainingSec)}`
  return 'Connecter Garmin'
}

export function ConnectForm({ onMfaRequired, onConnected }: Readonly<Props>) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
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
      const result = await connectGarmin(email, password)
      switch (result.status) {
        case 'connected':
          toast.success('Compte Garmin connecté !')
          onConnected()
          break
        case 'mfa_required':
          onMfaRequired(result.challenge_id)
          break
        case 'invalid_credentials': {
          const retry = result.retry_after_seconds ?? 60
          setCooldownUntil(Date.now() + retry * 1000)
          toast.error(`Identifiants Garmin invalides — patiente ${formatCooldown(retry)}`)
          break
        }
        case 'rate_limited': {
          const retry = result.retry_after_seconds ?? 30 * 60
          setCooldownUntil(Date.now() + retry * 1000)
          toast.error(
            `Garmin nous a rate-limités. Réessaye dans ${formatCooldown(retry)} (sinon notre IP risque un ban plus long).`,
            { duration: 15_000 }
          )
          break
        }
        case 'garmin_error':
          toast.error(`Garmin a renvoyé une erreur (${result.type}). Code: ${result.error_id}`, {
            duration: 15_000,
          })
          break
        case 'unexpected_error':
          console.error('Garmin connect unexpected error:', result)
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
        <Label htmlFor="garmin-email">Email Garmin Connect</Label>
        <Input
          id="garmin-email"
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
          }}
          required
          disabled={loading || onCooldown}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="garmin-password">Mot de passe Garmin</Label>
        <Input
          id="garmin-password"
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
          }}
          required
          disabled={loading || onCooldown}
        />
      </div>
      <Button
        type="submit"
        disabled={loading || onCooldown || !email || !password}
        className="w-full"
      >
        {buttonLabel({ loading, onCooldown, remainingSec })}
      </Button>
    </form>
  )
}
