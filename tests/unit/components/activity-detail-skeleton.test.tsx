// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { ActivityDetailSkeleton } from '@/app/(app)/_components/skeletons/activity-detail-skeleton'

afterEach(() => {
  cleanup()
})

describe('ActivityDetailSkeleton', () => {
  it('renders an accessible loading region for the activity analysis', () => {
    render(<ActivityDetailSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('activité')
  })
})
