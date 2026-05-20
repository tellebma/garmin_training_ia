// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

const regen = vi.fn()
vi.mock('@/app/actions/sessions', () => ({
  regenerateSession: (...args: unknown[]) => regen(...args) as unknown,
}))

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

beforeEach(() => {
  regen.mockReset()
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
