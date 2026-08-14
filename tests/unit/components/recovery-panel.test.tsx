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

  it('reads "improving" as a drop for lower-is-better metrics (issue #180)', () => {
    // Cas prod du 2026-08-14 : stress improving à 23,5 contre une baseline de 26.
    const data: RecoveryBaselines = {
      ...full,
      stress: { ...base, baseline: 26, recent: 23.5, trend: 'improving' },
      restingHr: { ...base, baseline: 46, recent: 44, trend: 'improving' },
    }
    render(<RecoveryPanel data={data} />)
    // Deux métriques inversées, trois qui montent réellement.
    expect(screen.getAllByText('En dessous de ta moyenne · bon signe')).toHaveLength(2)
    expect(screen.getAllByText('Au-dessus de ta moyenne · bon signe')).toHaveLength(3)
    expect(screen.getAllByText('↑')).toHaveLength(3)
    expect(screen.getAllByText('↓')).toHaveLength(2)
  })

  it('reads "declining" as a rise for lower-is-better metrics', () => {
    const data: RecoveryBaselines = {
      ...full,
      stress: { ...base, baseline: 26, recent: 31, trend: 'declining' },
    }
    render(<RecoveryPanel data={data} />)
    // Stress + FC repos (declining dans la fixture) montent tous les deux.
    expect(screen.getAllByText('Au-dessus de ta moyenne · à surveiller')).toHaveLength(2)
  })

  it('keeps the direction of higher-is-better metrics when they decline', () => {
    const data: RecoveryBaselines = {
      ...full,
      hrv: { ...base, trend: 'declining' },
      restingHr: { ...base, trend: 'stable' },
    }
    render(<RecoveryPanel data={data} />)
    expect(screen.getByText('En dessous de ta moyenne · à surveiller')).toBeTruthy()
  })

  it('shows the recent value against its 28-day baseline (issue #180)', () => {
    const data: RecoveryBaselines = {
      ...full,
      stress: { ...base, baseline: 26, recent: 23.5, trend: 'improving' },
    }
    render(<RecoveryPanel data={data} />)
    expect(screen.getByText('23,5')).toBeTruthy()
    expect(screen.getByText(/vs 26\s+sur 28 j/)).toBeTruthy()
    // HRV garde son unité.
    expect(screen.getByText(/vs 50 ms\s+sur 28 j/)).toBeTruthy()
  })

  it('adds the real sleep duration and score next to the composite index', () => {
    render(<RecoveryPanel data={full} />)
    expect(screen.getByText('7h46 · score 82 (moyenne 7h30)')).toBeTruthy()
  })

  it('falls back to a dash when no baseline has been computed yet', () => {
    const empty: RecoveryBaselines = {
      ...full,
      hrv: { ...base, baseline: null, recent: null, trend: 'no_data', confidence: 'no_data' },
    }
    render(<RecoveryPanel data={empty} />)
    // Un tiret pour la valeur, un pour la flèche de tendance.
    expect(screen.getAllByText('—')).toHaveLength(2)
    expect(screen.getByText('Pas assez de données')).toBeTruthy()
  })
})
