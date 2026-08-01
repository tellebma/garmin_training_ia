// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

const renderActivityStory = vi.hoisted(() => vi.fn())
const canvasToPngBlob = vi.hoisted(() => vi.fn())
const downloadBlob = vi.hoisted(() => vi.fn())
const sharePng = vi.hoisted(() => vi.fn())
const canSharePng = vi.hoisted(() => vi.fn())

type RenderModule = typeof RenderModuleType

vi.mock('@/lib/share/export-png', () => ({ canvasToPngBlob, downloadBlob, sharePng, canSharePng }))
vi.mock('@/lib/share/render-activity-story', async () => {
  const actual = await vi.importActual<RenderModule>('@/lib/share/render-activity-story')
  return { ...actual, renderActivityStory }
})

import type * as RenderModuleType from '@/lib/share/render-activity-story'
import { ActivityStoryExport } from '@/app/(app)/_components/share/activity-story-export'
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

const ROUTE = [
  { latitude: 45, longitude: 4 },
  { latitude: 45.01, longitude: 4.01 },
  { latitude: 45.02, longitude: 4.005 },
]

const ELEVATION = [
  { distance_m: 0, elevation_m: 100 },
  { distance_m: 500, elevation_m: 320 },
]

function setup(overrides: Partial<Parameters<typeof ActivityStoryExport>[0]> = {}) {
  return render(
    <ActivityStoryExport
      activity={ACTIVITY}
      sport="bike"
      sportLabel="Vélo"
      route={ROUTE}
      elevation={ELEVATION}
      {...overrides}
    />
  )
}

