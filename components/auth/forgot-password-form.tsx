'use client'

import Link from 'next/link'
import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { requestPasswordReset } from '@/app/(auth)/_actions/auth'

export function ForgotPasswordForm() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)

    await requestPasswordReset({ email })

    // Always show generic success (no email enum leak)
    setLoading(false)
    setSent(true)
  }

  if (sent) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-sm">
          Si <strong>{email}</strong> correspond à un compte, un email avec un lien de
          réinitialisation vient d&apos;être envoyé.
        </p>
        <p className="text-muted-foreground text-xs">Pense à vérifier ton dossier spam.</p>
        <Link href="/login" className="text-xs underline">
          ← Retour à la connexion
        </Link>
      </div>
    )
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          autoComplete="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
          }}
          required
          disabled={loading}
        />
      </div>
      <Button type="submit" disabled={loading || !email} className="w-full">
        {loading ? 'Envoi...' : 'Envoyer le lien'}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        <Link href="/login" className="underline">
          ← Retour à la connexion
        </Link>
      </p>
    </form>
  )
}
