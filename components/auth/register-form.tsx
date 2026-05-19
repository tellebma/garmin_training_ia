'use client'

import Link from 'next/link'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { registerWithMagicLink } from '@/app/(auth)/_actions/auth'

export function RegisterForm() {
  const [email, setEmail] = useState('')
  const [loading, setLoading] = useState(false)
  const [sent, setSent] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})

    const r = await registerWithMagicLink({ email })

    setLoading(false)

    if (r.success) {
      setSent(true)
      toast.success("Si cet email est autorisé, un lien vient d'être envoyé. Vérifie ta boîte.")
      return
    }

    if ('errors' in r) {
      setErrors(r.errors)
      return
    }

    const errorCode = 'error' in r ? r.error : undefined
    if (errorCode === 'rate_limited') {
      toast.error('Trop de tentatives depuis ton IP, réessaie dans 1 heure')
      return
    }
    if (errorCode === 'ip_unresolved') {
      toast.error("Impossible de résoudre ton IP — contacte l'admin")
      return
    }
    if (errorCode === 'email_not_allowed') {
      // Anti-leak : message identique succès-générique (mais on le différencie un peu pour UX honnête)
      toast.error(
        "Cet email n'est pas autorisé à s'inscrire. Contacte l'admin pour demander un accès."
      )
      return
    }
    toast.error('Erreur inattendue, réessaie')
  }

  if (sent) {
    return (
      <div className="space-y-4 text-center">
        <p className="text-sm">
          Si <strong>{email}</strong> est dans la liste d&apos;attente, un email vient
          d&apos;arriver avec un lien à cliquer pour activer ton compte.
        </p>
        <p className="text-muted-foreground text-xs">
          Pense à vérifier ton dossier spam. Le lien expire dans 1 heure.
        </p>
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
        {errors.email?.[0] && <p className="text-destructive text-xs">{errors.email[0]}</p>}
      </div>
      <Button type="submit" disabled={loading || !email} className="w-full">
        {loading ? 'Envoi du lien...' : 'Créer mon compte'}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        Déjà un compte ?{' '}
        <Link href="/login" className="underline">
          Se connecter
        </Link>
      </p>
    </form>
  )
}
