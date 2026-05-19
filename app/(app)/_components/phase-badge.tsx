// app/(app)/_components/phase-badge.tsx
import { cn } from '@/lib/utils'
import { PHASE_LABEL } from './sport-icon'
import type { Phase } from '@/lib/dashboard/types'

const PHASE_CLASS: Record<Phase, string> = {
  base: 'bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30',
  build: 'bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30',
  peak: 'bg-red-500/10 text-red-600 dark:text-red-400 border-red-500/30',
  taper: 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
  race: 'bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-500/30',
}

export function PhaseBadge({ phase, className }: Readonly<{ phase: Phase; className?: string }>) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full border px-2 py-0.5 text-xs font-medium',
        PHASE_CLASS[phase],
        className
      )}
    >
      {PHASE_LABEL[phase]}
    </span>
  )
}
