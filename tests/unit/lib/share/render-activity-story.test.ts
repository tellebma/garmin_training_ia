import { describe, expect, it, vi } from 'vitest'
import {
  availableStoryViews,
  fitFontSize,
  renderActivityStory,
  withAlpha,
  type StorySpec,
} from '@/lib/share/render-activity-story'
import type { StorySegment } from '@/lib/share/story-segments'

interface FakeCall {
  readonly op: string
  readonly args: readonly unknown[]
}

interface FakeCtx {
  readonly ctx: CanvasRenderingContext2D
  readonly calls: FakeCall[]
  texts: () => string[]
}

/** Contexte 2D minimal : jsdom n'implémente pas `getContext('2d')`. */
function fakeContext(charWidth = 20): FakeCtx {
  const calls: FakeCall[] = []
  const record =
    (op: string) =>
    (...args: unknown[]) => {
      calls.push({ op, args })
    }
  const target = {
    save: record('save'),
    restore: record('restore'),
    clearRect: record('clearRect'),
    fillRect: record('fillRect'),
    beginPath: record('beginPath'),
    moveTo: record('moveTo'),
    lineTo: record('lineTo'),
    closePath: record('closePath'),
    stroke: record('stroke'),
    fill: record('fill'),
    arc: record('arc'),
    fillText: record('fillText'),
    createLinearGradient: (...args: unknown[]) => {
      calls.push({ op: 'createLinearGradient', args })
      return { addColorStop: record('addColorStop') }
    },
    measureText: (text: string) => ({ width: text.length * charWidth }),
    font: '',
    fillStyle: '' as unknown,
    strokeStyle: '' as unknown,
    lineWidth: 0,
    lineCap: 'butt',
    lineJoin: 'miter',
    textAlign: 'left',
    textBaseline: 'alphabetic',
    shadowColor: '',
    shadowBlur: 0,
    shadowOffsetX: 0,
    shadowOffsetY: 0,
  }
  return {
    ctx: target as unknown as CanvasRenderingContext2D,
    calls,
    texts: () => calls.filter((c) => c.op === 'fillText').map((c) => String(c.args[0])),
  }
}

const ROUTE = [
  { latitude: 45, longitude: 4 },
  { latitude: 45.01, longitude: 4.01 },
  { latitude: 45.02, longitude: 4.005 },
]

const ELEVATION = [
  { distance_m: 0, elevation_m: 100 },
  { distance_m: 500, elevation_m: 320 },
  { distance_m: 1000, elevation_m: 180 },
]

/** Trace d'un triathlon : le temps écoulé rattache chaque point à sa discipline. */
const MULTISPORT_ROUTE = Array.from({ length: 9 }, (_, index) => ({
  latitude: 45 + index / 1000,
  longitude: 4 + (index % 3) / 1000,
  elapsed_s: index * 100,
}))

const SWIM: StorySegment = {
  sport: 'swim',
  duration_s: 300,
  distance_m: 1500,
  elevation_gain_m: null,
  hr_avg: 150,
  pace_avg_s_per_km: null,
}

const SEGMENTS: StorySegment[] = [
  SWIM,
  {
    sport: 'bike',
    duration_s: 300,
    distance_m: 40_000,
    elevation_gain_m: 320,
    hr_avg: 145,
    pace_avg_s_per_km: null,
  },
  {
    sport: 'run',
    duration_s: 300,
    distance_m: 10_000,
    elevation_gain_m: 40,
    hr_avg: 158,
    pace_avg_s_per_km: null,
  },
]

const SPEC: StorySpec = {
  view: 'trace',
  format: 'story',
  background: 'transparent',
  accent: '#22d3ee',
  title: 'Vélo',
  subtitle: 'mardi 28 juillet 2026',
  metrics: [
    { key: 'distance', label: 'Distance', value: '42 km' },
    { key: 'duration', label: 'Durée', value: '1h37' },
  ],
  route: ROUTE,
  elevation: ELEVATION,
  brand: 'Garmin Training Coach',
}

describe('withAlpha', () => {
  it('convertit un hex long', () => {
    expect(withAlpha('#22d3ee', 0.5)).toBe('rgba(34,211,238,0.5)')
  })

  it('convertit un hex court', () => {
    expect(withAlpha('#fff', 1)).toBe('rgba(255,255,255,1)')
  })

  it('laisse passer une couleur non hex', () => {
    expect(withAlpha('rgba(0,0,0,0.5)', 0.2)).toBe('rgba(0,0,0,0.5)')
  })
})

