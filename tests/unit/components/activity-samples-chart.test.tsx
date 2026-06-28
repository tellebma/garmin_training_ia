// @vitest-environment jsdom
// tests/unit/components/activity-samples-chart.test.tsx
import { fireEvent, render, cleanup } from '@testing-library/react'
import { describe, expect, it, beforeAll, afterEach } from 'vitest'
import { ActivitySamplesChart } from '@/app/(app)/_components/charts/activity-samples-chart'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

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

afterEach(() => {
  cleanup()
})

function sample(partial: Partial<ActivitySample>): ActivitySample {
  return {
    sample_index: 0,
    sample_time: null,
    elapsed_s: null,
    distance_m: null,
    elevation_m: null,
    heart_rate_bpm: null,
    power_w: null,
    cadence_rpm: null,
    speed_m_s: null,
    latitude: null,
    longitude: null,
    ...partial,
  }
}

const data: ActivitySample[] = [
  sample({ elapsed_s: 0, distance_m: 0, heart_rate_bpm: 120, speed_m_s: 3 }),
  sample({ elapsed_s: 60, distance_m: 200, heart_rate_bpm: 150, speed_m_s: 3 }),
]

describe('ActivitySamplesChart', () => {
  it('renders a chip per available metric', () => {
    const { getByRole } = render(<ActivitySamplesChart data={data} sport="run" />)
    expect(getByRole('button', { name: /FC/ })).toBeTruthy()
    expect(getByRole('button', { name: /Allure/ })).toBeTruthy()
  })

  it('labels the speed panel min/km for running', () => {
    const { getByText } = render(<ActivitySamplesChart data={data} sport="run" />)
    expect(getByText(/min\/km/)).toBeTruthy()
  })

  it('hides a metric panel when its chip is toggled off', () => {
    const { getByRole, queryByText } = render(<ActivitySamplesChart data={data} sport="run" />)
    fireEvent.click(getByRole('button', { name: /FC/ }))
    expect(queryByText(/bpm/)).toBeNull()
  })

  it('disables the distance toggle when no sample has distance', () => {
    const noDist = [sample({ elapsed_s: 0, heart_rate_bpm: 120 })]
    const { getByRole } = render(<ActivitySamplesChart data={noDist} sport="bike" />)
    expect(getByRole('button', { name: /Distance/ }).hasAttribute('disabled')).toBe(true)
  })
})
