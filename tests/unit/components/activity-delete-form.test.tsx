// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ActivityDeleteForm } from '@/app/(app)/history/[id]/activity-delete-form'

const deleteActivity = vi.fn()
const restoreActivity = vi.fn()
const push = vi.fn()
const refresh = vi.fn()

vi.mock('@/app/actions/activity-visibility', () => ({
  deleteActivity: (...args: unknown[]) => deleteActivity(...args) as unknown,
  restoreActivity: (...args: unknown[]) => restoreActivity(...args) as unknown,
}))

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, refresh }),
}))

describe('ActivityDeleteForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    deleteActivity.mockResolvedValue({ success: true })
    restoreActivity.mockResolvedValue({ success: true })
  })

  afterEach(() => {
    cleanup()
  })

  it('asks for confirmation before deleting, then sends the reason', async () => {
    const user = userEvent.setup()
    render(<ActivityDeleteForm activityId="act-1" excludedAt={null} excludedReason={null} />)

    await user.click(screen.getByRole('button', { name: /Supprimer cette activité/ }))
    await user.type(screen.getByLabelText(/Motif/), 'doublon compteur vélo')
    await user.click(screen.getByRole('button', { name: /Confirmer la suppression/ }))

    await waitFor(() => {
      expect(deleteActivity).toHaveBeenCalledWith({
        activityId: 'act-1',
        reason: 'doublon compteur vélo',
      })
    })
    expect(push).toHaveBeenCalledWith('/history')
  })

  it('lets the athlete back out of the confirmation', async () => {
    const user = userEvent.setup()
    render(<ActivityDeleteForm activityId="act-1" excludedAt={null} excludedReason={null} />)

    await user.click(screen.getByRole('button', { name: /Supprimer cette activité/ }))
    await user.click(screen.getByRole('button', { name: 'Annuler' }))

    expect(screen.queryByRole('button', { name: /Confirmer/ })).toBeNull()
    expect(deleteActivity).not.toHaveBeenCalled()
  })

  it('shows the deleted banner with its reason and restores', async () => {
    const user = userEvent.setup()
    render(
      <ActivityDeleteForm
        activityId="act-1"
        excludedAt="2026-08-24T10:00:00Z"
        excludedReason="doublon compteur vélo"
      />
    )

    expect(screen.getByText(/Activité supprimée/)).toBeTruthy()
    expect(screen.getByText(/doublon compteur vélo/)).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /Restaurer/ }))

    await waitFor(() => {
      expect(restoreActivity).toHaveBeenCalledWith('act-1')
    })
    expect(refresh).toHaveBeenCalled()
  })

  it('keeps the form open and explains when the action fails', async () => {
    deleteActivity.mockResolvedValue({ success: false, error: 'boom' })
    const user = userEvent.setup()
    render(<ActivityDeleteForm activityId="act-1" excludedAt={null} excludedReason={null} />)

    await user.click(screen.getByRole('button', { name: /Supprimer cette activité/ }))
    await user.click(screen.getByRole('button', { name: /Confirmer la suppression/ }))

    await waitFor(() => {
      expect(screen.getByText(/Action impossible/)).toBeTruthy()
    })
    expect(push).not.toHaveBeenCalled()
  })
})
