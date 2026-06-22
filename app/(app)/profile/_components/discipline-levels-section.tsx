import { Minus, TrendingDown, TrendingUp } from 'lucide-react'

interface DisciplineLevel {
  declared: number
  effective: number
  adjustment: number
  confidence: string
  reason: string
  signals: Record<string, number | boolean>
}

const LABELS: Record<string, string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
}

function AdjustmentIcon({ adjustment }: Readonly<{ adjustment: number }>) {
  if (adjustment > 0) return <TrendingUp className="h-4 w-4 text-emerald-500" />
  if (adjustment < 0) return <TrendingDown className="h-4 w-4 text-amber-500" />
  return <Minus className="text-muted-foreground h-4 w-4" />
}

export function DisciplineLevelsSection({
  disciplines,
}: Readonly<{
  disciplines: Record<string, DisciplineLevel>
}>) {
  const entries = Object.entries(disciplines)
  if (entries.length === 0) return null

  return (
    <section className="space-y-3 rounded-lg border p-6">
      <h2 className="text-lg font-semibold">Niveau par discipline</h2>
      <p className="text-muted-foreground text-sm">
        Niveau retenu, croisé avec tes 90 derniers jours d&apos;entraînement.
      </p>
      <ul className="space-y-2">
        {entries.map(([key, d]) => (
          <li key={key} className="flex items-start justify-between gap-3 border-t pt-2">
            <div>
              <div className="flex items-center gap-2 font-medium">
                {LABELS[key] ?? key}
                <AdjustmentIcon adjustment={d.adjustment} />
                <span className="tabular-nums">{d.effective}</span>
                {d.adjustment !== 0 && (
                  <span className="text-muted-foreground text-xs">(déclaré {d.declared})</span>
                )}
              </div>
              <p className="text-muted-foreground text-sm">{d.reason}</p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  )
}
