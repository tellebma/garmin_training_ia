import { redirect } from 'next/navigation'
import { setInitialPassword } from '@/app/(auth)/_actions/auth'
import { SetPasswordForm } from '@/components/auth/set-password-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function SetPasswordPage() {
  // Session guard — must be logged in (just clicked the magic-link)
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (!user) redirect('/login')

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Crée ton mot de passe</h1>
          <p className="text-muted-foreground text-sm">
            Choisis un mot de passe que tu utiliseras pour te connecter la prochaine fois.
          </p>
        </header>
        <SetPasswordForm
          action={setInitialPassword}
          submitLabel="Enregistrer et continuer"
          submitLabelLoading="Enregistrement..."
        />
      </div>
      <Toaster />
    </main>
  )
}
