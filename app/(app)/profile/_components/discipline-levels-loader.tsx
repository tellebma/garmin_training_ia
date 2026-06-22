import { createClient } from '@/lib/supabase/server'
import { workerPost } from '@/lib/worker'
import { DisciplineLevelsSection } from './discipline-levels-section'

export async function DisciplineLevelsLoader() {
  let disciplineLevels: Record<string, unknown> = {}
  try {
    const supabase = await createClient()
    const {
      data: { session },
    } = await supabase.auth.getSession()
    if (session?.access_token) {
      const res = await workerPost<{ disciplines?: Record<string, unknown> }>(
        '/coach/discipline-levels',
        {},
        session.access_token,
        15_000
      )
      disciplineLevels = res.disciplines ?? {}
    }
  } catch {
    disciplineLevels = {}
  }
  return <DisciplineLevelsSection disciplines={disciplineLevels as never} />
}
