// @vitest-environment jsdom
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'

const order = vi.fn()
const eq = vi.fn()
const select = vi.fn()

function buildQuery(finalValue: { data: unknown; error: null }) {
  const q: Record<string, unknown> = {}
  q.select = select.mockReturnValue(q)
  q.eq = eq.mockReturnValue(q)
  q.order = order.mockResolvedValue(finalValue)
  return q
}

let queryResult: { data: unknown; error: null } = { data: [], error: null }

vi.mock('@/lib/supabase/server', () => ({
  createClient: vi.fn(async () => ({
    from: vi.fn(() => buildQuery(queryResult)),
  })),
}))

describe('ActivityColsGravis', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryResult = { data: [], error: null }
  })

  it('renders nothing when no col was crossed', async () => {
    const { ActivityColsGravis } = await import('@/app/(app)/_components/activity-cols-gravis')
    const jsx = await ActivityColsGravis({ userId: 'user-1', garminActivityId: 123 })
    expect(jsx).toBeNull()
  })

  it('renders the crossed cols with name and elevation', async () => {
    queryResult = {
      data: [
        {
          col_id: 'col-a',
          crossed_at: '2026-06-01T08:00:00Z',
          cols: { name: 'Col du Galibier', elevation_m: 2642 },
        },
        {
          col_id: 'col-b',
          crossed_at: '2026-06-01T10:00:00Z',
          cols: { name: 'Col du Télégraphe', elevation_m: null },
        },
      ],
      error: null,
    }
    const { ActivityColsGravis } = await import('@/app/(app)/_components/activity-cols-gravis')
    const jsx = await ActivityColsGravis({ userId: 'user-1', garminActivityId: 123 })
    render(jsx)

    expect(screen.getByText('Cols gravis')).toBeTruthy()
    expect(screen.getByText('Col du Galibier')).toBeTruthy()
    expect(screen.getByText('2642 m')).toBeTruthy()
    expect(screen.getByText('Col du Télégraphe')).toBeTruthy()
    expect(screen.getByText('—')).toBeTruthy()
  })

  it('scopes the query to the given user and activity', async () => {
    const { ActivityColsGravis } = await import('@/app/(app)/_components/activity-cols-gravis')
    await ActivityColsGravis({ userId: 'user-42', garminActivityId: 999 })

    expect(eq).toHaveBeenCalledWith('user_id', 'user-42')
    expect(eq).toHaveBeenCalledWith('garmin_activity_id', 999)
  })
})
