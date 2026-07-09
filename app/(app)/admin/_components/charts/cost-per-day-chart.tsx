'use client'
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { CostPerDayPoint } from '@/lib/admin/types'

interface CostPerDayChartProps {
  readonly data: CostPerDayPoint[]
  readonly height?: number
}

export function CostPerDayChart({ data, height = 200 }: CostPerDayChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
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
          formatter={(value: number) => [`$${value.toFixed(4)}`, 'Coût estimé']}
        />
        <Bar dataKey="cost_usd" fill="var(--chart-1)" radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  )
}
