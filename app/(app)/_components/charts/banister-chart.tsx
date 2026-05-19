'use client'
import { Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { BanisterPoint } from '@/lib/dashboard/types'

interface BanisterChartProps {
  readonly data: BanisterPoint[]
  readonly height?: number
}

export function BanisterChart({ data, height = 240 }: BanisterChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <XAxis
          dataKey="date"
          tick={{ fontSize: 10 }}
          interval="preserveStartEnd"
          tickFormatter={(s: string) => s.slice(5)}
        />
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
        <Line
          type="monotone"
          dataKey="ctl"
          stroke="var(--chart-1)"
          strokeWidth={2}
          dot={false}
          name="CTL (fitness)"
        />
        <Line
          type="monotone"
          dataKey="atl"
          stroke="var(--chart-2)"
          strokeWidth={2}
          dot={false}
          name="ATL (fatigue)"
        />
        <Line
          type="monotone"
          dataKey="tsb"
          stroke="var(--chart-3)"
          strokeWidth={2}
          dot={false}
          name="TSB (forme)"
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
