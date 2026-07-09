import { redirect } from 'next/navigation'
import { BottomNav } from '@/components/nav/bottom-nav'
import { SideNav } from '@/components/nav/side-nav'
import { createClient } from '@/lib/supabase/server'
import { SyncNowButton } from '@/app/(app)/_components/sync-now-button'
import { MaintenancePage } from '@/app/(app)/_components/maintenance-page'

export default async function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  const [adminResult, maintenanceResult] = await Promise.all([
    supabase.rpc('is_admin_caller'),
    supabase.rpc('is_feature_flag_active', { p_key: 'maintenance_mode' }),
  ])
  const isAdmin = adminResult.data as boolean | null
  const maintenanceActive = maintenanceResult.data as boolean | null

  if (maintenanceActive && !isAdmin) {
    return <MaintenancePage />
  }

  return (
    <div className="flex min-h-screen">
      <SideNav isAdmin={Boolean(isAdmin)} />
      <main className="flex-1 pb-20 md:pb-0 md:pl-64">
        <div className="container mx-auto max-w-6xl px-4 py-6">
          <div className="mb-4 flex justify-end">
            <SyncNowButton />
          </div>
          {children}
        </div>
      </main>
      <BottomNav />
    </div>
  )
}
