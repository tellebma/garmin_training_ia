import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function HistoryLoading() {
  return (
    <LoadingRegion label="Chargement de l'historique">
      <div className="space-y-6">
        <Skeleton className="h-8 w-32" />
        <div className="flex gap-2">
          <Skeleton className="h-9 w-32" />
          <Skeleton className="h-9 w-32" />
        </div>
        <div className="space-y-2">
          {Array.from({ length: 10 }).map((_, i) => (
            <Skeleton key={i} className="h-14 w-full rounded" />
          ))}
        </div>
      </div>
    </LoadingRegion>
  )
}
