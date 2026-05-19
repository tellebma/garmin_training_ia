import { ForgotPasswordForm } from '@/components/auth/forgot-password-form'
import { Toaster } from '@/components/ui/sonner'

export default function ForgotPasswordPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center px-4">
      <div className="w-full max-w-sm space-y-8">
        <header className="space-y-2 text-center">
          <h1 className="text-2xl font-semibold">Mot de passe oublié</h1>
          <p className="text-muted-foreground text-sm">
            Entre ton email — on t&apos;envoie un lien pour le réinitialiser
          </p>
        </header>
        <ForgotPasswordForm />
      </div>
      <Toaster />
    </main>
  )
}
