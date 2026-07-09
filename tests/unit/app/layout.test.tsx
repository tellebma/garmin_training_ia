// @vitest-environment jsdom
import { describe, expect, it, vi, afterEach, beforeEach } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'

const getUser = vi.fn()
const rpc = vi.fn()
vi.mock('@/lib/supabase/server', () => ({
  createClient: () => Promise.resolve({ auth: { getUser }, rpc }),
}))
vi.mock('next/navigation', () => ({
  redirect: vi.fn(),
  usePathname: vi.fn(() => '/today'),
}))
vi.mock('next/link', () => ({
  default: ({
    href,
    children,
    className,
  }: {
    href: string
    children: React.ReactNode
    className?: string
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}))
vi.mock('@/app/actions/garmin-sync', () => ({
  triggerGarminSync: vi.fn().mockResolvedValue({ status: 'started' }),
}))

import AppLayout from '@/app/(app)/layout'

beforeEach(() => {
  getUser.mockReset()
  rpc.mockReset()
})

afterEach(cleanup)

describe('AppLayout maintenance mode', () => {
  it('shows the maintenance page to a non-admin when maintenance_mode is active', async () => {
    getUser.mockResolvedValue({ data: { user: { id: 'u1' } } })
    rpc.mockImplementation((fn: string) => {
      if (fn === 'is_admin_caller') return Promise.resolve({ data: false })
      if (fn === 'is_feature_flag_active') return Promise.resolve({ data: true })
      return Promise.resolve({ data: null })
    })
    const ui = await AppLayout({ children: <div>app content</div> })
    render(ui)
    expect(screen.getByText(/maintenance/i)).toBeTruthy()
    expect(screen.queryByText('app content')).toBeNull()
  })

  it('still shows normal content to an admin during maintenance', async () => {
    getUser.mockResolvedValue({ data: { user: { id: 'owner' } } })
    rpc.mockImplementation((fn: string) => {
      if (fn === 'is_admin_caller') return Promise.resolve({ data: true })
      if (fn === 'is_feature_flag_active') return Promise.resolve({ data: true })
      return Promise.resolve({ data: null })
    })
    const ui = await AppLayout({ children: <div>app content</div> })
    render(ui)
    expect(screen.getByText('app content')).toBeTruthy()
  })
})
