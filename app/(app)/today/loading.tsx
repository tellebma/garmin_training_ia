import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function TodayLoading() {
  return (
    <LoadingRegion label="Chargement de la page du jour">
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-36 w-full rounded-lg" />
        <div className="grid grid-cols-3 gap-2">
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
          <Skeleton className="h-24 rounded-lg" />
        </div>
        <Skeleton className="h-64 w-full rounded-lg" />
      </div>
    </LoadingRegion>
  )
}
