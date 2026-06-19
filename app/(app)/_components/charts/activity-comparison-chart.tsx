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
import type { ActivityComparisonPoint } from '@/lib/coach/activity-analysis'

interface ActivityComparisonChartProps {
  readonly data: ActivityComparisonPoint[]
  readonly height?: number
}

export function ActivityComparisonChart({ data, height = 280 }: ActivityComparisonChartProps) {
  const visibleData = data.filter(
    (d) => d.activity !== null || d.planned !== null || d.similarAvg !== null
  )

  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={visibleData} margin={{ top: 8, right: 8, left: -16, bottom: 24 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis dataKey="metric" tick={{ fontSize: 10 }} angle={-20} textAnchor="end" height={50} />
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
        <Bar dataKey="activity" fill="var(--chart-1)" name="Réalisé" />
        <Bar dataKey="planned" fill="var(--chart-2)" name="Prévu" />
        <Bar dataKey="similarAvg" fill="var(--chart-3)" name="Moy. similaire" />
      </BarChart>
    </ResponsiveContainer>
  )
}
