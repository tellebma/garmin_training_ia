import { cn } from '@/lib/utils'

function Skeleton({ className, ...props }: React.ComponentProps<'div'>) {
  return (
    <div
      aria-hidden
      className={cn('bg-muted/50 animate-pulse rounded-md motion-reduce:animate-none', className)}
      {...props}
    />
  )
}

export { Skeleton }
