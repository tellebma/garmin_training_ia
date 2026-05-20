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

const requestPasswordResetMock = vi.fn()
vi.mock('@/app/(auth)/_actions/auth', () => ({
  requestPasswordReset: (...args: unknown[]) => requestPasswordResetMock(...args) as unknown,
}))

vi.mock('sonner', () => ({
  toast: { error: vi.fn(), success: vi.fn(), info: vi.fn() },
}))

function fillEmail(email: string): HTMLFormElement {
  const input = screen.getByLabelText(/Email/i)
  fireEvent.change(input, { target: { value: email } })
  const form = input.closest('form')
  if (!form) throw new Error('form not found')
  return form
}

describe('ForgotPasswordForm', () => {
  beforeEach(() => {
    requestPasswordResetMock.mockReset()
  })

  it('renders the email field and submit button (disabled when empty)', async () => {
    const { ForgotPasswordForm } = await import('@/components/auth/forgot-password-form')
    render(<ForgotPasswordForm />)
    expect(screen.getByLabelText(/Email/i)).toBeTruthy()
    const button = screen.getByRole<HTMLButtonElement>('button', { name: /Envoyer le lien/i })
    expect(button.disabled).toBe(true)
  })

  it('enables button when an email is typed', async () => {
    const { ForgotPasswordForm } = await import('@/components/auth/forgot-password-form')
    render(<ForgotPasswordForm />)
    fillEmail('me@example.com')
    const button = screen.getByRole<HTMLButtonElement>('button', { name: /Envoyer le lien/i })
    expect(button.disabled).toBe(false)
  })

  it('calls requestPasswordReset and shows confirmation regardless of outcome (success)', async () => {
    requestPasswordResetMock.mockResolvedValue({ success: true })
    const { ForgotPasswordForm } = await import('@/components/auth/forgot-password-form')
    render(<ForgotPasswordForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(requestPasswordResetMock).toHaveBeenCalledWith({ email: 'me@example.com' })
    })
    await waitFor(() => {
      expect(screen.getByText(/me@example.com/)).toBeTruthy()
    })
    expect(screen.getByText(/un email avec un lien de/i)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Retour à la connexion/i })).toBeTruthy()
  })

  it('shows generic confirmation even when action errors (no email enum leak)', async () => {
    requestPasswordResetMock.mockResolvedValue({ success: false, error: 'ip_unresolved' })
    const { ForgotPasswordForm } = await import('@/components/auth/forgot-password-form')
    render(<ForgotPasswordForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(screen.getByText(/me@example.com/)).toBeTruthy()
    })
  })

  it('shows loading label while submitting', async () => {
    let resolve: (v: unknown) => void = () => {
      // intentionally empty
    }
    requestPasswordResetMock.mockReturnValue(
      new Promise((res) => {
        resolve = res
      })
    )
    const { ForgotPasswordForm } = await import('@/components/auth/forgot-password-form')
    render(<ForgotPasswordForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /^Envoi\.\.\.$/i })).toBeTruthy()
    })
    resolve({ success: true })
  })

  it('renders the "back to login" link before submission', async () => {
    const { ForgotPasswordForm } = await import('@/components/auth/forgot-password-form')
    render(<ForgotPasswordForm />)
    expect(screen.getByRole('link', { name: /Retour à la connexion/i })).toBeTruthy()
  })
})
