import { redirect } from 'next/navigation'
import { BottomNav } from '@/components/nav/bottom-nav'
import { SideNav } from '@/components/nav/side-nav'
import { ChangelogBell } from '@/components/nav/changelog-bell'
import { createClient } from '@/lib/supabase/server'
import { getCurrentUser } from '@/lib/supabase/current-user'
import { loadChangelog } from '@/lib/changelog/read'
import { SyncNowButton } from '@/app/(app)/_components/sync-now-button'
import { MaintenancePage } from '@/app/(app)/_components/maintenance-page'

export default async function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const user = await getCurrentUser()

  if (!user) {
    redirect('/login')
  }

  const supabase = await createClient()
  const [adminResult, maintenanceResult, changelogEntries, profileResult] = await Promise.all([
    supabase.rpc('is_admin_caller'),
    supabase.rpc('is_feature_flag_active', { p_key: 'maintenance_mode' }),
    loadChangelog(),
    supabase
      .from('athlete_profiles')
      .select('last_seen_changelog_version')
      .eq('user_id', user.id)
      .maybeSingle(),
  ])
  const isAdmin = adminResult.data as boolean | null
  const maintenanceActive = maintenanceResult.data as boolean | null
  const latestVersion = changelogEntries[0]?.version ?? null
  const lastSeenVersion = (profileResult.data?.last_seen_changelog_version ?? null) as string | null

  if (maintenanceActive && !isAdmin) {
    return <MaintenancePage />
  }

  return (
    <div className="flex min-h-screen">
      <SideNav isAdmin={Boolean(isAdmin)} />
      <main className="flex-1 pb-20 md:pb-0 md:pl-64">
        <div className="container mx-auto max-w-6xl px-4 py-6">
          <div className="mb-4 flex items-center justify-between">
            <ChangelogBell
              entries={changelogEntries}
              latestVersion={latestVersion}
              initialLastSeenVersion={lastSeenVersion}
            />
            <SyncNowButton />
          </div>
          {children}
        </div>
      </main>
      <BottomNav />
    </div>
  )
}
