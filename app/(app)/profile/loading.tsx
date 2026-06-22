import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../_components/skeletons/loading-region'

export default function ProfileLoading() {
  return (
    <LoadingRegion label="Chargement du profil">
      <div className="space-y-6">
        <Skeleton className="h-8 w-40" />
        {Array.from({ length: 5 }).map((_, i) => (
          <Skeleton key={i} className="h-40 w-full rounded-lg" />
        ))}
      </div>
    </LoadingRegion>
  )
}
