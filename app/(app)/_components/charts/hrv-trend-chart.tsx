'use client'
import {
  Line,
  LineChart,
  ReferenceArea,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { HrvDto } from '@/lib/dashboard/types'

interface HrvTrendChartProps {
  readonly data: HrvDto[]
  readonly height?: number
}

export function HrvTrendChart({ data, height = 200 }: HrvTrendChartProps) {
  const baselineLow = data.find((d) => d.baseline_low !== null)?.baseline_low ?? null
  const baselineHigh = data.find((d) => d.baseline_high !== null)?.baseline_high ?? null

  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(s: string) => s.slice(5)} />
        <YAxis tick={{ fontSize: 10 }} />
        {baselineLow !== null && baselineHigh !== null && (
          <ReferenceArea
            y1={baselineLow}
            y2={baselineHigh}
            fill="var(--chart-3)"
            fillOpacity={0.12}
          />
        )}
        <Tooltip
          contentStyle={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Line
          type="monotone"
          dataKey="last_night_avg"
          stroke="var(--chart-1)"
          strokeWidth={2}
          dot={false}
          name="HRV (ms)"
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
