// app/(app)/_components/metric-tile.tsx
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

interface MetricTileProps {
  icon: LucideIcon
  label: string
  value: string
  delta?: { value: string; positive?: boolean } | null
  className?: string
}

export function MetricTile({
  icon: Icon,
  label,
  value,
  delta,
  className,
}: Readonly<MetricTileProps>) {
  return (
    <div className={cn('bg-card rounded-lg border p-4', className)}>
      <div className="flex items-center gap-2">
        <Icon size={16} className="text-muted-foreground" />
        <span className="text-muted-foreground text-xs tracking-wide uppercase">{label}</span>
      </div>
      <div className="mt-2 flex items-baseline gap-2">
        <span className="text-foreground text-2xl font-semibold">{value}</span>
        {delta && (
          <span className={cn('text-xs', delta.positive ? 'text-emerald-500' : 'text-red-500')}>
            {delta.value}
          </span>
        )}
      </div>
    </div>
  )
}
