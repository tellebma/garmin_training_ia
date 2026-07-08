// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ColsWidgetSkeleton } from '@/app/(app)/_components/skeletons/cols-widget-skeleton'

afterEach(() => {
  cleanup()
})

describe('ColsWidgetSkeleton', () => {
  it('renders an accessible loading region for the cols widget', () => {
    render(<ColsWidgetSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('cols')
  })
})
