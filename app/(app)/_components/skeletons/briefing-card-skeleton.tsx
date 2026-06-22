import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

export function BriefingCardSkeleton() {
  return (
    <LoadingRegion label="Chargement du briefing du jour">
      <section className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <Skeleton className="h-4 w-32" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-20 w-full rounded-md" />
      </section>
    </LoadingRegion>
  )
}
