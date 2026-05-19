import { redirect } from 'next/navigation'
import { setPasswordAfterReset } from '@/app/(auth)/_actions/auth'
import { SetPasswordForm } from '@/components/auth/set-password-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function ResetPasswordPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) {
    // Lien expiré ou utilisé → retour forgot
    redirect('/forgot-password?expired=1')
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Réinitialise ton mot de passe</h1>
          <p className="text-muted-foreground text-sm">Choisis ton nouveau mot de passe.</p>
        </header>
        <SetPasswordForm
          action={setPasswordAfterReset}
          submitLabel="Réinitialiser"
          submitLabelLoading="Enregistrement..."
        />
      </div>
      <Toaster />
    </main>
  )
}
