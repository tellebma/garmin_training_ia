// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const askCoach = vi.fn()
vi.mock('@/app/actions/coach-chat', () => ({
  askCoach: (...args: unknown[]) => askCoach(...args) as unknown,
}))

import { ChatPanel } from '@/app/(app)/_components/chat-panel'

function answer(overrides: Record<string, unknown> = {}) {
  return {
    success: true,
    conversationId: 'c1',
    answer: 'Ton TSB est à -13,4.',
    toolsUsed: ['get_form_state'],
    ...overrides,
  }
}

describe('ChatPanel', () => {
  beforeEach(() => {
    askCoach.mockReset()
  })

  afterEach(() => {
    cleanup()
  })

  it('shows suggestions before any exchange', () => {
    render(<ChatPanel />)
    expect(screen.getByText(/Suis-je prêt pour ma prochaine course/)).toBeTruthy()
  })

  it('sends a question and displays the answer', async () => {
    askCoach.mockResolvedValue(answer())
    const user = userEvent.setup()
    render(<ChatPanel />)

    await user.type(screen.getByPlaceholderText('Ta question…'), 'Je suis frais ?')
    await user.click(screen.getByRole('button', { name: 'Envoyer' }))

    await waitFor(() => {
      expect(screen.getByText('Ton TSB est à -13,4.')).toBeTruthy()
    })
    expect(screen.getByText('Je suis frais ?')).toBeTruthy()
  })

  it('lists the data the coach consulted', async () => {
    askCoach.mockResolvedValue(answer({ toolsUsed: ['get_form_state', 'get_form_state'] }))
    const user = userEvent.setup()
    render(<ChatPanel />)

    await user.type(screen.getByPlaceholderText('Ta question…'), 'q')
    await user.click(screen.getByRole('button', { name: 'Envoyer' }))

    await waitFor(() => {
      // Dédupliqué : un outil appelé deux fois ne s'affiche qu'une fois.
      expect(screen.getByText('Données consultées : get_form_state')).toBeTruthy()
    })
  })

  it('continues the same conversation on the second question', async () => {
    askCoach.mockResolvedValue(answer())
    const user = userEvent.setup()
    render(<ChatPanel />)
    const input = screen.getByPlaceholderText('Ta question…')

    await user.type(input, 'première')
    await user.click(screen.getByRole('button', { name: 'Envoyer' }))
    await waitFor(() => {
      expect(screen.getByText('première')).toBeTruthy()
    })

    await user.type(input, 'seconde')
    await user.click(screen.getByRole('button', { name: 'Envoyer' }))

    await waitFor(() => {
      expect(askCoach).toHaveBeenLastCalledWith('seconde', 'c1')
    })
  })

  it('renders an error without losing the question', async () => {
    askCoach.mockResolvedValue({ success: false, error: 'Quota atteint.' })
    const user = userEvent.setup()
    render(<ChatPanel />)

    await user.type(screen.getByPlaceholderText('Ta question…'), 'q')
    await user.click(screen.getByRole('button', { name: 'Envoyer' }))

    await waitFor(() => {
      expect(screen.getByText('Quota atteint.')).toBeTruthy()
    })
    expect(screen.getByText('q')).toBeTruthy()
  })

  it('sends a suggestion on click', async () => {
    askCoach.mockResolvedValue(answer())
    const user = userEvent.setup()
    render(<ChatPanel />)

    await user.click(screen.getByText(/Pourquoi je me sens fatigué/))

    await waitFor(() => {
      expect(askCoach).toHaveBeenCalledWith('Pourquoi je me sens fatigué en ce moment ?', undefined)
    })
  })

  it('keeps the submit button disabled while the draft is empty', () => {
    render(<ChatPanel />)
    const submit = screen.getByRole('button', { name: 'Envoyer' })
    expect((submit as HTMLButtonElement).disabled).toBe(true)
  })
})
