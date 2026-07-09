import { Suspense } from 'react'
import { requireAdmin } from '@/lib/admin/guard'
import { FinopsPanel } from './_components/finops-panel'
import { FeatureFlagsPanel } from './_components/feature-flags-panel'
import { AllowlistPanel } from './_components/allowlist-panel'
import { FinopsPanelSkeleton } from './_components/skeletons/finops-panel-skeleton'
import { FeatureFlagsPanelSkeleton } from './_components/skeletons/feature-flags-panel-skeleton'
import { AllowlistPanelSkeleton } from './_components/skeletons/allowlist-panel-skeleton'

export const revalidate = 0

export default async function AdminPage() {
  await requireAdmin()

  return (
    <div className="space-y-8">
      <header>
        <p className="text-muted-foreground text-sm">Réservé à l&rsquo;owner</p>
        <h1 className="text-2xl font-semibold">Console admin</h1>
      </header>

      <Suspense fallback={<FinopsPanelSkeleton />}>
        <FinopsPanel />
      </Suspense>

      <Suspense fallback={<FeatureFlagsPanelSkeleton />}>
        <FeatureFlagsPanel />
      </Suspense>

      <Suspense fallback={<AllowlistPanelSkeleton />}>
        <AllowlistPanel />
      </Suspense>
    </div>
  )
}
