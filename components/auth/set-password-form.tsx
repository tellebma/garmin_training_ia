'use client'

import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'

type SetPasswordAction = (input: {
  password: string
  confirm: string
}) => Promise<
  { success: true } | { success: false; errors?: Record<string, string[]>; error?: string }
>

interface Props {
  action: SetPasswordAction
  submitLabel: string
  submitLabelLoading: string
}

export function SetPasswordForm({ action, submitLabel, submitLabelLoading }: Readonly<Props>) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    try {
      const r = await action({ password, confirm })
      if (r.success) return // server redirected
      if ('errors' in r) {
        setErrors(r.errors)
      } else if (r.error === 'already_set') {
        toast.error(
          'Mot de passe déjà défini — utilise "Mot de passe oublié" pour le réinitialiser'
        )
      } else if (r.error === 'unauthenticated') {
        toast.error('Session expirée — reconnecte-toi')
      } else {
        toast.error('Erreur de sauvegarde')
      }
    } catch (err) {
      // Server Action `redirect()` throws NEXT_REDIRECT — that's success, do nothing.
      if (err instanceof Error && err.message.startsWith('NEXT_REDIRECT')) return
      toast.error('Erreur inattendue')
    } finally {
      setLoading(false)
    }
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="password">Nouveau mot de passe</Label>
        <Input
          id="password"
          type="password"
          autoComplete="new-password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value)
          }}
          required
          disabled={loading}
          minLength={10}
          maxLength={72}
        />
        <p className="text-muted-foreground text-xs">
          Au moins 10 caractères. Évite les mots de passe courants.
        </p>
        {errors.password?.[0] && <p className="text-destructive text-xs">{errors.password[0]}</p>}
      </div>
      <div className="space-y-2">
        <Label htmlFor="confirm">Confirme</Label>
        <Input
          id="confirm"
          type="password"
          autoComplete="new-password"
          value={confirm}
          onChange={(e) => {
            setConfirm(e.target.value)
          }}
          required
          disabled={loading}
        />
        {errors.confirm?.[0] && <p className="text-destructive text-xs">{errors.confirm[0]}</p>}
      </div>
      <Button type="submit" disabled={loading || !password || !confirm} className="w-full">
        {loading ? submitLabelLoading : submitLabel}
      </Button>
    </form>
  )
}
