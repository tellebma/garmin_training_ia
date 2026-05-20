// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { BottomNav } from '@/components/nav/bottom-nav'

afterEach(cleanup)

vi.mock('next/navigation', () => ({
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

describe('BottomNav', () => {
  it('renders the 4 main app links', () => {
    render(<BottomNav />)
    expect(screen.getByText('Plan')).toBeTruthy()
    expect(screen.getByText('Stats')).toBeTruthy()
    expect(screen.getByText('Profil')).toBeTruthy()
    expect(screen.getByText(/Aujourd/)).toBeTruthy()
  })

  it('marks the current pathname link as active (font-medium)', () => {
    render(<BottomNav />)
    const todayLink = screen.getByText(/Aujourd/).closest('a')
    expect(todayLink?.className).toContain('font-medium')

    const planLink = screen.getByText('Plan').closest('a')
    expect(planLink?.className).toContain('text-muted-foreground')
  })
})
