'use client'

import dynamic from 'next/dynamic'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

const ActivityRouteMap = dynamic(
  () => import('./activity-route-map').then((m) => m.ActivityRouteMap),
  { ssr: false }
)

interface ActivityRouteMapLazyProps {
  readonly samples: ActivitySample[]
}

export function ActivityRouteMapLazy({ samples }: ActivityRouteMapLazyProps) {
  return <ActivityRouteMap samples={samples} />
}
