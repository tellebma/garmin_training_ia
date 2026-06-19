// @vitest-environment jsdom
import { cleanup, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { ActivityFeedbackForm } from '@/app/(app)/history/[id]/activity-feedback-form'

const saveActivityFeedback = vi.fn()

vi.mock('@/app/actions/activity-feedback', () => ({
  saveActivityFeedback: (...args: unknown[]) => saveActivityFeedback(...args) as unknown,
}))

describe('ActivityFeedbackForm', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    saveActivityFeedback.mockResolvedValue({ success: true })
  })

  afterEach(() => {
    cleanup()
  })

  it('shows the session-RPE load and saves the selected effort', async () => {
    const user = userEvent.setup()
    render(
      <ActivityFeedbackForm
        activityId="8f9dce34-c156-4b0f-90c2-ee55acb1d4b0"
        durationSeconds={3600}
        initialFeedback={null}
      />
    )

    expect(screen.getByText('300 u.a.')).toBeTruthy()
    const rpeGroup = screen.getByRole('group', { name: 'Effort global (RPE)' })
    await user.click(within(rpeGroup).getByRole('button', { name: '7' }))
    expect(screen.getByText('420 u.a.')).toBeTruthy()
    await user.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => {
      expect(saveActivityFeedback).toHaveBeenCalled()
    })
    expect(saveActivityFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ rpe: 7, activityId: '8f9dce34-c156-4b0f-90c2-ee55acb1d4b0' })
    )
    expect(await screen.findByText('Ressenti enregistré')).toBeTruthy()
  })

  it('reveals the pain area when a discomfort is selected', async () => {
    const user = userEvent.setup()
    render(
      <ActivityFeedbackForm
        activityId="8f9dce34-c156-4b0f-90c2-ee55acb1d4b0"
        durationSeconds={1800}
        initialFeedback={null}
      />
    )

    const painGroup = screen.getByRole('group', { name: /Douleur ou gêne/ })
    await user.click(within(painGroup).getByRole('button', { name: '2' }))

    expect(screen.getByLabelText('Zone concernée')).toBeTruthy()
  })

  it('loads and updates an existing feedback', () => {
    render(
      <ActivityFeedbackForm
        activityId="8f9dce34-c156-4b0f-90c2-ee55acb1d4b0"
        durationSeconds={3600}
        initialFeedback={{
          activity_id: '8f9dce34-c156-4b0f-90c2-ee55acb1d4b0',
          rpe: 8,
          fatigue: 4,
          soreness: null,
          pain: 0,
          mood: 3,
          perceived_difficulty: 'harder',
          pain_area: null,
          comment: 'Séance exigeante',
          updated_at: '2026-06-19T08:00:00Z',
        }}
      />
    )

    expect(screen.getByText('480 u.a.')).toBeTruthy()
    expect(screen.getByDisplayValue('Séance exigeante')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Mettre à jour' })).toBeTruthy()
  })
})
