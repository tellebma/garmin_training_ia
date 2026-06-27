// @vitest-environment jsdom
import { describe, expect, it, afterEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import { RecoveryPanel } from '@/app/(app)/_components/recovery-panel'
import type { RecoveryBaselines } from '@/lib/dashboard/recovery'

afterEach(cleanup)

const base = {
  baseline: 50,
  recent: 55,
  trend: 'improving' as const,
  confidence: 'high' as const,
  freshness: 'fresh' as const,
  daysCovered: 28,
  lastDate: '2026-06-27',
}

const full: RecoveryBaselines = {
  computedAt: '2026-06-27T05:00:00Z',
  hrv: base,
  restingHr: { ...base, trend: 'declining' },
  sleep: {
    ...base,
    durationBaselineS: 27000,
    durationRecentS: 28000,
    scoreBaseline: 80,
    scoreRecent: 82,
  },
  stress: base,
  bodyBattery: base,
}

describe('RecoveryPanel', () => {
  it('renders an empty state when data is null', () => {
    render(<RecoveryPanel data={null} />)
    expect(screen.getByText(/bient.t disponible/i)).toBeTruthy()
  })

  it('renders a card per metric with prudent labels', () => {
    render(<RecoveryPanel data={full} />)
    expect(screen.getByText(/HRV/i)).toBeTruthy()
    expect(screen.getByText(/FC repos/i)).toBeTruthy()
    expect(screen.getByText(/Sommeil/i)).toBeTruthy()
    expect(screen.getByText(/Stress/i)).toBeTruthy()
    expect(screen.getByText(/Body Battery/i)).toBeTruthy()
  })

  it('flags insufficient data', () => {
    const low: RecoveryBaselines = {
      ...full,
      hrv: { ...base, confidence: 'low', trend: 'no_data' },
    }
    render(<RecoveryPanel data={low} />)
    expect(screen.getByText(/donn.es insuffisantes/i)).toBeTruthy()
  })

  it('renders stable trend label and glyph', () => {
    const stable: RecoveryBaselines = {
      ...full,
      hrv: { ...base, trend: 'stable' },
    }
    render(<RecoveryPanel data={stable} />)
    expect(screen.getByText('Dans ta moyenne')).toBeTruthy()
    expect(screen.getByText('→')).toBeTruthy()
  })

  it('renders stale badge when freshness is stale and confidence is high', () => {
    const stale: RecoveryBaselines = {
      ...full,
      hrv: { ...base, freshness: 'stale', confidence: 'high' },
    }
    render(<RecoveryPanel data={stale} />)
    expect(screen.getByText('Donnée ancienne')).toBeTruthy()
  })
})