describe('ActivityStoryExport', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    canSharePng.mockReturnValue(false)
    canvasToPngBlob.mockResolvedValue(new Blob(['x'], { type: 'image/png' }))
    sharePng.mockResolvedValue('shared')
    // jsdom n'implémente pas le contexte 2D : on le simule pour l'effet de rendu.
    HTMLCanvasElement.prototype.getContext = vi.fn(
      () => ({}) as unknown as CanvasRenderingContext2D
    ) as unknown as HTMLCanvasElement['getContext']
  })

  afterEach(() => {
    cleanup()
  })

  it('propose les gabarits disponibles et rend un aperçu', async () => {
    setup()
    expect(screen.getByRole('heading', { name: 'Partager en story' })).toBeTruthy()
    for (const label of [
      'Tracé + métriques',
      'Métriques + tracé',
      'Profil + métriques',
      'Métriques seules',
      'Tracé seul',
    ]) {
      expect(screen.getByRole('button', { name: label })).toBeTruthy()
    }
    await waitFor(() => {
      expect(renderActivityStory).toHaveBeenCalled()
    })
    const spec = renderActivityStory.mock.calls.at(-1)?.[1] as { view: string; format: string }
    expect(spec.view).toBe('trace')
    expect(spec.format).toBe('story')
  })

  it('ne propose que les métriques seules sans GPS ni altitude', () => {
    setup({ route: [], elevation: [] })
    expect(screen.getByRole('button', { name: 'Métriques seules' })).toBeTruthy()
    expect(screen.queryByRole('button', { name: 'Tracé + métriques' })).toBeNull()
  })

  it('change de format et de fond', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: 'Carré 1:1' }))
    await user.click(screen.getByRole('button', { name: 'Sombre' }))
    await waitFor(() => {
      const spec = renderActivityStory.mock.calls.at(-1)?.[1] as {
        format: string
        background: string
      }
      expect(spec.format).toBe('square')
      expect(spec.background).toBe('dark')
    })
  })

  it('plafonne la sélection au nombre de métriques que le gabarit peut porter', async () => {
    const user = userEvent.setup()
    setup()
    // Vue « Tracé + métriques » : une ligne de 3 métriques, déjà pleine.
    expect(screen.getByText('Métriques (3/3)')).toBeTruthy()
    const calories = screen.getByRole('button', { name: 'Calories' })
    await user.click(calories)
    expect(calories.getAttribute('aria-pressed')).toBe('false')

    const distance = screen.getByRole('button', { name: 'Distance' })
    await user.click(distance)
    expect(distance.getAttribute('aria-pressed')).toBe('false')
    await user.click(calories)
    expect(calories.getAttribute('aria-pressed')).toBe('true')
  })

  it('complète la sélection quand le gabarit accepte une métrique de plus', async () => {
    const user = userEvent.setup()
    setup()
    // Sélection pleine (3/3) : le gabarit à 4 emplacements prend la métrique suivante.
    await user.click(screen.getByRole('button', { name: 'Métriques + tracé' }))
    expect(screen.getByText('Métriques (4/4)')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Vitesse' }).getAttribute('aria-pressed')).toBe(
      'true'
    )

    await user.click(screen.getByRole('button', { name: 'Tracé + métriques' }))
    expect(screen.getByText('Métriques (3/3)')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Vitesse' }).getAttribute('aria-pressed')).toBe(
      'false'
    )
  })

  it('ne réintroduit pas une métrique que l’utilisateur a retirée', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: 'Dénivelé' }))
    expect(screen.getByText('Métriques (2/3)')).toBeTruthy()

    await user.click(screen.getByRole('button', { name: 'Métriques + tracé' }))
    expect(screen.getByText('Métriques (2/4)')).toBeTruthy()
    expect(screen.getByRole('button', { name: 'Dénivelé' }).getAttribute('aria-pressed')).toBe(
      'false'
    )
  })

  it('bascule le titre et la signature', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: 'Sport et date' }))
    await user.click(screen.getByRole('button', { name: 'Signature' }))
    await waitFor(() => {
      const spec = renderActivityStory.mock.calls.at(-1)?.[1] as {
        showTitle: boolean
        showBrand: boolean
      }
      expect(spec.showTitle).toBe(false)
      expect(spec.showBrand).toBe(false)
    })
  })

  it('masque métriques et habillage en vue « Tracé seul »', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: 'Tracé seul' }))
    expect(screen.queryByRole('button', { name: 'Distance' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Signature' })).toBeNull()
  })

  it('télécharge le PNG', async () => {
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: /Télécharger le PNG/ }))
    const day = new Date(ACTIVITY.start_time).toLocaleDateString('en-CA')
    await waitFor(() => {
      expect(downloadBlob).toHaveBeenCalledWith(
        expect.any(Blob),
        `garmin-coach-${day}-bike-trace.png`
      )
    })
    expect(screen.getByText('PNG téléchargé.')).toBeTruthy()
  })

  it('signale un encodage impossible', async () => {
    const user = userEvent.setup()
    canvasToPngBlob.mockResolvedValue(null)
    setup()
    await user.click(screen.getByRole('button', { name: /Télécharger le PNG/ }))
    await waitFor(() => {
      expect(screen.getByText("L'image n'a pas pu être générée.")).toBeTruthy()
    })
    expect(downloadBlob).not.toHaveBeenCalled()
  })

  it('n’affiche le bouton Partager que si le navigateur le supporte', async () => {
    canSharePng.mockReturnValue(true)
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: /Partager/ }))
    await waitFor(() => {
      expect(sharePng).toHaveBeenCalledOnce()
    })
    expect(screen.getByText('Image envoyée au partage.')).toBeTruthy()
    expect(downloadBlob).not.toHaveBeenCalled()
  })

  it('retombe sur le téléchargement quand le partage est indisponible', async () => {
    canSharePng.mockReturnValue(true)
    sharePng.mockResolvedValue('unsupported')
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: /Partager/ }))
    await waitFor(() => {
      expect(downloadBlob).toHaveBeenCalledOnce()
    })
    expect(screen.getByText('Partage indisponible : PNG téléchargé à la place.')).toBeTruthy()
  })

  it('reste silencieux quand l’utilisateur annule le partage', async () => {
    canSharePng.mockReturnValue(true)
    sharePng.mockResolvedValue('cancelled')
    const user = userEvent.setup()
    setup()
    await user.click(screen.getByRole('button', { name: /Partager/ }))
    await waitFor(() => {
      expect(sharePng).toHaveBeenCalledOnce()
    })
    expect(downloadBlob).not.toHaveBeenCalled()
    expect(screen.queryByText(/PNG téléchargé/)).toBeNull()
  })

  it('partage le PNG déjà encodé, sans ré-encoder après le clic', async () => {
    // Safari iOS révoque l'activation utilisateur au premier `await` : le partage doit
    // partir du blob préparé par l'effet de rendu, pas d'un encodage déclenché au clic.
    canSharePng.mockReturnValue(true)
    const user = userEvent.setup()
    setup()
    await waitFor(() => {
      expect(canvasToPngBlob).toHaveBeenCalledOnce()
    })

    await user.click(screen.getByRole('button', { name: /Partager/ }))

    await waitFor(() => {
      expect(sharePng).toHaveBeenCalledOnce()
    })
    expect(canvasToPngBlob).toHaveBeenCalledOnce()
  })

  it('encode à la volée si le PNG n’était pas encore prêt', async () => {
    canSharePng.mockReturnValue(true)
    canvasToPngBlob
      .mockResolvedValueOnce(null) // encodage anticipé raté
      .mockResolvedValueOnce(new Blob(['x'], { type: 'image/png' }))
    const user = userEvent.setup()
    setup()
    await waitFor(() => {
      expect(canvasToPngBlob).toHaveBeenCalledOnce()
    })

    await user.click(screen.getByRole('button', { name: /Partager/ }))

    await waitFor(() => {
      expect(sharePng).toHaveBeenCalledOnce()
    })
    expect(canvasToPngBlob).toHaveBeenCalledTimes(2)
  })

  it('n’affiche pas le bouton Partager sur un navigateur sans Web Share', () => {
    setup()
    expect(screen.queryByRole('button', { name: /^Partager$/ })).toBeNull()
  })

  it('ne rend rien sans contexte 2D disponible', () => {
    HTMLCanvasElement.prototype.getContext = vi.fn(() => null)
    setup()
    expect(renderActivityStory).not.toHaveBeenCalled()
  })
})
