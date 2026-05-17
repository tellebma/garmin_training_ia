import Link from 'next/link'
import { redirect } from 'next/navigation'
import { SignOutButton } from '@/components/auth/sign-out-button'
import { Button } from '@/components/ui/button'
import { createClient } from '@/lib/supabase/server'

interface AthleteProfile {
  first_name: string | null
  city: string | null
  onboarding_completed_at: string | null
}

export default async function ProfilePage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  // Supabase generated types come in E2 — cast the row shape manually for now.
  const { data: profile } = await supabase
    .from('athlete_profiles')
    .select('first_name, city, onboarding_completed_at')
    .eq('user_id', user.id)
    .single<AthleteProfile>()

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Profil</h1>
        <p className="text-muted-foreground text-sm">{user.email}</p>
      </header>
      <section className="space-y-2 rounded-lg border p-6 text-sm">
        <div>
          <strong>Prénom :</strong>{' '}
          {profile?.first_name ?? <em className="text-muted-foreground">non renseigné</em>}
        </div>
        <div>
          <strong>Ville :</strong>{' '}
          {profile?.city ?? <em className="text-muted-foreground">non renseigné</em>}
        </div>
        <div>
          <strong>Onboarding complété :</strong>{' '}
          {profile?.onboarding_completed_at ? 'oui' : 'non — sera fait en E3'}
        </div>
      </section>
      <section className="space-y-3 rounded-lg border p-6">
        <h2 className="text-lg font-semibold">Garmin Connect</h2>
        <p className="text-muted-foreground text-sm">
          Connecte ton compte Garmin pour synchroniser tes activités et métriques.
        </p>
        <Button asChild variant="outline">
          <Link href="/profile/garmin">Connecter Garmin</Link>
        </Button>
      </section>
      <SignOutButton />
    </div>
  )
}
