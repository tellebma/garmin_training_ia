// @vitest-environment jsdom
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor, act } from '@testing-library/react'

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
  vi.useRealTimers()
})

// Mock Server Actions
const connectGarmin = vi.fn()
const submitGarminMfa = vi.fn()
vi.mock('@/app/actions/garmin-auth', () => ({
  connectGarmin: (...args: unknown[]) => connectGarmin(...args) as unknown,
  submitGarminMfa: (...args: unknown[]) => submitGarminMfa(...args) as unknown,
}))

const toastSuccess = vi.fn()
const toastError = vi.fn()
vi.mock('sonner', () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccess(...args) as unknown,
    error: (...args: unknown[]) => toastError(...args) as unknown,
  },
}))

interface FillArgs {
  email?: string
  password?: string
}

function fillForm({ email = 'rider@example.com', password = 'super-secret' }: FillArgs = {}) {
  const emailInput = screen.getByLabelText('Email Garmin Connect')
  const passwordInput = screen.getByLabelText('Mot de passe Garmin')
  fireEvent.change(emailInput, { target: { value: email } })
  fireEvent.change(passwordInput, { target: { value: password } })
  return { emailInput, passwordInput }
}

describe('ConnectForm', () => {
  let onMfaRequired: ReturnType<typeof vi.fn<(challengeId: string) => void>>
  let onConnected: ReturnType<typeof vi.fn<() => void>>

  beforeEach(() => {
    onMfaRequired = vi.fn<(challengeId: string) => void>()
    onConnected = vi.fn<() => void>()
  })

  it('renders the form with disabled submit button when fields are empty', async () => {
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    expect(screen.getByLabelText('Email Garmin Connect')).toBeTruthy()
    expect(screen.getByLabelText('Mot de passe Garmin')).toBeTruthy()
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Connecter Garmin' })
    expect(button.disabled).toBe(true)
  })

  it('enables the submit button once fields are filled', async () => {
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Connecter Garmin' })
    expect(button.disabled).toBe(false)
  })

  it('calls onConnected and shows success toast on status=connected', async () => {
    connectGarmin.mockResolvedValueOnce({ status: 'connected' })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(connectGarmin).toHaveBeenCalledWith('rider@example.com', 'super-secret')
    })
    await waitFor(() => {
      expect(onConnected).toHaveBeenCalledTimes(1)
      expect(toastSuccess).toHaveBeenCalledWith('Compte Garmin connecté !')
    })
  })

  it('calls onMfaRequired with challenge id when status=mfa_required', async () => {
    connectGarmin.mockResolvedValueOnce({ status: 'mfa_required', challenge_id: 'chal-123' })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(onMfaRequired).toHaveBeenCalledWith('chal-123')
    })
  })

  it('shows invalid_credentials toast and starts cooldown (custom retry under 60s)', async () => {
    connectGarmin.mockResolvedValueOnce({
      status: 'invalid_credentials',
      retry_after_seconds: 30,
    })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('Identifiants Garmin invalides')
      )
    })
    // button should switch to cooldown label "Réessaye dans 30s"
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans/ })).toBeTruthy()
    })
  })

  it('uses default retry (60s) for invalid_credentials when missing', async () => {
    connectGarmin.mockResolvedValueOnce({ status: 'invalid_credentials' })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    // Toast uses the explicit retry value (60s) formatted as "1 min"
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(expect.stringContaining('1 min'))
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans/ })).toBeTruthy()
    })
  })

  it('shows rate_limited toast with min-formatted cooldown', async () => {
    connectGarmin.mockResolvedValueOnce({
      status: 'rate_limited',
      retry_after_seconds: 1800,
    })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('30 min'),
        expect.objectContaining({ duration: 15_000 })
      )
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans/ })).toBeTruthy()
    })
  })

  it('uses default retry (30 min) for rate_limited when missing', async () => {
    connectGarmin.mockResolvedValueOnce({ status: 'rate_limited' })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('30 min'),
        expect.objectContaining({ duration: 15_000 })
      )
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans/ })).toBeTruthy()
    })
  })

  it('shows garmin_error toast with error_id', async () => {
    connectGarmin.mockResolvedValueOnce({
      status: 'garmin_error',
      type: 'GarminConnectError',
      error_id: 'err-42',
    })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('err-42'),
        expect.objectContaining({ duration: 15_000 })
      )
    })
  })

  it('logs and shows unexpected_error toast', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    connectGarmin.mockResolvedValueOnce({
      status: 'unexpected_error',
      type: 'RuntimeError',
      error_id: 'err-99',
    })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled()
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('err-99'),
        expect.objectContaining({ duration: 15_000 })
      )
    })
    consoleSpy.mockRestore()
  })

  it('shows generic error toast when the action throws', async () => {
    connectGarmin.mockRejectedValueOnce(new Error('network down'))
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Erreur: network down')
    })
  })

  it('disables the submit button while loading and shows loading label', async () => {
    let resolveFn!: (value: { status: string }) => void
    connectGarmin.mockReturnValueOnce(
      new Promise<{ status: string }>((resolve) => {
        resolveFn = resolve
      })
    )
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      const btn = screen.getByRole<HTMLButtonElement>('button', { name: 'Connexion...' })
      expect(btn.disabled).toBe(true)
    })
    await act(async () => {
      resolveFn({ status: 'connected' })
    })
  })

  it('decreases the cooldown over time via the interval and clears it', async () => {
    connectGarmin.mockResolvedValueOnce({
      status: 'invalid_credentials',
      retry_after_seconds: 2,
    })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    // Initially the button shows a cooldown label
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans/ })).toBeTruthy()
    })
    // After ~2.5s the interval tick recomputes remainingSec=0 and the label returns to "Connecter Garmin"
    await waitFor(
      () => {
        expect(screen.getByRole('button', { name: 'Connecter Garmin' })).toBeTruthy()
      },
      { timeout: 5000 }
    )
  }, 10000)

  it('blocks submission while on cooldown', async () => {
    connectGarmin.mockResolvedValueOnce({
      status: 'invalid_credentials',
      retry_after_seconds: 120,
    })
    const { ConnectForm } = await import('@/components/garmin/connect-form')
    render(<ConnectForm onMfaRequired={onMfaRequired} onConnected={onConnected} />)
    fillForm()
    fireEvent.click(screen.getByRole('button', { name: 'Connecter Garmin' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans \d+ min/ })).toBeTruthy()
    })
    const form = screen.getByRole('button', { name: /Réessaye dans/ }).closest('form')
    expect(form).not.toBeNull()
    expect(connectGarmin).toHaveBeenCalledTimes(1)
    // directly fire a submit on the form — should be a no-op (cooldown guard)
    if (form) fireEvent.submit(form)
    // give microtasks a tick
    await waitFor(() => {
      expect(connectGarmin).toHaveBeenCalledTimes(1)
    })
  })
})
