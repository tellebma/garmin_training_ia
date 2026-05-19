'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { login } from '@/app/(auth)/_actions/auth'

export function EmailPasswordForm() {
  const router = useRouter()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})

    const r = await login({ email, password })

    if (r.success) {
      router.push('/today')
      router.refresh()
      return
    }

    if ('errors' in r) {
      setErrors(r.errors)
      setLoading(false)
      return
    }

    setLoading(false)

    const errorCode = 'error' in r ? r.error : undefined
    if (errorCode === 'rate_limited') {
      toast.error('Trop de tentatives, réessaie dans 15 minutes')
      return
    }
    if (errorCode === 'ip_unresolved') {
      toast.error("Impossible de résoudre ton IP — contacte l'admin")
      return
    }
    // 'invalid_credentials' OU unknown → message générique anti-leak
    toast.error('Email ou mot de passe incorrect')
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
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <Label htmlFor="password">Mot de passe</Label>
          <Link href="/forgot-password" className="text-muted-foreground text-xs hover:underline">
            Mot de passe oublié ?
          </Link>
        </div>
        <Input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
          }}
          required
          disabled={loading}
        />
        {errors.password?.[0] && <p className="text-destructive text-xs">{errors.password[0]}</p>}
      </div>
      <Button type="submit" disabled={loading || !email || !password} className="w-full">
        {loading ? 'Connexion...' : 'Se connecter'}
      </Button>
      <p className="text-muted-foreground text-center text-xs">
        Pas encore de compte ?{' '}
        <Link href="/register" className="underline">
          Créer un compte
        </Link>
      </p>
    </form>
  )
}
