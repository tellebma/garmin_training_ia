'use client'
import {
  Bar,
  BarChart,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { SleepDto } from '@/lib/dashboard/types'

function scoreColor(score: number | null): string {
  if (score === null) return 'var(--muted)'
  if (score < 60) return '#ef4444'
  if (score < 80) return '#f59e0b'
  return '#10b981'
}

interface SleepTrendChartProps {
  readonly data: SleepDto[]
  readonly height?: number
}

export function SleepTrendChart({ data, height = 200 }: SleepTrendChartProps) {
  return (
    <ResponsiveContainer width="100%" height={height}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: -16, bottom: 0 }}>
        <XAxis dataKey="date" tick={{ fontSize: 10 }} tickFormatter={(s: string) => s.slice(5)} />
        <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
        <Tooltip
          contentStyle={{
            background: 'var(--card)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
          }}
        />
        <ReferenceLine y={80} stroke="var(--chart-3)" strokeDasharray="3 3" />
        <Bar dataKey="score" name="Score sommeil">
          {data.map((d) => (
            <Cell key={d.date} fill={scoreColor(d.score)} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  )
}
