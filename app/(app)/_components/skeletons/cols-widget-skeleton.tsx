import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from './loading-region'

const ROW_KEYS = ['row-1', 'row-2', 'row-3', 'row-4']

export function ColsWidgetSkeleton() {
  return (
    <LoadingRegion label="Chargement des cols">
      <section className="space-y-3 rounded-lg border p-4">
        <Skeleton className="h-4 w-32" />
        <div className="divide-y">
          {ROW_KEYS.map((key) => (
            <div key={key} className="flex items-center justify-between py-2">
              <Skeleton className="h-4 w-40" />
              <Skeleton className="h-4 w-16" />
            </div>
          ))}
        </div>
      </section>
    </LoadingRegion>
  )
}
