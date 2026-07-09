import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '@/app/(app)/_components/skeletons/loading-region'

export function FinopsPanelSkeleton() {
  return (
    <LoadingRegion label="Chargement des indicateurs finops">
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {['users', 'activities', 'cost-est', 'cost-billed', 'sync-health'].map((key) => (
            <div key={key} className="space-y-2 rounded-lg border p-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-7 w-16" />
            </div>
          ))}
        </div>
        <Skeleton className="h-52 w-full rounded-md" />
      </div>
    </LoadingRegion>
  )
}
