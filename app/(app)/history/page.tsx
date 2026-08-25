// app/(app)/history/page.tsx
import Link from 'next/link'
import { Activity as ActivityIcon } from 'lucide-react'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { ActivityRow } from '../_components/activity-row'
import { EmptyState } from '../_components/empty-state'
import { countedActivities, excludedActivities } from '@/lib/activities/scope'
import type { ActivityRowDto } from '@/lib/dashboard/types'

export const revalidate = 300

const PAGE_SIZE = 20

interface HistoryPageProps {
  readonly searchParams: Promise<{
    readonly sport?: string
    readonly period?: string
    readonly offset?: string
    readonly view?: string
  }>
}

const SPORTS = [
  { value: 'all', label: 'Tous sports' },
  { value: 'swim', label: 'Natation' },
  { value: 'bike', label: 'Vélo' },
  { value: 'run', label: 'Course' },
]

const PERIODS = [
  { value: '7', label: '7 jours' },
  { value: '30', label: '30 jours' },
  { value: '90', label: '90 jours' },
  { value: 'all', label: 'Tout' },
]

export default async function HistoryPage({ searchParams }: HistoryPageProps) {
  const userId = await requireOnboarded()
  const {
    sport: sportParam,
    period: periodParam,
    offset: offsetParam,
    view: viewParam,
  } = await searchParams
  // Vue « supprimées » : le seul endroit qui montre les activités exclues, pour pouvoir
  // en restaurer une (E24.3).
  const deletedView = viewParam === 'deleted'
  const sport = SPORTS.find((s) => s.value === sportParam)?.value ?? 'all'
  const period = PERIODS.find((p) => p.value === periodParam)?.value ?? '30'
  const offset = Math.max(0, Number.parseInt(offsetParam ?? '0', 10) || 0)

  const supabase = await createClient()
  const scoped = deletedView ? excludedActivities : countedActivities
  let query = scoped(
    supabase
      .from('activities')
      .select(
        'id, garmin_activity_id, start_time, sport, duration_s, distance_m, elevation_gain_m, tss, hr_avg, route_polyline, race_goal_id'
      )
      .eq('user_id', userId)
  )

  if (sport !== 'all') {
    query = query.eq('sport', sport)
  }

  if (period !== 'all') {
    const days = Number.parseInt(period, 10)
    // Server component runs once per request — Date.now() is deterministic here.
    // eslint-disable-next-line react-hooks/purity
    const cutoff = new Date(Date.now() - days * 86_400_000).toISOString()
    query = query.gte('start_time', cutoff)
  }

  const { data } = await query
    .order('start_time', { ascending: false })
    .range(offset, offset + PAGE_SIZE - 1)

  const activities = (data ?? []) as ActivityRowDto[]
  const hasMore = activities.length === PAGE_SIZE

  function buildLink(updates: Record<string, string>): string {
    const params = new URLSearchParams()
    params.set('sport', sport)
    params.set('period', period)
    if (deletedView) params.set('view', 'deleted')
    if (offset > 0) params.set('offset', String(offset))
    for (const [k, v] of Object.entries(updates)) params.set(k, v)
    return `/history?${params.toString()}`
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Historique</h1>
      </header>

      <div className="flex flex-wrap gap-2">
        <div className="flex gap-1">
          {SPORTS.map((s) => (
            <Link
              key={s.value}
              href={buildLink({ sport: s.value, offset: '0' })}
              className={
                sport === s.value
                  ? 'bg-primary text-primary-foreground rounded-md border px-3 py-1.5 text-xs font-medium'
                  : 'text-muted-foreground hover:bg-accent/50 rounded-md border px-3 py-1.5 text-xs'
              }
            >
              {s.label}
            </Link>
          ))}
        </div>
        <div className="flex gap-1">
          {PERIODS.map((p) => (
            <Link
              key={p.value}
              href={buildLink({ period: p.value, offset: '0' })}
              className={
                period === p.value
                  ? 'bg-primary text-primary-foreground rounded-md border px-3 py-1.5 text-xs font-medium'
                  : 'text-muted-foreground hover:bg-accent/50 rounded-md border px-3 py-1.5 text-xs'
              }
            >
              {p.label}
            </Link>
          ))}
        </div>
        <Link
          href={
            deletedView
              ? `/history?sport=${sport}&period=${period}`
              : `/history?sport=${sport}&period=${period}&view=deleted`
          }
          className={
            deletedView
              ? 'bg-primary text-primary-foreground rounded-md border px-3 py-1.5 text-xs font-medium'
              : 'text-muted-foreground hover:bg-accent/50 rounded-md border px-3 py-1.5 text-xs'
          }
        >
          {deletedView ? 'Retour à l’historique' : 'Supprimées'}
        </Link>
      </div>

      {deletedView && (
        <p className="text-muted-foreground text-sm">
          Ces activités ne comptent plus dans tes statistiques. Ouvre-en une pour la restaurer.
        </p>
      )}

      {activities.length > 0 ? (
        <>
          <div className="rounded-lg border">
            {activities.map((a) => (
              <Link key={a.id} href={`/history/${a.id}`} className="block">
                <ActivityRow activity={a} className="px-3" />
              </Link>
            ))}
          </div>
          <div className="flex items-center justify-between">
            {offset > 0 ? (
              <Link
                href={buildLink({ offset: String(Math.max(0, offset - PAGE_SIZE)) })}
                className="text-muted-foreground text-xs underline"
              >
                Précédent
              </Link>
            ) : (
              <span />
            )}
            {hasMore ? (
              <Link
                href={buildLink({ offset: String(offset + PAGE_SIZE) })}
                className="bg-primary text-primary-foreground rounded-md px-3 py-1.5 text-xs"
              >
                Charger plus
              </Link>
            ) : (
              <span className="text-muted-foreground text-xs">Fin de l&rsquo;historique</span>
            )}
          </div>
        </>
      ) : (
        <EmptyState
          icon={ActivityIcon}
          title={deletedView ? 'Aucune activité supprimée' : 'Aucune activité'}
          description={
            deletedView
              ? 'Tout ton historique compte dans tes statistiques.'
              : 'Élargis le filtre ou attends le prochain sync (05:00 UTC).'
          }
        />
      )}
    </div>
  )
}
