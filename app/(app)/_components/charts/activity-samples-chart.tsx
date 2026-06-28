'use client'

import { useState } from 'react'
import type { ActivitySample } from '@/lib/coach/activity-analysis'
import type { Sport } from '@/lib/dashboard/types'
import { MetricPanel } from './metric-panel'
import { availableMetrics, buildChartData, hasDistance, type MetricKey } from './use-samples-chart'

interface ActivitySamplesChartProps {
  readonly data: ActivitySample[]
  readonly sport: Sport
  readonly height?: number
}

export function ActivitySamplesChart({ data, sport, height = 96 }: ActivitySamplesChartProps) {
  const distanceAvailable = hasDistance(data)
  const [xBasis, setXBasis] = useState<'time' | 'distance'>('time')
  const [hidden, setHidden] = useState<Set<MetricKey>>(new Set())

  const metrics = availableMetrics(data, sport)
  const effectiveBasis = xBasis === 'distance' && distanceAvailable ? 'distance' : 'time'
  const chartData = buildChartData(data, sport, effectiveBasis)
  const visible = metrics.filter((m) => !hidden.has(m.key))

  function toggleMetric(key: MetricKey) {
    setHidden((prev) => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key)
      else next.add(key)
      return next
    })
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <div className="bg-muted flex rounded-md p-0.5 text-xs">
          <button
            type="button"
            onClick={() => {
              setXBasis('time')
            }}
            className={`rounded px-2 py-1 ${effectiveBasis === 'time' ? 'bg-card font-medium' : 'text-muted-foreground'}`}
          >
            Temps
          </button>
          <button
            type="button"
            disabled={!distanceAvailable}
            onClick={() => {
              setXBasis('distance')
            }}
            className={`rounded px-2 py-1 ${effectiveBasis === 'distance' ? 'bg-card font-medium' : 'text-muted-foreground'} disabled:opacity-40`}
          >
            Distance
          </button>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {metrics.map((m) => {
            const active = !hidden.has(m.key)
            return (
              <button
                key={m.key}
                type="button"
                onClick={() => {
                  toggleMetric(m.key)
                }}
                aria-pressed={active}
                className={`rounded-full border px-2 py-0.5 text-xs ${active ? 'text-foreground border-transparent' : 'text-muted-foreground opacity-60'}`}
                style={
                  active
                    ? { background: `color-mix(in srgb, ${m.color} 18%, transparent)` }
                    : undefined
                }
              >
                {m.name}
              </button>
            )
          })}
        </div>
      </div>

      {visible.length === 0 ? (
        <p className="text-muted-foreground py-8 text-center text-sm">
          Sélectionne au moins une métrique à afficher.
        </p>
      ) : (
        <div className="space-y-2">
          {visible.map((m, idx) => (
            <MetricPanel
              key={m.key}
              descriptor={m}
              data={chartData}
              xUnit={effectiveBasis === 'distance' ? 'km' : 'min'}
              showXAxis={idx === visible.length - 1}
              height={height}
            />
          ))}
        </div>
      )}
    </div>
  )
}
