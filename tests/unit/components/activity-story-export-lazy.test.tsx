// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'

const canvasToPngBlob = vi.hoisted(() => vi.fn())
const renderActivityStory = vi.hoisted(() => vi.fn())

type RenderModule = typeof RenderModuleType

vi.mock('@/lib/share/export-png', () => ({
  canvasToPngBlob,
  downloadBlob: vi.fn(),
  sharePng: vi.fn(),
  canSharePng: () => false,
}))
vi.mock('@/lib/share/render-activity-story', async () => {
  const actual = await vi.importActual<RenderModule>('@/lib/share/render-activity-story')
  return { ...actual, renderActivityStory }
})

import type * as RenderModuleType from '@/lib/share/render-activity-story'
import { ActivityStoryExportLazy } from '@/app/(app)/_components/share/activity-story-export-lazy'
import type { StoryActivity } from '@/lib/share/story-layout'

const ACTIVITY: StoryActivity = {
  start_time: '2026-07-28T07:12:00.000Z',
  sport: 'bike',
  duration_s: 5820,
  distance_m: 42_350,
  elevation_gain_m: 780,
  tss: 186,
  hr_avg: 148,
  hr_max: 176,
  power_avg: 212,
  pace_avg_s_per_km: null,
  calories: 1240,
}

describe('ActivityStoryExportLazy', () => {
  beforeEach(() => {
    canvasToPngBlob.mockResolvedValue(new Blob(['x'], { type: 'image/png' }))
    HTMLCanvasElement.prototype.getContext = vi.fn(
      () => ({}) as unknown as CanvasRenderingContext2D
    ) as unknown as HTMLCanvasElement['getContext']
  })

  afterEach(() => {
    cleanup()
  })

  it('charge le calque à la demande et lui transmet ses props', async () => {
    render(
      <ActivityStoryExportLazy
        activity={ACTIVITY}
        sport="bike"
        sportLabel="Vélo"
        route={[]}
        elevation={[]}
      />
    )

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Partager en story' })).toBeTruthy()
    })
    // Sans GPS ni altitude, seul le gabarit « Métriques seules » est proposé.
    expect(screen.getByRole('button', { name: 'Métriques seules' })).toBeTruthy()
  })
})
