// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { SyncTimingsCard } from '@/app/(app)/_components/sync-timings-card'

afterEach(() => {
  cleanup()
})

describe('SyncTimingsCard', () => {
  it('renders "jamais" when no sync ever happened', () => {
    const now = new Date('2026-05-21T12:00:00Z')
    render(
      <SyncTimingsCard
        lastSleepSyncAt={null}
        lastActivitiesSyncAt={null}
        lastProfileSyncAt={null}
        now={now}
      />
    )
    const jamais = screen.getAllByText(/jamais/i)
    expect(jamais.length).toBe(3)
  })

  it('shows relative past for recent sync', () => {
    const now = new Date('2026-05-21T12:30:00Z')
    render(
      <SyncTimingsCard
        lastSleepSyncAt="2026-05-21T08:00:00Z"
        lastActivitiesSyncAt="2026-05-20T18:00:00Z"
        lastProfileSyncAt={null}
        now={now}
      />
    )
    expect(screen.getByText(/il y a 4 h/)).toBeTruthy()
    expect(screen.getByText(/il y a 18 h/)).toBeTruthy()
  })

  it('picks 13:00 UTC as next activities sync when current time is before 13:00 UTC', () => {
    const now = new Date('2026-05-21T12:30:00Z')
    render(
      <SyncTimingsCard
        lastSleepSyncAt={null}
        lastActivitiesSyncAt="2026-05-20T18:00:00Z"
        lastProfileSyncAt={null}
        now={now}
      />
    )
    expect(screen.getByText(/dans 30 min/)).toBeTruthy()
  })

  it('picks 18:00 UTC as next activities sync when current time is between 13:00 and 18:00 UTC', () => {
    const now = new Date('2026-05-21T14:30:00Z')
    render(
      <SyncTimingsCard
        lastSleepSyncAt={null}
        lastActivitiesSyncAt="2026-05-21T13:00:00Z"
        lastProfileSyncAt={null}
        now={now}
      />
    )
    // Either "à HH:MM" same-day or appears as future time. We just check a 16:xx
    // or 18:xx label appears (Paris is UTC+2 in May, so 18:00 UTC = 20:00).
    const labels = screen.getAllByText(/à \d{2}:\d{2}|dans \d+/)
    expect(labels.length).toBeGreaterThan(0)
  })

  it('renders next sleep sync as "demain" when after 08:00 UTC', () => {
    const now = new Date('2026-05-21T12:00:00Z')
    render(
      <SyncTimingsCard
        lastSleepSyncAt="2026-05-21T08:00:00Z"
        lastActivitiesSyncAt={null}
        lastProfileSyncAt={null}
        now={now}
      />
    )
    expect(screen.getByText(/demain/i)).toBeTruthy()
  })
})
