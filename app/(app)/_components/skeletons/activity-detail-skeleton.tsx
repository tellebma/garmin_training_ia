import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

const TILE_KEYS = ['tile-1', 'tile-2', 'tile-3', 'tile-4']

export function ActivityDetailSkeleton() {
  return (
    <LoadingRegion label="Chargement de l'analyse d'activité">
      <div className="space-y-6">
        <Skeleton className="h-24 w-full rounded-lg" />
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {TILE_KEYS.map((key) => (
            <Skeleton key={key} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-72 w-full rounded-lg" />
        <Skeleton className="h-72 w-full rounded-lg" />
      </div>
    </LoadingRegion>
  )
}
