import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../../_components/skeletons/loading-region'

export default function GarminLoading() {
  return (
    <LoadingRegion label="Chargement de la connexion Garmin">
      <div className="space-y-6">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-40 w-full rounded-lg" />
        <Skeleton className="h-10 w-40 rounded-md" />
      </div>
    </LoadingRegion>
  )
}
