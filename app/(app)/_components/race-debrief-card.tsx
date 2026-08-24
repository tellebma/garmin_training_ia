import { ThumbsUp, Target } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { RaceDebrief } from '@/lib/coach/race-analysis'

/** Le retour sur la course : ce qui a marché, ce qui est à corriger. */
export function RaceDebriefCard({ debrief }: { readonly debrief: RaceDebrief }) {
  return (
    <section
      className={cn(
        'rounded-lg border p-4',
        debrief.tone === 'watch'
          ? 'border-amber-500/30 bg-amber-500/5'
          : 'border-emerald-500/30 bg-emerald-500/5'
      )}
    >
      <p className="text-sm font-semibold">{debrief.verdict}</p>
      <div className="mt-4 grid gap-4 md:grid-cols-2">
        <div>
          <h2 className="flex items-center gap-2 text-xs font-semibold tracking-wide uppercase">
            <ThumbsUp size={14} /> Ce qui a marché
          </h2>
          <ul className="text-muted-foreground mt-2 space-y-2 text-sm">
            {debrief.strengths.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="flex items-center gap-2 text-xs font-semibold tracking-wide uppercase">
            <Target size={14} /> Points d’amélioration
          </h2>
          <ul className="text-muted-foreground mt-2 space-y-2 text-sm">
            {debrief.improvements.map((item) => (
              <li key={item}>{item}</li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  )
}
