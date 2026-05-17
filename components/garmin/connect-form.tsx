'use client'

import { useState } from 'react'
import { connectGarmin } from '@/app/actions/garmin-auth'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { toast } from 'sonner'

interface Props {
  onMfaRequired: (challengeId: string) => void
  onConnected: () => void
}

export function ConnectForm({ onMfaRequired, onConnected }: Readonly<Props>) {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
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
        case 'invalid_credentials':
          toast.error('Identifiants Garmin invalides')
          break
        case 'rate_limited':
          toast.error('Trop de tentatives Garmin — réessaye dans quelques minutes')
          break
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
          disabled={loading}
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
          disabled={loading}
        />
      </div>
      <Button type="submit" disabled={loading || !email || !password} className="w-full">
        {loading ? 'Connexion...' : 'Connecter Garmin'}
      </Button>
    </form>
  )
}
