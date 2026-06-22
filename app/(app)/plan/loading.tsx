import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function PlanLoading() {
  return (
    <LoadingRegion label="Chargement du plan">
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-10 w-full" />
        <div className="space-y-2">
          {Array.from({ length: 7 }).map((_, i) => (
            <Skeleton key={i} className="h-16 w-full rounded-lg" />
          ))}
        </div>
      </div>
    </LoadingRegion>
  )
}
