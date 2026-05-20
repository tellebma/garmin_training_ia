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

const push = vi.fn()
const refresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, refresh }),
}))

const loginMock = vi.fn()
vi.mock('@/app/(auth)/_actions/auth', () => ({
  login: (...args: unknown[]) => loginMock(...args) as unknown,
}))

const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()
vi.mock('sonner', () => ({
  toast: { error: toastErrorMock, success: toastSuccessMock, info: vi.fn() },
}))

interface LoginInput {
  email: string
  password: string
}

function fillForm(email: string, password: string): HTMLFormElement {
  const emailInput = screen.getByLabelText(/Email/i)
  const passwordInput = screen.getByLabelText(/Mot de passe/i)
  fireEvent.change(emailInput, { target: { value: email } })
  fireEvent.change(passwordInput, { target: { value: password } })
  const form = emailInput.closest('form')
  if (!form) throw new Error('form not found')
  return form
}

describe('EmailPasswordForm', () => {
  beforeEach(() => {
    loginMock.mockReset()
  })

  it('renders email and password fields with submit button disabled when empty', async () => {
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    expect(screen.getByLabelText(/Email/i)).toBeTruthy()
    expect(screen.getByLabelText(/Mot de passe/i)).toBeTruthy()
    const button = screen.getByRole<HTMLButtonElement>('button', { name: /Se connecter/i })
    expect(button.disabled).toBe(true)
  })

  it('enables submit when both fields are filled', async () => {
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    fillForm('me@example.com', 'pass1234')
    const button = screen.getByRole<HTMLButtonElement>('button', { name: /Se connecter/i })
    expect(button.disabled).toBe(false)
  })

  it('calls login and redirects to /today on success', async () => {
    loginMock.mockResolvedValue({ success: true })
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    const form = fillForm('me@example.com', 'pass1234')
    fireEvent.submit(form)
    await waitFor(() => {
      expect(loginMock).toHaveBeenCalledWith({ email: 'me@example.com', password: 'pass1234' })
    })
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith('/today')
      expect(refresh).toHaveBeenCalledTimes(1)
    })
  })

  it('shows field-level errors when zod returns errors', async () => {
    loginMock.mockResolvedValue({
      success: false,
      errors: { email: ['Email invalide'], password: ['Trop court'] },
    })
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    const form = fillForm('bad', 'short')
    fireEvent.submit(form)
    await waitFor(() => {
      expect(screen.getByText('Email invalide')).toBeTruthy()
      expect(screen.getByText('Trop court')).toBeTruthy()
    })
    expect(push).not.toHaveBeenCalled()
  })

  it('shows rate_limited toast', async () => {
    loginMock.mockResolvedValue({ success: false, error: 'rate_limited' })
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    fireEvent.submit(fillForm('me@example.com', 'pass1234'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Trop de tentatives, réessaie dans 15 minutes')
    })
  })

  it('shows ip_unresolved toast', async () => {
    loginMock.mockResolvedValue({ success: false, error: 'ip_unresolved' })
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    fireEvent.submit(fillForm('me@example.com', 'pass1234'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        "Impossible de résoudre ton IP — contacte l'admin"
      )
    })
  })

  it('shows generic toast for invalid_credentials', async () => {
    loginMock.mockResolvedValue({ success: false, error: 'invalid_credentials' })
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    fireEvent.submit(fillForm('me@example.com', 'pass1234'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Email ou mot de passe incorrect')
    })
  })

  it('disables inputs while loading', async () => {
    let resolve: (v: unknown) => void = () => {
      // intentionally empty
    }
    loginMock.mockReturnValue(
      new Promise((res) => {
        resolve = res
      })
    )
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    const form = fillForm('me@example.com', 'pass1234')
    fireEvent.submit(form)
    await waitFor(() => {
      const button = screen.getByRole<HTMLButtonElement>('button', { name: /Connexion/i })
      expect(button.disabled).toBe(true)
    })
    resolve({ success: false, error: 'invalid_credentials' })
  })

  it('passes typed input shape to login action', async () => {
    loginMock.mockResolvedValue({ success: true })
    const { EmailPasswordForm } = await import('@/components/auth/email-password-form')
    render(<EmailPasswordForm />)
    fireEvent.submit(fillForm('user@test.io', 'mypassword'))
    await waitFor(() => {
      const callArg = loginMock.mock.calls[0]?.[0] as LoginInput
      expect(callArg.email).toBe('user@test.io')
      expect(callArg.password).toBe('mypassword')
    })
  })
})
