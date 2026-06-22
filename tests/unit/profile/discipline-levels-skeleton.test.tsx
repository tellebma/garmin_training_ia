// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { DisciplineLevelsSkeleton } from '@/app/(app)/profile/_components/discipline-levels-skeleton'

afterEach(() => {
  cleanup()
})

describe('DisciplineLevelsSkeleton', () => {
  it('renders a titled status region with placeholder rows', () => {
    render(<DisciplineLevelsSkeleton />)
    const region = screen.getByRole('status')
    expect(region.getAttribute('aria-label')).toContain('niveau par discipline')
  })
})
