// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { BriefingCardSkeleton } from '@/app/(app)/_components/skeletons/briefing-card-skeleton'

afterEach(() => {
  cleanup()
})

describe('BriefingCardSkeleton', () => {
  it('renders an accessible loading region for the daily briefing', () => {
    render(<BriefingCardSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('briefing')
  })
})
