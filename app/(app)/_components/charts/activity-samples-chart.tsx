'use client'

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

interface ActivitySamplesChartProps {
  readonly data: ActivitySample[]
  readonly height?: number
}

function hasMetric(data: ActivitySample[], key: keyof ActivitySample): boolean {
  return data.some((sample) => typeof sample[key] === 'number')
}

function labelMinutes(sample: ActivitySample): string {
  if (typeof sample.elapsed_s === 'number') return `${String(Math.round(sample.elapsed_s / 60))}m`
  return String(sample.sample_index)
}

export function ActivitySamplesChart({ data, height = 320 }: ActivitySamplesChartProps) {
  const chartData = data.map((sample) => ({
    ...sample,
    label: labelMinutes(sample),
    pace_min_km:
      typeof sample.speed_m_s === 'number' && sample.speed_m_s > 0
        ? 1000 / sample.speed_m_s / 60
        : null,
  }))

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={chartData} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="label" tick={{ fontSize: 10 }} interval="preserveStartEnd" />
        <YAxis tick={{ fontSize: 10 }} />
        <Tooltip
          contentStyle={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        {hasMetric(data, 'heart_rate_bpm') && (
          <Line
            type="monotone"
            dataKey="heart_rate_bpm"
            stroke="var(--chart-1)"
            strokeWidth={2}
            dot={false}
            name="FC"
          />
        )}
        {hasMetric(data, 'elevation_m') && (
          <Line
            type="monotone"
            dataKey="elevation_m"
            stroke="var(--chart-2)"
            strokeWidth={2}
            dot={false}
            name="Altitude"
          />
        )}
        {hasMetric(data, 'power_w') && (
          <Line
            type="monotone"
            dataKey="power_w"
            stroke="var(--chart-3)"
            strokeWidth={2}
            dot={false}
            name="Puissance"
          />
        )}
        {hasMetric(data, 'cadence_rpm') && (
          <Line
            type="monotone"
            dataKey="cadence_rpm"
            stroke="var(--chart-4)"
            strokeWidth={2}
            dot={false}
            name="Cadence"
          />
        )}
        {hasMetric(data, 'speed_m_s') && (
          <Line
            type="monotone"
            dataKey="pace_min_km"
            stroke="var(--chart-5)"
            strokeWidth={2}
            dot={false}
            name="Allure min/km"
          />
        )}
      </LineChart>
    </ResponsiveContainer>
  )
}
