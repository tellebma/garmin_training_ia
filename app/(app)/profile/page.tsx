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

interface GarminCredentialsRow {
  last_sync_at: string | null
  last_sync_status: string | null
  initial_sync_completed_at: string | null
  token_refresh_failed_at: string | null
  updated_at: string
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('fr-FR', { dateStyle: 'short', timeStyle: 'short' })
}

export default async function ProfilePage() {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  const [{ data: profile }, { data: garmin }] = await Promise.all([
    supabase
      .from('athlete_profiles')
      .select('first_name, city, onboarding_completed_at')
      .eq('user_id', user.id)
      .single<AthleteProfile>(),
    supabase
      .from('garmin_credentials')
      .select(
        'last_sync_at, last_sync_status, initial_sync_completed_at, token_refresh_failed_at, updated_at'
      )
      .eq('user_id', user.id)
      .maybeSingle<GarminCredentialsRow>(),
  ])

  const garminConnected = garmin !== null
  const garminAuthStale = garmin?.token_refresh_failed_at !== null && garmin !== null

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
        <div className="flex items-center justify-between gap-3">
          <h2 className="text-lg font-semibold">Garmin Connect</h2>
          {garminConnected && !garminAuthStale && (
            <span className="rounded-full bg-emerald-500/10 px-3 py-1 text-xs font-medium text-emerald-600 dark:text-emerald-400">
              ✓ Connecté
            </span>
          )}
          {garminAuthStale && (
            <span className="rounded-full bg-amber-500/10 px-3 py-1 text-xs font-medium text-amber-600 dark:text-amber-400">
              ⚠ Token expiré
            </span>
          )}
        </div>

        {!garminConnected && (
          <>
            <p className="text-muted-foreground text-sm">
              Connecte ton compte Garmin pour synchroniser tes activités et métriques.
            </p>
            <Button asChild variant="outline">
              <Link href="/profile/garmin">Connecter Garmin</Link>
            </Button>
          </>
        )}

        {garminConnected && (
          <>
            <dl className="text-muted-foreground grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
              <dt>Connecté le</dt>
              <dd className="text-foreground">{formatDateTime(garmin.updated_at)}</dd>
              <dt>Backfill 90 j</dt>
              <dd className="text-foreground">
                {garmin.initial_sync_completed_at
                  ? `terminé le ${formatDateTime(garmin.initial_sync_completed_at)}`
                  : 'en attente (cron 05:00 UTC)'}
              </dd>
              <dt>Dernier sync</dt>
              <dd className="text-foreground">{formatDateTime(garmin.last_sync_at)}</dd>
              <dt>Statut sync</dt>
              <dd className="text-foreground">{garmin.last_sync_status ?? '—'}</dd>
            </dl>
            <Button asChild variant="outline">
              <Link href="/profile/garmin">Reconnecter</Link>
            </Button>
          </>
        )}
      </section>
      <SignOutButton />
    </div>
  )
}
