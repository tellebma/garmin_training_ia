// app/(app)/plan/page.tsx
import Link from 'next/link'
import { CalendarOff, ChevronLeft, ChevronRight } from 'lucide-react'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { createClient } from '@/lib/supabase/server'
import { EmptyState } from '../_components/empty-state'
import { PhaseBadge } from '../_components/phase-badge'
import { SessionCard } from '../_components/session-card'
import { formatDuration, formatTSS, formatWeekday } from '@/lib/dashboard/format'
import type { PlannedSession } from '@/lib/dashboard/types'

export const revalidate = 0

function weekRange(weekOffset: number): { start: string; end: string } {
  const now = new Date()
  const monday = new Date(now)
  const day = (now.getDay() + 6) % 7
  monday.setDate(now.getDate() - day + weekOffset * 7)
  monday.setHours(0, 0, 0, 0)
  const sunday = new Date(monday)
  sunday.setDate(monday.getDate() + 6)
  return { start: monday.toISOString().slice(0, 10), end: sunday.toISOString().slice(0, 10) }
}

interface PlanPageProps {
  searchParams: Promise<{ week?: string }>
}

export default async function PlanPage({ searchParams }: Readonly<PlanPageProps>) {
  const userId = await requireOnboarded()
  const { week } = await searchParams
  const weekOffset = Number.parseInt(week ?? '0', 10) || 0
  const { start, end } = weekRange(weekOffset)

  const supabase = await createClient()
  const [planRes, sessionsRes] = await Promise.all([
    supabase
      .from('training_plans')
      .select('id, race_goal_id, start_date, end_date, weeks_count')
      .eq('user_id', userId)
      .eq('status', 'active')
      .maybeSingle(),
    supabase
      .from('planned_sessions')
      .select(
        'id, date, sport, session_type, target_duration_s, target_tss, target_elevation_gain_m, phase, week_offset, notes, workout, workout_generated_at'
      )
      .eq('user_id', userId)
      .gte('date', start)
      .lte('date', end)
      .order('date', { ascending: true }),
  ])

  const plan = planRes.data
  const sessions = (sessionsRes.data ?? []) as PlannedSession[]
  const sessionsByDate = new Map(sessions.map((s) => [s.date, s]))

  if (!plan) {
    return (
      <div className="space-y-6">
        <header>
          <h1 className="text-2xl font-semibold">Plan</h1>
        </header>
        <EmptyState
          icon={CalendarOff}
          title="Pas de plan actif"
          description="Le plan sera généré après le prochain dimanche 22h UTC."
        />
      </div>
    )
  }

  const days: string[] = []
  for (let i = 0; i < 7; i++) {
    const d = new Date(start)
    d.setDate(d.getDate() + i)
    days.push(d.toISOString().slice(0, 10))
  }

  const totalDuration = sessions.reduce((acc, s) => acc + (s.target_duration_s ?? 0), 0)
  const totalTss = sessions.reduce((acc, s) => acc + (s.target_tss ?? 0), 0)
  const firstPhase = sessions[0]?.phase

  return (
    <div className="space-y-6">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Plan</h1>
          <p className="text-muted-foreground text-sm">
            Semaine du {start} au {end}
          </p>
        </div>
        {firstPhase && <PhaseBadge phase={firstPhase} />}
      </header>

      <nav className="flex items-center justify-between">
        <Link
          href={`/plan?week=${String(weekOffset - 1)}`}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          <ChevronLeft size={16} /> Précédente
        </Link>
        {weekOffset !== 0 && (
          <Link href="/plan" className="text-muted-foreground text-xs underline">
            Cette semaine
          </Link>
        )}
        <Link
          href={`/plan?week=${String(weekOffset + 1)}`}
          className="text-muted-foreground hover:text-foreground inline-flex items-center gap-1 text-sm"
        >
          Suivante <ChevronRight size={16} />
        </Link>
      </nav>

      <ul className="space-y-2">
        {days.map((d) => {
          const s = sessionsByDate.get(d)
          return (
            <li key={d} className="flex items-center gap-3">
              <span className="text-muted-foreground w-10 shrink-0 text-xs uppercase">
                {formatWeekday(d)}
              </span>
              <div className="flex-1">
                {s ? (
                  <SessionCard session={s} compact showWorkout />
                ) : (
                  <div className="text-muted-foreground bg-muted/30 rounded-lg border border-dashed py-3 text-center text-xs">
                    Aucune séance
                  </div>
                )}
              </div>
            </li>
          )
        })}
      </ul>

      <footer className="text-muted-foreground border-t pt-3 text-xs">
        Total semaine : {formatDuration(totalDuration)} · {formatTSS(totalTss)}
      </footer>
    </div>
  )
}
