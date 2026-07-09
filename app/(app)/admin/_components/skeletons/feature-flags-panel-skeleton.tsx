import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

export function FeatureFlagsPanelSkeleton() {
  return (
    <LoadingRegion label="Chargement des feature flags">
      <div className="space-y-2">
        {['flag-1', 'flag-2', 'flag-3'].map((key) => (
          <Skeleton key={key} className="h-14 w-full rounded-md" />
        ))}
      </div>
    </LoadingRegion>
  )
}
