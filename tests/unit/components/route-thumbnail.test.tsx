// @vitest-environment jsdom
// tests/unit/components/route-thumbnail.test.tsx
import { render } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { RouteThumbnail } from '@/app/(app)/_components/maps/route-thumbnail'

describe('RouteThumbnail', () => {
  it('renders an svg path for a valid polyline', () => {
    const { container } = render(
      <RouteThumbnail
        polyline={[
          [4.0, 45.0],
          [5.0, 46.0],
        ]}
      />
    )
    const path = container.querySelector('path')
    expect(path).not.toBeNull()
    expect(path?.getAttribute('d')).toBe('M0,100 L100,0')
    expect(container.querySelector('svg')?.getAttribute('viewBox')).toBe('0 0 100 100')
  })

  it('renders nothing when the polyline has no usable route', () => {
    const { container } = render(<RouteThumbnail polyline={[]} />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('renders nothing for the empty-array sentinel', () => {
    const { container } = render(<RouteThumbnail polyline={null} />)
    expect(container.firstChild).toBeNull()
  })
})
