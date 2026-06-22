import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

const KPI_KEYS = ['kpi-1', 'kpi-2', 'kpi-3', 'kpi-4']

export function CockpitSkeleton() {
  return (
    <LoadingRegion label="Chargement du cockpit">
      <div className="space-y-8">
        <Skeleton className="h-24 w-full rounded-md" />
        <div className="grid border-y sm:grid-cols-2 lg:grid-cols-4">
          {KPI_KEYS.map((key) => (
            <div key={key} className="space-y-3 p-4">
              <Skeleton className="h-4 w-20" />
              <Skeleton className="h-7 w-24" />
            </div>
          ))}
        </div>
        <div className="grid gap-6 lg:grid-cols-2">
          <Skeleton className="h-72 w-full rounded-md" />
          <Skeleton className="h-72 w-full rounded-md" />
        </div>
      </div>
    </LoadingRegion>
  )
}
