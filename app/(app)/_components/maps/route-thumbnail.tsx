// app/(app)/_components/maps/route-thumbnail.tsx
import { cn } from '@/lib/utils'
import { polylineToSvgPath } from '@/lib/maps/route-thumbnail'

interface RouteThumbnailProps {
  readonly polyline: unknown
  readonly size?: number
  readonly className?: string
}

export function RouteThumbnail({ polyline, size = 100, className }: RouteThumbnailProps) {
  const route = polylineToSvgPath(polyline, size)
  if (!route) return null

  return (
    <svg
      viewBox={route.viewBox}
      className={cn('text-primary', className)}
      role="img"
      aria-label="Aperçu du parcours"
      fill="none"
    >
      <path
        d={route.d}
        stroke="currentColor"
        strokeWidth={3}
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  )
}
