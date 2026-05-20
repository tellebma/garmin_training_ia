// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn(), refresh: vi.fn() }),
}))

const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()
vi.mock('sonner', () => ({
  toast: { error: toastErrorMock, success: toastSuccessMock, info: vi.fn() },
}))

interface ActionInput {
  password: string
  confirm: string
}

type ActionResult =
  | { success: true }
  | { success: false; errors: Record<string, string[]> }
  | { success: false; error: string }

function fill(password: string, confirm: string): HTMLFormElement {
  const passwordInput = screen.getByLabelText(/Nouveau mot de passe/i)
  const confirmInput = screen.getByLabelText(/^Confirme$/i)
  fireEvent.change(passwordInput, { target: { value: password } })
  fireEvent.change(confirmInput, { target: { value: confirm } })
  const form = passwordInput.closest('form')
  if (!form) throw new Error('form not found')
  return form
}

describe('SetPasswordForm', () => {
  beforeEach(() => {
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
  })

  it('renders password fields with provided submit label (disabled when empty)', async () => {
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>()
    render(
      <SetPasswordForm
        action={action}
        submitLabel="Définir mon mot de passe"
        submitLabelLoading="Enregistrement..."
      />
    )
    expect(screen.getByLabelText(/Nouveau mot de passe/i)).toBeTruthy()
    expect(screen.getByLabelText(/^Confirme$/i)).toBeTruthy()
    const button = screen.getByRole<HTMLButtonElement>('button', {
      name: /Définir mon mot de passe/i,
    })
    expect(button.disabled).toBe(true)
  })

  it('calls action with password and confirm values; returns early on success', async () => {
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockResolvedValue({
      success: true,
    })
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(<SetPasswordForm action={action} submitLabel="OK" submitLabelLoading="Loading..." />)
    fireEvent.submit(fill('strongpass1', 'strongpass1'))
    await waitFor(() => {
      expect(action).toHaveBeenCalledWith({ password: 'strongpass1', confirm: 'strongpass1' })
    })
    // No toast on success
    expect(toastErrorMock).not.toHaveBeenCalled()
  })

  it('renders field errors when action returns errors', async () => {
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockResolvedValue({
      success: false,
      errors: { password: ['Trop court'], confirm: ['Ne correspond pas'] },
    })
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(<SetPasswordForm action={action} submitLabel="OK" submitLabelLoading="Loading..." />)
    fireEvent.submit(fill('short', 'other'))
    await waitFor(() => {
      expect(screen.getByText('Trop court')).toBeTruthy()
      expect(screen.getByText('Ne correspond pas')).toBeTruthy()
    })
  })

  it('shows already_set toast', async () => {
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockResolvedValue({
      success: false,
      error: 'already_set',
    })
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(<SetPasswordForm action={action} submitLabel="OK" submitLabelLoading="Loading..." />)
    fireEvent.submit(fill('strongpass1', 'strongpass1'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        'Mot de passe déjà défini — utilise "Mot de passe oublié" pour le réinitialiser'
      )
    })
  })

  it('shows unauthenticated toast', async () => {
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockResolvedValue({
      success: false,
      error: 'unauthenticated',
    })
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(<SetPasswordForm action={action} submitLabel="OK" submitLabelLoading="Loading..." />)
    fireEvent.submit(fill('strongpass1', 'strongpass1'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Session expirée — reconnecte-toi')
    })
  })

  it('shows generic save error toast for unknown error code', async () => {
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockResolvedValue({
      success: false,
      error: 'save_failed',
    })
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(<SetPasswordForm action={action} submitLabel="OK" submitLabelLoading="Loading..." />)
    fireEvent.submit(fill('strongpass1', 'strongpass1'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Erreur de sauvegarde')
    })
  })

  it('treats NEXT_REDIRECT thrown error as success (no toast)', async () => {
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockImplementation(() => {
      throw new Error('NEXT_REDIRECT;replace;/onboarding')
    })
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(<SetPasswordForm action={action} submitLabel="OK" submitLabelLoading="Loading..." />)
    fireEvent.submit(fill('strongpass1', 'strongpass1'))
    await waitFor(() => {
      expect(action).toHaveBeenCalled()
    })
    expect(toastErrorMock).not.toHaveBeenCalled()
  })

  it('shows unexpected error toast when a non-redirect error is thrown', async () => {
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockImplementation(() => {
      throw new Error('boom')
    })
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(<SetPasswordForm action={action} submitLabel="OK" submitLabelLoading="Loading..." />)
    fireEvent.submit(fill('strongpass1', 'strongpass1'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Erreur inattendue')
    })
  })

  it('shows loading label while submitting', async () => {
    let resolve: (v: ActionResult) => void = () => {
      // intentionally empty
    }
    const action = vi.fn<(input: ActionInput) => Promise<ActionResult>>().mockReturnValue(
      new Promise<ActionResult>((res) => {
        resolve = res
      })
    )
    const { SetPasswordForm } = await import('@/components/auth/set-password-form')
    render(
      <SetPasswordForm action={action} submitLabel="Définir" submitLabelLoading="Sauvegarde..." />
    )
    fireEvent.submit(fill('strongpass1', 'strongpass1'))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Sauvegarde/i })).toBeTruthy()
    })
    resolve({ success: false, error: 'save_failed' })
  })
})
