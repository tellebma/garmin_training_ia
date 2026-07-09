// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { SideNav } from '@/components/nav/side-nav'

afterEach(cleanup)

vi.mock('next/navigation', () => ({
  usePathname: vi.fn(() => '/plan'),
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

describe('SideNav', () => {
  it('renders the app title and 4 nav links', () => {
    render(<SideNav />)
    expect(screen.getByText('Garmin Coach')).toBeTruthy()
    expect(screen.getByText('Plan')).toBeTruthy()
    expect(screen.getByText('Stats')).toBeTruthy()
    expect(screen.getByText('Profil')).toBeTruthy()
  })

  it('highlights the active route with accent background', () => {
    render(<SideNav />)
    const planLink = screen.getByText('Plan').closest('a')
    expect(planLink?.className).toContain('bg-accent')

    const statsLink = screen.getByText('Stats').closest('a')
    expect(statsLink?.className).toContain('text-muted-foreground')
  })

  it('does not render an Admin link for a non-admin', () => {
    render(<SideNav isAdmin={false} />)
    expect(screen.queryByText('Admin')).toBeNull()
  })

  it('renders an Admin link pointing to /admin when isAdmin is true', () => {
    render(<SideNav isAdmin />)
    const adminLink = screen.getByText('Admin').closest('a')
    expect(adminLink?.getAttribute('href')).toBe('/admin')
  })
})
