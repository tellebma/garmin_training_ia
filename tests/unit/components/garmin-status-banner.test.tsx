// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { GarminStatusBanner } from '@/app/(app)/_components/garmin-status-banner'

afterEach(() => {
  cleanup()
})

describe('GarminStatusBanner', () => {
  it('renders nothing when status is ok and sync is recent', () => {
    const now = new Date('2026-08-01T12:00:00Z')
    const { container } = render(
      <GarminStatusBanner status="ok" lastActivitiesSyncAt="2026-07-31T18:00:00Z" now={now} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('renders nothing when there is no sync history yet (no_data, not stale)', () => {
    const now = new Date('2026-08-01T12:00:00Z')
    const { container } = render(
      <GarminStatusBanner status="ok" lastActivitiesSyncAt={null} now={now} />
    )
    expect(container.firstChild).toBeNull()
  })

  it('shows the freshness banner with the exact day count when status is ok but data is stale', () => {
    // 19 days, matching the prod incident (#126).
    const now = new Date('2026-08-01T12:00:00Z')
    render(<GarminStatusBanner status="ok" lastActivitiesSyncAt="2026-07-13T12:00:00Z" now={now} />)
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(screen.getByText(/non synchronisées/i)).toBeTruthy()
    expect(screen.getByText(/19 jours/)).toBeTruthy()
  })

  it('prioritizes the specific auth_failed banner over the generic staleness one', () => {
    const now = new Date('2026-08-01T12:00:00Z')
    render(
      <GarminStatusBanner
        status="auth_failed"
        lastActivitiesSyncAt="2026-07-13T12:00:00Z"
        now={now}
      />
    )
    expect(screen.getByText(/Reconnexion Garmin requise/i)).toBeTruthy()
    expect(screen.queryByText(/19 jours/)).toBeNull()
  })
})
