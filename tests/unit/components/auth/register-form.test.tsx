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

const registerMock = vi.fn()
vi.mock('@/app/(auth)/_actions/auth', () => ({
  registerWithMagicLink: (...args: unknown[]) => registerMock(...args) as unknown,
}))

const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()
vi.mock('sonner', () => ({
  toast: { error: toastErrorMock, success: toastSuccessMock, info: vi.fn() },
}))

function fillEmail(email: string): HTMLFormElement {
  const input = screen.getByLabelText(/Email/i)
  fireEvent.change(input, { target: { value: email } })
  const form = input.closest('form')
  if (!form) throw new Error('form not found')
  return form
}

describe('RegisterForm', () => {
  beforeEach(() => {
    registerMock.mockReset()
  })

  it('renders the email field and submit button (disabled when empty)', async () => {
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    expect(screen.getByLabelText(/Email/i)).toBeTruthy()
    const button = screen.getByRole<HTMLButtonElement>('button', { name: /Créer mon compte/i })
    expect(button.disabled).toBe(true)
  })

  it('renders link to login', async () => {
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    expect(screen.getByRole('link', { name: /Se connecter/i })).toBeTruthy()
  })

  it('shows sent confirmation and success toast on success', async () => {
    registerMock.mockResolvedValue({ success: true })
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(registerMock).toHaveBeenCalledWith({ email: 'me@example.com' })
    })
    await waitFor(() => {
      expect(toastSuccessMock).toHaveBeenCalledWith(
        "Si cet email est autorisé, un lien vient d'être envoyé. Vérifie ta boîte."
      )
    })
    // confirmation block uses email value
    expect(screen.getByText(/me@example.com/)).toBeTruthy()
    expect(screen.getByRole('link', { name: /Retour à la connexion/i })).toBeTruthy()
  })

  it('shows field errors when zod returns errors', async () => {
    registerMock.mockResolvedValue({
      success: false,
      errors: { email: ['Email invalide'] },
    })
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    fireEvent.submit(fillEmail('bad'))
    await waitFor(() => {
      expect(screen.getByText('Email invalide')).toBeTruthy()
    })
    expect(toastSuccessMock).not.toHaveBeenCalled()
  })

  it('shows rate_limited toast', async () => {
    registerMock.mockResolvedValue({ success: false, error: 'rate_limited' })
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        'Trop de tentatives depuis ton IP, réessaie dans 1 heure'
      )
    })
  })

  it('shows ip_unresolved toast', async () => {
    registerMock.mockResolvedValue({ success: false, error: 'ip_unresolved' })
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        "Impossible de résoudre ton IP — contacte l'admin"
      )
    })
  })

  it('shows email_not_allowed toast', async () => {
    registerMock.mockResolvedValue({ success: false, error: 'email_not_allowed' })
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith(
        "Cet email n'est pas autorisé à s'inscrire. Contacte l'admin pour demander un accès."
      )
    })
  })

  it('shows generic toast on unexpected error', async () => {
    registerMock.mockResolvedValue({ success: false, error: 'save_failed' })
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Erreur inattendue, réessaie')
    })
  })

  it('shows loading label while submitting', async () => {
    let resolve: (v: unknown) => void = () => {
      // intentionally empty
    }
    registerMock.mockReturnValue(
      new Promise((res) => {
        resolve = res
      })
    )
    const { RegisterForm } = await import('@/components/auth/register-form')
    render(<RegisterForm />)
    fireEvent.submit(fillEmail('me@example.com'))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Envoi du lien/i })).toBeTruthy()
    })
    resolve({ success: false, error: 'save_failed' })
  })
})