describe('fitFontSize', () => {
  it('garde la taille quand le texte tient', () => {
    const { ctx } = fakeContext(2)
    expect(fitFontSize(ctx, '42 km', '700', 64, 400)).toBe(64)
  })

  it('réduit la taille quand le texte déborde', () => {
    const { ctx } = fakeContext(20)
    expect(fitFontSize(ctx, '26.2 km/h', '700', 92, 100)).toBeLessThan(92)
  })

  it('ne descend pas sous la taille plancher', () => {
    const { ctx } = fakeContext(1000)
    expect(fitFontSize(ctx, 'texte impossible', '700', 92, 10)).toBe(22)
  })

  it('renvoie la taille demandée sans measureText exploitable', () => {
    const ctx = {} as unknown as CanvasRenderingContext2D
    expect(fitFontSize(ctx, '42 km', '700', 64, 400)).toBe(64)
  })
})

describe('renderActivityStory', () => {
  it('dessine titre, date, métriques et signature en vue trace', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, SPEC)
    const texts = fake.texts()
    expect(texts).toContain('VÉLO · MARDI 28 JUILLET 2026')
    expect(texts).toContain('42 km')
    expect(texts).toContain('Distance')
    expect(texts).toContain('Garmin Training Coach')
    expect(fake.calls.some((c) => c.op === 'lineTo')).toBe(true)
  })

  it('n’opacifie rien sur fond transparent', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, SPEC)
    const fullBleed = fake.calls.filter(
      (c) => c.op === 'fillRect' && c.args[2] === 1080 && c.args[3] === 1920
    )
    expect(fullBleed).toHaveLength(0)
    expect(fake.calls.filter((c) => c.op === 'clearRect')).toHaveLength(1)
  })

  it('peint un aplat sur fond sombre', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, background: 'dark' })
    expect(
      fake.calls.some((c) => c.op === 'fillRect' && c.args[2] === 1080 && c.args[3] === 1920)
    ).toBe(true)
    expect(fake.calls.some((c) => c.op === 'createLinearGradient')).toBe(false)
  })

  it('peint un dégradé sur fond dégradé', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, background: 'gradient' })
    expect(fake.calls.some((c) => c.op === 'createLinearGradient')).toBe(true)
  })

  it('ne dessine aucun texte en vue minimal', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, view: 'minimal' })
    expect(fake.texts()).toEqual([])
    expect(fake.calls.some((c) => c.op === 'lineTo')).toBe(true)
  })

  it('annote l’altitude maximale en vue profil', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, view: 'profil' })
    expect(fake.texts()).toContain('320 m')
  })

  it.each([
    ['montée pure (sommet au dernier point)', [100, 400, 900]],
    ['descente pure (sommet au premier point)', [900, 400, 100]],
  ])('garde l’annotation d’altitude dans la zone sûre — %s', (_case, elevations) => {
    // 20 px par caractère : « 900 m » mesure 100 px, largement de quoi déborder d'un bord.
    const fake = fakeContext(20)
    const elevation = elevations.map((elevation_m, index) => ({
      distance_m: index * 500,
      elevation_m,
    }))
    renderActivityStory(fake.ctx, { ...SPEC, view: 'profil', elevation })

    const call = fake.calls.find((c) => c.op === 'fillText' && c.args[0] === '900 m')
    expect(call).toBeDefined()
    const x = Number(call?.args[1])
    // Texte centré : ses deux extrémités doivent rester dans la zone sûre (88 px de marge).
    expect(x - 50).toBeGreaterThanOrEqual(88)
    expect(x + 50).toBeLessThanOrEqual(1080 - 88)
  })

  it('n’affiche pas de visuel en vue stats', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, view: 'stats' })
    expect(fake.texts()).toContain('42 km')
    expect(fake.calls.some((c) => c.op === 'lineTo')).toBe(false)
  })

  it('dessine les métriques puis le tracé en vue stats-trace', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, view: 'stats-trace' })
    expect(fake.texts()).toContain('42 km')
    expect(fake.calls.some((c) => c.op === 'lineTo')).toBe(true)
  })

  it('retire titre et signature à la demande', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, showTitle: false, showBrand: false })
    const texts = fake.texts()
    expect(texts).not.toContain('VÉLO · MARDI 28 JUILLET 2026')
    expect(texts).not.toContain('Garmin Training Coach')
    expect(texts).toContain('42 km')
  })

  it('n’affiche que les métriques que le gabarit peut porter', () => {
    const fake = fakeContext(2)
    const many = [
      ...SPEC.metrics,
      { key: 'elevation', label: 'Dénivelé', value: '780 m' },
      { key: 'hr_avg', label: 'FC moyenne', value: '148 bpm' },
    ]
    renderActivityStory(fake.ctx, { ...SPEC, metrics: many })
    expect(fake.texts()).toContain('780 m')
    expect(fake.texts()).not.toContain('148 bpm')
  })

  it('reste silencieux quand le tracé est inexploitable', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, route: [] })
    expect(fake.calls.some((c) => c.op === 'lineTo')).toBe(false)
    expect(fake.texts()).toContain('VÉLO · MARDI 28 JUILLET 2026')
  })

  it('reste silencieux quand le profil est inexploitable', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, view: 'profil', elevation: [] })
    expect(fake.calls.some((c) => c.op === 'lineTo')).toBe(false)
  })

  it('rend une story sans métrique', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, metrics: [] })
    expect(fake.texts()).toContain('VÉLO · MARDI 28 JUILLET 2026')
  })

  it('rend le format carré', () => {
    const fake = fakeContext(2)
    renderActivityStory(fake.ctx, { ...SPEC, format: 'square', background: 'dark' })
    expect(
      fake.calls.some((c) => c.op === 'fillRect' && c.args[2] === 1080 && c.args[3] === 1080)
    ).toBe(true)
  })
})

