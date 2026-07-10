// @vitest-environment jsdom
// tests/unit/components/activity-samples-chart-hover.test.tsx
import { fireEvent, render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import type { ActivitySample } from '@/lib/coach/activity-analysis'

vi.mock('@/app/(app)/_components/charts/metric-panel', () => ({
  MetricPanel: ({
    descriptor,
    onHoverIndexChange,
  }: {
    descriptor: { key: string }
    onHoverIndexChange?: (index: number | null) => void
  }) => (
    <button
      type="button"
      data-testid={`panel-${descriptor.key}`}
      onClick={() => onHoverIndexChange?.(7)}
    />
  ),
}))

import { ActivitySamplesChart } from '@/app/(app)/_components/charts/activity-samples-chart'

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
  sample({ elapsed_s: 0, heart_rate_bpm: 120 }),
  sample({ elapsed_s: 60, heart_rate_bpm: 150 }),
]

describe('ActivitySamplesChart hover forwarding', () => {
  it('forwards onHoverIndexChange down to each rendered metric panel', () => {
    const onHoverIndexChange = vi.fn()
    render(<ActivitySamplesChart data={data} sport="run" onHoverIndexChange={onHoverIndexChange} />)
    fireEvent.click(screen.getByTestId('panel-heart_rate_bpm'))
    expect(onHoverIndexChange).toHaveBeenCalledWith(7)
  })
})
