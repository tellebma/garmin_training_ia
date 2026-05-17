import { redirect } from 'next/navigation'
import { MagicLinkForm } from '@/components/auth/magic-link-form'
import { Toaster } from '@/components/ui/sonner'
import { createClient } from '@/lib/supabase/server'

export default async function LoginPage() {
  // Already-authenticated users skip the login form. The middleware used to
  // do this but we removed it (the Edge runtime can't run @supabase/ssr).
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()
  if (user) {
    redirect('/today')
  }

  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Garmin Training Coach</h1>
          <p className="text-muted-foreground text-sm">Connecte-toi pour accéder à ton plan</p>
        </header>
        <MagicLinkForm />
      </div>
      <Toaster />
    </main>
  )
}