describe('availableStoryViews', () => {
  it('propose tous les gabarits quand tout est disponible', () => {
    expect(availableStoryViews(ROUTE, ELEVATION)).toEqual([
      'trace',
      'stats-trace',
      'profil',
      'stats',
      'minimal',
    ])
  })

  it('ne propose que les stats sans GPS ni altitude', () => {
    expect(availableStoryViews([], [])).toEqual(['stats'])
  })

  it('propose le profil sans GPS (home-trainer avec altitude)', () => {
    expect(availableStoryViews([], ELEVATION)).toEqual(['profil', 'stats'])
  })

  it('met le gabarit multisport en tête quand les disciplines diffèrent', () => {
    expect(availableStoryViews(ROUTE, ELEVATION, SEGMENTS)[0]).toBe('disciplines')
  })

  it('ne le propose pas pour une activité d’une seule discipline', () => {
    expect(availableStoryViews(ROUTE, ELEVATION, [SWIM])).not.toContain('disciplines')
  })
})

describe('gabarit par discipline', () => {
  it('dessine une ligne par discipline plutôt qu\u2019un total agrégé', () => {
    const fake = fakeContext(2)

    renderActivityStory(fake.ctx, {
      ...SPEC,
      view: 'disciplines',
      title: 'Brick',
      segments: SEGMENTS,
    })

    const texts = fake.texts()
    expect(texts).toContain('Natation')
    expect(texts).toContain('Vélo')
    expect(texts).toContain('Course')
    expect(texts).toContain('5min · 1.5 km · 0:20 /100m')
  })

  it('colorie le tracé discipline par discipline', () => {
    const fake = fakeContext(2)

    renderActivityStory(fake.ctx, {
      ...SPEC,
      view: 'trace',
      route: MULTISPORT_ROUTE,
      segments: SEGMENTS,
    })

    // Trois tronçons, chacun doublé de son halo : six passes de trait au lieu
    // des deux d'un tracé monochrome.
    const strokes = fake.calls.filter((c) => c.op === 'stroke')
    expect(strokes.length).toBeGreaterThanOrEqual(6)
  })

  it('retombe sur un tracé d\u2019une seule couleur sans segment', () => {
    const fake = fakeContext(2)

    renderActivityStory(fake.ctx, { ...SPEC, view: 'trace', route: MULTISPORT_ROUTE })

    expect(fake.calls.filter((c) => c.op === 'stroke')).toHaveLength(2)
  })

  it('ne dessine aucune ligne quand les segments sont inexploitables', () => {
    const fake = fakeContext(2)

    renderActivityStory(fake.ctx, {
      ...SPEC,
      view: 'disciplines',
      segments: [{ ...SWIM, duration_s: null }],
    })

    expect(fake.texts()).not.toContain('Natation')
  })
})

describe('rendu défensif', () => {
  it('n’explose pas si une primitive canvas est absente', () => {
    const fake = fakeContext(2)
    const ctx = fake.ctx as unknown as Record<string, unknown>
    const spy = vi.spyOn(console, 'error').mockImplementation(() => undefined)
    ctx.measureText = undefined
    expect(() => {
      renderActivityStory(fake.ctx, SPEC)
    }).not.toThrow()
    spy.mockRestore()
  })
})
