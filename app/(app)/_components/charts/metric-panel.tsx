'use client'

import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { ChartPoint, MetricDescriptor } from './use-samples-chart'

interface MetricPanelProps {
  readonly descriptor: MetricDescriptor
  readonly data: ChartPoint[]
  readonly xUnit: 'min' | 'km'
  readonly showXAxis: boolean
  readonly height?: number
  readonly onHoverIndexChange?: (index: number | null) => void
}

export function MetricPanel({
  descriptor,
  data,
  xUnit,
  showXAxis,
  height = 96,
  onHoverIndexChange,
}: MetricPanelProps) {
  return (
    <div>
      <div className="text-muted-foreground mb-1 flex items-center gap-2 text-xs">
        <span
          className="inline-block h-2 w-2 rounded-full"
          style={{ background: descriptor.color }}
          aria-hidden
        />
        <span className="font-medium">{descriptor.name}</span>
        <span>({descriptor.unit})</span>
      </div>
      <ResponsiveContainer width="100%" height={height}>
        <LineChart
          data={data}
          syncId="activity-samples"
          margin={{ top: 4, right: 8, left: -16, bottom: showXAxis ? 0 : -8 }}
          onMouseMove={(state: { activeTooltipIndex?: number }) => {
            onHoverIndexChange?.(
              typeof state.activeTooltipIndex === 'number' ? state.activeTooltipIndex : null
            )
          }}
          onMouseLeave={() => {
            onHoverIndexChange?.(null)
          }}
        >
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border)" />
          <XAxis
            dataKey="x"
            type="number"
            domain={['dataMin', 'dataMax']}
            tick={showXAxis ? { fontSize: 10 } : false}
            height={showXAxis ? 20 : 0}
            tickFormatter={(v: number) => (xUnit === 'km' ? v.toFixed(1) : String(Math.round(v)))}
            unit={showXAxis ? ` ${xUnit}` : ''}
          />
          <YAxis
            tick={{ fontSize: 10 }}
            width={40}
            domain={['auto', 'auto']}
            reversed={descriptor.inverted}
          />
          <Tooltip
            contentStyle={{
              background: 'var(--card)',
              border: '1px solid var(--border)',
              borderRadius: 6,
              fontSize: 12,
            }}
            formatter={(value: number | string) => [
              `${String(value)} ${descriptor.unit}`,
              descriptor.name,
            ]}
          />
          <Line
            type="monotone"
            dataKey={descriptor.key}
            stroke={descriptor.color}
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
            name={descriptor.name}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
