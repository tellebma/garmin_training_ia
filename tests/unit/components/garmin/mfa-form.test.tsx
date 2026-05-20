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

function fillCode(value = '123456') {
  const codeInput = screen.getByLabelText(/Code à 6 chiffres/)
  fireEvent.change(codeInput, { target: { value } })
  return codeInput
}

describe('MfaForm', () => {
  let onConnected: ReturnType<typeof vi.fn<() => void>>
  let onCancel: ReturnType<typeof vi.fn<() => void>>

  beforeEach(() => {
    onConnected = vi.fn<() => void>()
    onCancel = vi.fn<() => void>()
  })

  it('renders the MFA input, validate button, and cancel button', async () => {
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    expect(screen.getByLabelText(/Code à 6 chiffres/)).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Valider' })).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Annuler' })).toBeTruthy()
  })

  it('keeps the submit button disabled while code is shorter than 4 chars', async () => {
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('12')
    const button = screen.getByRole<HTMLButtonElement>('button', { name: 'Valider' })
    expect(button.disabled).toBe(true)
    fillCode('1234')
    expect(screen.getByRole<HTMLButtonElement>('button', { name: 'Valider' }).disabled).toBe(false)
  })

  it('calls onCancel when the cancel button is clicked', async () => {
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fireEvent.click(screen.getByRole('button', { name: 'Annuler' }))
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('submits the code and calls onConnected on status=connected', async () => {
    submitGarminMfa.mockResolvedValueOnce({ status: 'connected' })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-7" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('654321')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(submitGarminMfa).toHaveBeenCalledWith('chal-7', '654321')
    })
    await waitFor(() => {
      expect(onConnected).toHaveBeenCalledTimes(1)
      expect(toastSuccess).toHaveBeenCalledWith('Compte Garmin connecté !')
    })
  })

  it('shows invalid_code toast and starts cooldown (custom retry)', async () => {
    submitGarminMfa.mockResolvedValueOnce({
      status: 'invalid_code',
      retry_after_seconds: 20,
    })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(expect.stringContaining('Code MFA invalide'))
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans \d+s/ })).toBeTruthy()
    })
  })

  it('uses default retry (60s) for invalid_code when missing', async () => {
    submitGarminMfa.mockResolvedValueOnce({ status: 'invalid_code' })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans \d+ min/ })).toBeTruthy()
    })
  })

  it('calls onCancel on status=challenge_expired with error toast', async () => {
    submitGarminMfa.mockResolvedValueOnce({ status: 'challenge_expired' })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Challenge expiré, réessaye depuis le début')
      expect(onCancel).toHaveBeenCalledTimes(1)
    })
  })

  it('calls onCancel on status=challenge_user_mismatch with error toast', async () => {
    submitGarminMfa.mockResolvedValueOnce({ status: 'challenge_user_mismatch' })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Challenge invalide pour cet utilisateur')
      expect(onCancel).toHaveBeenCalledTimes(1)
    })
  })

  it('shows rate_limited toast and cooldown (custom retry)', async () => {
    submitGarminMfa.mockResolvedValueOnce({
      status: 'rate_limited',
      retry_after_seconds: 600,
    })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('rate-limités'),
        expect.objectContaining({ duration: 15_000 })
      )
    })
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans \d+ min/ })).toBeTruthy()
    })
  })

  it('uses default retry (30 min) for rate_limited when missing', async () => {
    submitGarminMfa.mockResolvedValueOnce({ status: 'rate_limited' })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans \d+ min/ })).toBeTruthy()
    })
  })

  it('shows garmin_error toast with error_id', async () => {
    submitGarminMfa.mockResolvedValueOnce({
      status: 'garmin_error',
      type: 'GarminMfaError',
      error_id: 'err-mfa-1',
    })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('err-mfa-1'),
        expect.objectContaining({ duration: 15_000 })
      )
    })
  })

  it('logs and shows unexpected_error toast', async () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    submitGarminMfa.mockResolvedValueOnce({
      status: 'unexpected_error',
      type: 'RuntimeError',
      error_id: 'err-unx-mfa',
    })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalled()
      expect(toastError).toHaveBeenCalledWith(
        expect.stringContaining('err-unx-mfa'),
        expect.objectContaining({ duration: 15_000 })
      )
    })
    consoleSpy.mockRestore()
  })

  it('shows generic error toast when the action throws', async () => {
    submitGarminMfa.mockRejectedValueOnce(new Error('socket reset'))
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(toastError).toHaveBeenCalledWith('Erreur: socket reset')
    })
  })

  it('disables the submit button while loading and shows loading label', async () => {
    let resolveFn!: (value: { status: string }) => void
    submitGarminMfa.mockReturnValueOnce(
      new Promise<{ status: string }>((resolve) => {
        resolveFn = resolve
      })
    )
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      const btn = screen.getByRole<HTMLButtonElement>('button', { name: 'Vérification...' })
      expect(btn.disabled).toBe(true)
    })
    // Annuler is also disabled while loading
    const cancelBtn = screen.getByRole<HTMLButtonElement>('button', { name: 'Annuler' })
    expect(cancelBtn.disabled).toBe(true)
    await act(async () => {
      resolveFn({ status: 'connected' })
    })
  })

  it('decreases the cooldown over time via the interval', async () => {
    vi.useFakeTimers()
    const start = new Date('2026-05-20T12:00:00Z').getTime()
    vi.setSystemTime(start)
    submitGarminMfa.mockResolvedValueOnce({
      status: 'invalid_code',
      retry_after_seconds: 4,
    })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await vi.waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans \ds/ })).toBeTruthy()
    })
    await act(async () => {
      vi.setSystemTime(start + 2000)
      vi.advanceTimersByTime(2000)
    })
    expect(screen.getByRole('button', { name: /Réessaye dans \ds/ })).toBeTruthy()
    await act(async () => {
      vi.setSystemTime(start + 5000)
      vi.advanceTimersByTime(3000)
    })
    expect(screen.getByRole('button', { name: 'Valider' })).toBeTruthy()
  })

  it('blocks submission while on cooldown', async () => {
    submitGarminMfa.mockResolvedValueOnce({
      status: 'invalid_code',
      retry_after_seconds: 90,
    })
    const { MfaForm } = await import('@/components/garmin/mfa-form')
    render(<MfaForm challengeId="chal-1" onConnected={onConnected} onCancel={onCancel} />)
    fillCode('111111')
    fireEvent.click(screen.getByRole('button', { name: 'Valider' }))
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /Réessaye dans/ })).toBeTruthy()
    })
    expect(submitGarminMfa).toHaveBeenCalledTimes(1)
    const form = screen.getByRole('button', { name: /Réessaye dans/ }).closest('form')
    expect(form).not.toBeNull()
    if (form) fireEvent.submit(form)
    await waitFor(() => {
      expect(submitGarminMfa).toHaveBeenCalledTimes(1)
    })
  })
})
