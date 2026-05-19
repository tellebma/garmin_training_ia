import { redirect } from 'next/navigation'
import { RegisterForm } from '@/components/auth/register-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function RegisterPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (user) redirect('/today')

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Créer un compte</h1>
          <p className="text-muted-foreground text-sm">
            Entre ton email — tu recevras un lien d&apos;activation
          </p>
        </header>
        <RegisterForm />
      </div>
      <Toaster />
    </main>
  )
}
