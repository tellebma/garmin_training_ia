// @vitest-environment jsdom
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, fireEvent, waitFor } from '@testing-library/react'

afterEach(cleanup)

beforeAll(() => {
  process.env.NEXT_PUBLIC_SUPABASE_URL = 'https://example.supabase.co'
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY = 'anon-key-test'
})

const signOut = vi.fn().mockResolvedValue(undefined)
const push = vi.fn()
const refresh = vi.fn()

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push, refresh }),
}))

vi.mock('@/lib/supabase/client', () => ({
  createClient: () => ({ auth: { signOut } }),
}))

describe('SignOutButton', () => {
  it('renders a French logout button', async () => {
    const { SignOutButton } = await import('@/components/auth/sign-out-button')
    render(<SignOutButton />)
    expect(screen.getByRole('button', { name: /Se déconnecter/ })).toBeTruthy()
  })

  it('signs out and redirects to /login when clicked', async () => {
    const { SignOutButton } = await import('@/components/auth/sign-out-button')
    render(<SignOutButton />)
    fireEvent.click(screen.getByRole('button'))
    await waitFor(() => {
      expect(signOut).toHaveBeenCalledTimes(1)
    })
    await waitFor(() => {
      expect(push).toHaveBeenCalledWith('/login')
      expect(refresh).toHaveBeenCalledTimes(1)
    })
  })
})
