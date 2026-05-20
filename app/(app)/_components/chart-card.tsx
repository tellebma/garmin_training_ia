// app/(app)/_components/chart-card.tsx
import { cn } from '@/lib/utils'

interface ChartCardProps {
  title: string
  description?: string
  className?: string
  children: React.ReactNode
}

export function ChartCard({ title, description, className, children }: Readonly<ChartCardProps>) {
  return (
    <section className={cn('bg-card rounded-lg border p-4', className)}>
      <header className="mb-4">
        <h2 className="text-foreground text-base font-semibold">{title}</h2>
        {description && <p className="text-muted-foreground mt-0.5 text-xs">{description}</p>}
      </header>
      {children}
    </section>
  )
}
