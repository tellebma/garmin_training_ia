// app/(app)/_components/empty-state.tsx
import { cn } from '@/lib/utils'
import type { LucideIcon } from 'lucide-react'

interface EmptyStateProps {
  icon: LucideIcon
  title: string
  description?: string
  className?: string
}

export function EmptyState({
  icon: Icon,
  title,
  description,
  className,
}: Readonly<EmptyStateProps>) {
  return (
    <div
      className={cn(
        'border-border/50 flex flex-col items-center justify-center rounded-lg border border-dashed py-8 text-center',
        className
      )}
    >
      <Icon size={32} className="text-muted-foreground/60 mb-2" />
      <p className="text-foreground text-sm font-medium">{title}</p>
      {description && <p className="text-muted-foreground mt-1 max-w-xs text-xs">{description}</p>}
    </div>
  )
}
