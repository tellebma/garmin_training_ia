import { AlertTriangle } from 'lucide-react'
import { createClient } from '@/lib/supabase/server'
import { isFlagActive, type FeatureFlagRow } from '@/lib/admin/types'
import { FeatureFlagsList } from './feature-flags-list'

export async function FeatureFlagsPanel() {
  const supabase = await createClient()
  const result = await supabase.rpc('admin_list_feature_flags')
  const flags = result.data as FeatureFlagRow[] | null
  if (result.error || !flags) {
    return <p className="text-destructive text-sm">Impossible de charger les feature flags.</p>
  }
  const risky = flags.filter(
    (f) =>
      isFlagActive(f) && (f.key === 'maintenance_mode' || f.key === 'public_registration_enabled')
  )

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Feature flags</h2>
      {risky.length > 0 && (
        <div className="rounded-md border border-amber-500/40 bg-amber-500/5 px-4 py-3 text-sm text-amber-800 dark:text-amber-200">
          {risky.map((f) => (
            <p key={f.key} className="flex items-start gap-2">
              <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
              <span>
                {f.description}
                {f.expires_at && ` — expire le ${new Date(f.expires_at).toLocaleString('fr-FR')}`}
              </span>
            </p>
          ))}
        </div>
      )}
      <FeatureFlagsList flags={flags} />
    </section>
  )
}
