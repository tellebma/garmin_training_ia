import { createClient } from '@/lib/supabase/server'

export default async function TodayPage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Aujourd&rsquo;hui</h1>
        <p className="text-muted-foreground text-sm">Connecté en tant que {user?.email}</p>
      </header>
      <section className="rounded-lg border p-6">
        <p className="text-muted-foreground">
          Ta séance du jour s&rsquo;affichera ici une fois ton profil complété et tes données Garmin
          synchronisées.
        </p>
      </section>
    </div>
  )
}
