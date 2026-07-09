import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { createClient } from '@/lib/supabase/server'
import { CostPerDayChart } from './charts/cost-per-day-chart'
import type { AdminOverview } from '@/lib/admin/types'

function formatUsd(value: number): string {
  return `$${value.toFixed(2)}`
}

export async function FinopsPanel() {
  const supabase = await createClient()
  const result = await supabase.rpc('admin_overview')
  const overview = result.data as AdminOverview | null
  if (result.error || !overview) {
    return <p className="text-destructive text-sm">Impossible de charger les indicateurs finops.</p>
  }

  return (
    <section className="space-y-4">
      <h2 className="text-lg font-semibold">Finops</h2>
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Utilisateurs</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{overview.users.total}</p>
            <p className="text-muted-foreground text-xs">
              {overview.users.active_7d} actifs sur 7j
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Activités</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{overview.activities.total}</p>
            <p className="text-muted-foreground text-xs">{overview.activities.last_7d} sur 7j</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Coût IA estimé (7j)</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {formatUsd(overview.llm_estimated.cost_usd_7d)}
            </p>
            <p className="text-muted-foreground text-xs">
              {overview.llm_estimated.total_tokens_7d.toLocaleString('fr-FR')} tokens
            </p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Coût IA facturé (7j)</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">{formatUsd(overview.llm_billed.cost_usd_7d)}</p>
            <p className="text-muted-foreground text-xs">Source OpenAI, délai ~24-48h</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle className="text-sm font-medium">Santé sync Garmin</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-2xl font-semibold">
              {overview.sync_health.ok} / {overview.sync_health.ok + overview.sync_health.failed}
            </p>
            <p className="text-muted-foreground text-xs">
              {overview.sync_health.failed > 0
                ? `${overview.sync_health.failed.toString()} en échec`
                : 'Toutes les syncs OK'}
            </p>
          </CardContent>
        </Card>
      </div>
      <Card>
        <CardHeader>
          <CardTitle className="text-sm font-medium">Coût estimé / jour (7j)</CardTitle>
        </CardHeader>
        <CardContent>
          <CostPerDayChart data={overview.cost_per_day_7d} />
        </CardContent>
      </Card>
    </section>
  )
}
