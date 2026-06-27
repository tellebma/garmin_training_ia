// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi, beforeEach } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const triggerGarminSync = vi.hoisted(() => vi.fn())
vi.mock('@/app/actions/garmin-sync', () => ({ triggerGarminSync }))

import { SyncNowButton } from '@/app/(app)/_components/sync-now-button'

describe('SyncNowButton', () => {
  afterEach(() => {
    cleanup()
    vi.clearAllMocks()
  })

  beforeEach(() => {
    triggerGarminSync.mockReset()
    triggerGarminSync.mockResolvedValue({ status: 'started' })
  })

  it('fires an auto sync on mount', async () => {
    render(<SyncNowButton />)
    await waitFor(() => {
      expect(triggerGarminSync).toHaveBeenCalledWith('auto')
    })
  })

  it('fires a manual sync on click and shows a confirmation', async () => {
    render(<SyncNowButton />)
    await waitFor(() => {
      expect(triggerGarminSync).toHaveBeenCalledWith('auto')
    })
    triggerGarminSync.mockResolvedValue({ status: 'started' })

    await userEvent.click(screen.getByRole('button', { name: /synchroniser/i }))

    await waitFor(() => {
      expect(triggerGarminSync).toHaveBeenCalledWith('manual')
      expect(screen.getByText(/synchronisation lanc/i)).toBeTruthy()
    })
  })

  it('shows a cooldown message on manual cooldown', async () => {
    render(<SyncNowButton />)
    await waitFor(() => {
      expect(triggerGarminSync).toHaveBeenCalledWith('auto')
    })
    triggerGarminSync.mockResolvedValue({ status: 'cooldown', retry_after_seconds: 180 })

    await userEvent.click(screen.getByRole('button', { name: /synchroniser/i }))

    await waitFor(() => {
      expect(screen.getByText(/déjà à jour/i)).toBeTruthy()
    })
  })
})
