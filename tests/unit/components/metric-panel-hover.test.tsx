// @vitest-environment jsdom
// tests/unit/components/metric-panel-hover.test.tsx
import { cleanup, fireEvent, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

interface MockLineChartProps {
  readonly children: ReactNode
  readonly onMouseMove?: (state: { activeTooltipIndex?: number }) => void
  readonly onMouseLeave?: () => void
}

vi.mock('recharts', () => ({
  ResponsiveContainer: ({ children }: { children: ReactNode }) => <>{children}</>,
  LineChart: ({ children, onMouseMove, onMouseLeave }: MockLineChartProps) => (
    <div>
      <button
        type="button"
        data-testid="mousemove"
        onClick={() => onMouseMove?.({ activeTooltipIndex: 3 })}
      />
      <button type="button" data-testid="mousemove-outside" onClick={() => onMouseMove?.({})} />
      <button type="button" data-testid="mouseleave" onClick={() => onMouseLeave?.()} />
      {children}
    </div>
  ),
  CartesianGrid: () => null,
  XAxis: () => null,
  YAxis: () => null,
  Tooltip: () => null,
  Line: () => null,
}))

import { MetricPanel } from '@/app/(app)/_components/charts/metric-panel'
import type { ChartPoint, MetricDescriptor } from '@/app/(app)/_components/charts/use-samples-chart'

const fc: MetricDescriptor = {
  key: 'heart_rate_bpm',
  name: 'FC',
  unit: 'bpm',
  color: 'var(--chart-1)',
  inverted: false,
}

const data: ChartPoint[] = [
  { x: 0, heart_rate_bpm: 120, elevation_m: null, power_w: null, cadence_rpm: null, speed: null },
  { x: 1, heart_rate_bpm: 150, elevation_m: null, power_w: null, cadence_rpm: null, speed: null },
]

describe('MetricPanel hover correlation', () => {
  afterEach(cleanup)

  it('reports the hovered index via onHoverIndexChange', () => {
    const onHoverIndexChange = vi.fn()
    const { getByTestId } = render(
      <MetricPanel
        descriptor={fc}
        data={data}
        xUnit="min"
        showXAxis
        onHoverIndexChange={onHoverIndexChange}
      />
    )
    fireEvent.click(getByTestId('mousemove'))
    expect(onHoverIndexChange).toHaveBeenCalledWith(3)
  })

  it('reports null when the mouse state has no active tooltip index', () => {
    const onHoverIndexChange = vi.fn()
    const { getByTestId } = render(
      <MetricPanel
        descriptor={fc}
        data={data}
        xUnit="min"
        showXAxis
        onHoverIndexChange={onHoverIndexChange}
      />
    )
    fireEvent.click(getByTestId('mousemove-outside'))
    expect(onHoverIndexChange).toHaveBeenCalledWith(null)
  })

  it('clears the hover index on mouse leave', () => {
    const onHoverIndexChange = vi.fn()
    const { getByTestId } = render(
      <MetricPanel
        descriptor={fc}
        data={data}
        xUnit="min"
        showXAxis
        onHoverIndexChange={onHoverIndexChange}
      />
    )
    fireEvent.click(getByTestId('mouseleave'))
    expect(onHoverIndexChange).toHaveBeenCalledWith(null)
  })

  it('does not throw when onHoverIndexChange is not provided', () => {
    const { getByTestId } = render(
      <MetricPanel descriptor={fc} data={data} xUnit="min" showXAxis />
    )
    expect(() => {
      fireEvent.click(getByTestId('mousemove'))
      fireEvent.click(getByTestId('mouseleave'))
    }).not.toThrow()
  })
})
