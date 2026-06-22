import { Skeleton } from '@/components/ui/skeleton'
import { LoadingRegion } from '../../_components/skeletons/loading-region'

const ROW_KEYS = ['disc-1', 'disc-2', 'disc-3']

export function DisciplineLevelsSkeleton() {
  return (
    <LoadingRegion label="Chargement du niveau par discipline">
      <section className="space-y-3 rounded-lg border p-6">
        <Skeleton className="h-5 w-48" />
        <Skeleton className="h-4 w-72" />
        <ul className="space-y-2">
          {ROW_KEYS.map((key) => (
            <li key={key} className="flex items-start justify-between gap-3 border-t pt-2">
              <div className="flex-1 space-y-2">
                <Skeleton className="h-4 w-40" />
                <Skeleton className="h-3 w-full max-w-md" />
              </div>
            </li>
          ))}
        </ul>
      </section>
    </LoadingRegion>
  )
}
