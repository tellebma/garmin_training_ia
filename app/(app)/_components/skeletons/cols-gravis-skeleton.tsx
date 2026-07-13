import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

export function ColsGravisSkeleton() {
  return (
    <LoadingRegion label="Chargement des cols gravis">
      <div className="space-y-2">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-10 w-full rounded-md" />
        <Skeleton className="h-10 w-full rounded-md" />
      </div>
    </LoadingRegion>
  )
}
