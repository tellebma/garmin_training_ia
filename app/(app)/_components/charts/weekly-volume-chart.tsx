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
import type { WeeklyVolumePoint } from '@/lib/dashboard/types'

interface WeeklyVolumeChartProps {
  readonly data: WeeklyVolumePoint[]
  readonly height?: number
}

export function WeeklyVolumeChart({ data, height = 240 }: WeeklyVolumeChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
        <XAxis
          dataKey="week"
          tick={{ fontSize: 10 }}
          tickFormatter={(w: string) => w.split('-W')[1] ?? w}
        />
        <YAxis tick={{ fontSize: 10 }} tickFormatter={(v: number) => `${String(v)}m`} />
        <Tooltip
          contentStyle={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <Legend wrapperStyle={{ fontSize: 11 }} />
        <Bar dataKey="swim" stackId="vol" fill="var(--chart-1)" name="Natation" />
        <Bar dataKey="bike" stackId="vol" fill="var(--chart-2)" name="Vélo" />
        <Bar dataKey="run" stackId="vol" fill="var(--chart-3)" name="Course" />
      </BarChart>
    </ResponsiveContainer>
  )
}
