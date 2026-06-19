'use client'

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { WeeklyPerformancePoint } from '@/lib/dashboard/performance-cockpit'

interface Props {
  readonly data: WeeklyPerformancePoint[]
  readonly height?: number
}

export function PlannedActualChart({ data, height = 260 }: Readonly<Props>) {
  return (
    <div role="img" aria-label="Durée hebdomadaire prévue et réalisée en minutes">
      <ResponsiveContainer width="100%" height={height}>
        <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
          <CartesianGrid vertical={false} stroke="var(--border)" />
          <XAxis dataKey="label" tick={{ fontSize: 11 }} axisLine={false} tickLine={false} />
          <YAxis
            tick={{ fontSize: 10 }}
            tickFormatter={(value: number) => `${String(value)}m`}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            formatter={(value) => [`${String(value)} min`]}
            contentStyle={{
              background: 'var(--card)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              fontSize: 12,
            }}
          />
          <Legend wrapperStyle={{ fontSize: 11 }} />
          <Bar
            dataKey="plannedDurationMin"
            fill="var(--muted-foreground)"
            fillOpacity={0.35}
            radius={[3, 3, 0, 0]}
            name="Prévu"
          />
          <Bar
            dataKey="actualDurationMin"
            fill="var(--chart-2)"
            radius={[3, 3, 0, 0]}
            name="Réalisé"
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
