import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

export function AllowlistPanelSkeleton() {
  return (
    <LoadingRegion label="Chargement de l'allowlist">
      <div className="space-y-2">
        <Skeleton className="h-9 w-full max-w-md rounded-md" />
        <Skeleton className="h-48 w-full rounded-md" />
      </div>
    </LoadingRegion>
  )
}
