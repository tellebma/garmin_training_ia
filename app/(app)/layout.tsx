import { redirect } from 'next/navigation'
import { BottomNav } from '@/components/nav/bottom-nav'
import { SideNav } from '@/components/nav/side-nav'
import { createClient } from '@/lib/supabase/server'
import { SyncNowButton } from '@/app/(app)/_components/sync-now-button'

export default async function AppLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  const supabase = await createClient()
  const {
    data: { user },
  } = await supabase.auth.getUser()

  if (!user) {
    redirect('/login')
  }

  return (
    <div className="flex min-h-screen">
      <SideNav />
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
