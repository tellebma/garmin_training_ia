import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { drawSportGlyph } from '@/lib/share/sport-glyphs'

interface FakePath {
  readonly ops: string[]
}

const paths: FakePath[] = []

class FakePath2D implements FakePath {
  readonly ops: string[] = []
  constructor() {
    paths.push(this)
  }
  moveTo() {
    this.ops.push('moveTo')
  }
  lineTo() {
    this.ops.push('lineTo')
  }
  arc() {
    this.ops.push('arc')
  }
  bezierCurveTo() {
    this.ops.push('bezierCurveTo')
  }
}

interface FakeCtx {
  readonly ctx: CanvasRenderingContext2D
  readonly strokes: unknown[]
  readonly colors: string[]
}

function fakeContext(): FakeCtx {
  const strokes: unknown[] = []
  const colors: string[] = []
  const target = {
    save: () => undefined,
    restore: () => undefined,
    stroke: (path: unknown) => {
      strokes.push(path)
      colors.push(String(target.strokeStyle))
    },
    strokeStyle: '' as unknown,
    lineWidth: 0,
    lineCap: 'butt',
    lineJoin: 'miter',
  }
  return { ctx: target as unknown as CanvasRenderingContext2D, strokes, colors }
}

beforeEach(() => {
  paths.length = 0
  ;(globalThis as { Path2D?: unknown }).Path2D = FakePath2D
})

afterEach(() => {
  delete (globalThis as { Path2D?: unknown }).Path2D
})

describe('drawSportGlyph', () => {
  it.each(['swim', 'bike', 'run', 'transition'])('dessine le pictogramme %s', (sport) => {
    const { ctx, strokes, colors } = fakeContext()

    drawSportGlyph(ctx, sport, 100, 100, 40, '#38bdf8')

    // Deux passes : halo sombre puis la teinte de la discipline — le calque est
    // posé sur une photo inconnue, un trait simple s'y perdrait.
    expect(strokes).toHaveLength(2)
    expect(colors[1]).toBe('#38bdf8')
    expect(paths[0]?.ops.length).toBeGreaterThan(0)
  })

  it('ne dessine rien pour un sport sans pictogramme', () => {
    const { ctx, strokes } = fakeContext()

    drawSportGlyph(ctx, 'kayaking', 100, 100, 40, '#ffffff')

    expect(strokes).toEqual([])
  })

  it('ne dessine rien là où Path2D n’existe pas', () => {
    // jsdom, et tout contexte de rendu serveur : le calque doit rester silencieux
    // plutôt que de casser la page.
    delete (globalThis as { Path2D?: unknown }).Path2D
    const { ctx, strokes } = fakeContext()

    drawSportGlyph(ctx, 'run', 100, 100, 40, '#ffffff')

    expect(strokes).toEqual([])
  })
})
