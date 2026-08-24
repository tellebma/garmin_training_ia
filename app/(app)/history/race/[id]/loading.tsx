import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../../../_components/skeletons/loading-region'

export default function RaceDetailLoading() {
  return (
    <LoadingRegion label="Chargement de la course">
      <div className="space-y-6">
        <Skeleton className="h-8 w-56" />
        <Skeleton className="h-24 w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-72 w-full rounded-lg" />
      </div>
    </LoadingRegion>
  )
}
