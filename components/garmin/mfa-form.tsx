'use client'

import { useState } from 'react'
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

export function MfaForm({ challengeId, onConnected, onCancel }: Readonly<Props>) {
  const [code, setCode] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    try {
      const result = await submitGarminMfa(challengeId, code)
      switch (result.status) {
        case 'connected':
          toast.success('Compte Garmin connecté !')
          onConnected()
          break
        case 'invalid_code':
          toast.error('Code MFA invalide')
          break
        case 'challenge_expired':
          toast.error('Challenge expiré, réessaye depuis le début')
          onCancel()
          break
        case 'challenge_user_mismatch':
          toast.error('Challenge invalide pour cet utilisateur')
          onCancel()
          break
        case 'rate_limited':
          toast.error('Trop de tentatives Garmin — réessaye dans quelques minutes')
          break
        case 'garmin_error':
          toast.error(`Garmin: ${result.detail}`)
          break
        case 'unexpected_error':
          console.error('Garmin MFA unexpected error:', result)
          toast.error(`Erreur: ${result.type} — ${result.detail}`)
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
          disabled={loading}
        />
      </div>
      <div className="flex gap-2">
        <Button type="submit" disabled={loading || code.length < 4} className="flex-1">
          {loading ? 'Vérification...' : 'Valider'}
        </Button>
        <Button type="button" variant="outline" onClick={onCancel} disabled={loading}>
          Annuler
        </Button>
      </div>
    </form>
  )
}
