'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { createClient } from '@/lib/supabase/client'

export function MagicLinkForm() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)

    const supabase = createClient()
    const { error } = await supabase.auth.signInWithOtp({
      email,
      options: {
        emailRedirectTo: `${window.location.origin}/auth/callback`,
      },
    })

    setLoading(false)

    if (error) {
      toast.error(`Erreur: ${error.message}`)
      return
    }

    setSent(true)
  }

  if (sent) {
    return (
      <div className="space-y-2 text-center">
        <h2 className="text-xl font-semibold">Vérifie tes emails</h2>
        <p className="text-muted-foreground text-sm">
          Un lien de connexion a été envoyé à <strong>{email}</strong>.
        </p>
      </div>
    )
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="w-full max-w-sm space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="email">Email</Label>
        <Input
          id="email"
          type="email"
          placeholder="toi@exemple.com"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
          }}
          required
          disabled={loading}
        />
      </div>
      <Button type="submit" disabled={loading || !email} className="w-full">
        {loading ? 'Envoi...' : 'Recevoir le lien de connexion'}
      </Button>
    </form>
  )
}
