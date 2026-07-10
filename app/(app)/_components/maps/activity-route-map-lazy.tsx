'use client'

import dynamic from 'next/dynamic'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

const ActivityRouteMap = dynamic(
  () => import('./activity-route-map').then((m) => m.ActivityRouteMap),
  { ssr: false }
)

interface ActivityRouteMapLazyProps {
  readonly samples: ActivitySample[]
  readonly height?: number
  readonly hoverIndex?: number | null
}

export function ActivityRouteMapLazy({ samples, height, hoverIndex }: ActivityRouteMapLazyProps) {
  return (
    <ActivityRouteMap
      samples={samples}
      {...(height !== undefined && { height })}
      {...(hoverIndex !== undefined && { hoverIndex })}
    />
  )
}
