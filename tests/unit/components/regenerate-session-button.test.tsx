// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

const regen = vi.fn()
vi.mock('@/app/actions/sessions', () => ({
  regenerateSession: (...args: unknown[]) => regen(...args) as unknown,
}))

const refresh = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ refresh }),
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  regen.mockReset()
  refresh.mockReset()
})

describe('RegenerateSessionButton', () => {
  it('calls regenerateSession on click', async () => {
    regen.mockResolvedValueOnce({ success: true })
    const { RegenerateSessionButton } =
      await import('@/app/(app)/_components/regenerate-session-button')
    render(<RegenerateSessionButton sessionId="sess-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Régénérer' }))
    await waitFor(() => {
      expect(regen).toHaveBeenCalledWith('sess-1')
    })
  })

  it('refreshes the page after a successful regeneration', async () => {
    regen.mockResolvedValueOnce({ success: true })
    const { RegenerateSessionButton } =
      await import('@/app/(app)/_components/regenerate-session-button')
    render(<RegenerateSessionButton sessionId="sess-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Régénérer' }))
    await waitFor(() => {
      expect(refresh).toHaveBeenCalled()
    })
  })

  it('does not refresh when the action fails', async () => {
    regen.mockResolvedValueOnce({ success: false, error: 'oops' })
    const { RegenerateSessionButton } =
      await import('@/app/(app)/_components/regenerate-session-button')
    render(<RegenerateSessionButton sessionId="sess-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Régénérer' }))
    await waitFor(() => {
      expect(screen.getByText('oops')).toBeTruthy()
    })
    expect(refresh).not.toHaveBeenCalled()
  })

  it('shows error when action fails', async () => {
    regen.mockResolvedValueOnce({ success: false, error: 'oops' })
    const { RegenerateSessionButton } =
      await import('@/app/(app)/_components/regenerate-session-button')
    render(<RegenerateSessionButton sessionId="sess-1" />)
    fireEvent.click(screen.getByRole('button', { name: 'Régénérer' }))
    await waitFor(() => {
      expect(screen.getByText('oops')).toBeTruthy()
    })
  })
})
