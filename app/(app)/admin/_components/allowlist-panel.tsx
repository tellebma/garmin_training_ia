import { createClient } from '@/lib/supabase/server'
import type { AllowedEmailRow } from '@/lib/admin/types'
import { AllowlistTable } from './allowlist-table'

export async function AllowlistPanel() {
  const supabase = await createClient()
  const result = await supabase.rpc('admin_list_allowed_emails')
  const rows = result.data as AllowedEmailRow[] | null
  if (result.error || !rows) {
    return <p className="text-destructive text-sm">Impossible de charger l&rsquo;allowlist.</p>
  }
  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Allowlist</h2>
      <AllowlistTable rows={rows} />
    </section>
  )
}
