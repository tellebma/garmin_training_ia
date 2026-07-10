'use client'

import { useState } from 'react'
import type { ActivitySample } from '@/lib/coach/activity-analysis'
import type { Sport } from '@/lib/dashboard/types'
import { ChartCard } from '../chart-card'
import { ActivityRouteMapLazy } from '../maps/activity-route-map-lazy'
import { ActivitySamplesChart } from './activity-samples-chart'

interface ActivityMapChartSyncProps {
  readonly samples: ActivitySample[]
  readonly sport: Sport
  readonly showMap: boolean
}

export function ActivityMapChartSync({ samples, sport, showMap }: ActivityMapChartSyncProps) {
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)

  return (
    <>
      {showMap && (
        <ChartCard
          title="Trace GPS"
          description="Parcours de l'activité d'après les données Garmin."
        >
          <ActivityRouteMapLazy samples={samples} hoverIndex={hoverIndex} />
        </ChartCard>
      )}

      <ChartCard
        title="Courbes d'activité"
        description="Fréquence cardiaque, altitude, puissance, cadence et allure selon les données Garmin disponibles."
      >
        <ActivitySamplesChart data={samples} sport={sport} onHoverIndexChange={setHoverIndex} />
      </ChartCard>
    </>
  )
}
