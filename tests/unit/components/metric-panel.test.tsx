// @vitest-environment jsdom
// tests/unit/components/metric-panel.test.tsx
import { render } from '@testing-library/react'
import { describe, expect, it, beforeAll } from 'vitest'
import { MetricPanel } from '@/app/(app)/_components/charts/metric-panel'
import type { ChartPoint, MetricDescriptor } from '@/app/(app)/_components/charts/use-samples-chart'

beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    observe() {}
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    unobserve() {}
    // eslint-disable-next-line @typescript-eslint/no-empty-function
    disconnect() {}
  }
})

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

describe('MetricPanel', () => {
  it('renders the metric name and unit', () => {
    const { getByText } = render(<MetricPanel descriptor={fc} data={data} xUnit="min" showXAxis />)
    expect(getByText(/FC/)).toBeTruthy()
    expect(getByText(/bpm/)).toBeTruthy()
  })
})
