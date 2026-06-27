'use client'

import dynamic from 'next/dynamic'

const RoutesHeatmap = dynamic(() => import('./routes-heatmap').then((m) => m.RoutesHeatmap), {
  ssr: false,
})

interface RoutesHeatmapLazyProps {
  readonly polylines: unknown[]
}

export function RoutesHeatmapLazy({ polylines }: RoutesHeatmapLazyProps) {
  return <RoutesHeatmap polylines={polylines} />
}
