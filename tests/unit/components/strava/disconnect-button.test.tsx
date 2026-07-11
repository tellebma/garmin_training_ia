// @vitest-environment jsdom
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const disconnectStrava = vi.fn()
vi.mock('@/app/actions/strava-auth', () => ({
  disconnectStrava: (...a: unknown[]) => disconnectStrava(...a) as unknown,
}))

const refresh = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh }),
}))

import { StravaDisconnectButton } from '@/components/strava/disconnect-button'

beforeEach(() => {
  disconnectStrava.mockReset()
  refresh.mockReset()
})

describe('StravaDisconnectButton', () => {
  it('calls disconnectStrava and refreshes the router on click', async () => {
    disconnectStrava.mockResolvedValue({ status: 'disconnected' })
    render(<StravaDisconnectButton />)

    fireEvent.click(screen.getByRole('button', { name: /déconnecter/i }))

    await waitFor(() => {
      expect(disconnectStrava).toHaveBeenCalled()
      expect(refresh).toHaveBeenCalled()
    })
  })
})
