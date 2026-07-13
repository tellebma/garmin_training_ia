import { createClient } from '@/lib/supabase/server'
import { toActivityColCrossings } from '@/lib/dashboard/cols'
import type { ActivityColCrossingRowDto } from '@/lib/dashboard/cols'
import { ChartCard } from './chart-card'

export async function ActivityColsGravis({
  userId,
  garminActivityId,
}: {
  readonly userId: string
  readonly garminActivityId: number
}) {
  const supabase = await createClient()
  const { data } = await supabase
    .from('col_crossings')
    .select('col_id, crossed_at, cols(name, elevation_m)')
    .eq('user_id', userId)
    .eq('garmin_activity_id', garminActivityId)
    .order('crossed_at', { ascending: true })

  const crossings = toActivityColCrossings((data ?? []) as unknown as ActivityColCrossingRowDto[])
  if (crossings.length === 0) return null

  return (
    <ChartCard title="Cols gravis" description="Cols franchis pendant cette activité">
      <ul className="divide-y">
        {crossings.map((c) => (
          <li key={c.colId} className="flex items-center justify-between py-2 text-sm">
            <span className="font-medium">{c.name}</span>
            <span className="text-muted-foreground">
              {c.elevationM === null ? '—' : `${String(c.elevationM)} m`}
            </span>
          </li>
        ))}
      </ul>
    </ChartCard>
  )
}
