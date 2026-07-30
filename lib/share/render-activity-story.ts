import {
  buildElevationProfile,
  computeStoryLayout,
  projectRoute,
  STORY_SIZES,
  type Box,
  type ElevationProfile,
  type ProjectedRoute,
  type StoryBackground,
  type StoryFormat,
  type StoryElevationPoint,
  type StoryMetric,
  type StoryPoint,
  type StoryView,
} from './story-layout'

export interface StorySpec {
  readonly view: StoryView
  readonly format: StoryFormat
  readonly background: StoryBackground
  readonly accent: string
  /** Titre principal, ex. « Course à pied ». */
  readonly title: string
  /** Sous-titre, ex. « mercredi 30 juillet 2026 ». */
  readonly subtitle: string
  readonly metrics: readonly StoryMetric[]
  readonly route: readonly StoryPoint[]
  readonly elevation: readonly StoryElevationPoint[]
  readonly brand: string
}

const FONT_STACK = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
const WHITE = '#ffffff'
const MUTED = 'rgba(255,255,255,0.72)'
const FAINT = 'rgba(255,255,255,0.7)'
const DARK_HALO = 'rgba(2,6,23,0.6)'
const DARK_BG = '#080d1a'

const TEXT_SHADOW_BLUR = 24
const TEXT_SHADOW_OFFSET = 3

function hexChannels(color: string): string[] | null {
  const long = /^#([\da-f]{2})([\da-f]{2})([\da-f]{2})$/i.exec(color)
  if (long) return [long[1] ?? '', long[2] ?? '', long[3] ?? '']
  const short = /^#([\da-f])([\da-f])([\da-f])$/i.exec(color)
  if (short) return [short[1] ?? '', short[2] ?? '', short[3] ?? ''].map((c) => c + c)
  return null
}

/** Convertit `#rrggbb` (ou `#rgb`) en `rgba(...)`. Toute autre valeur est renvoyée telle quelle. */
export function withAlpha(color: string, alpha: number): string {
  const parts = hexChannels(color)
  if (!parts) return color
  const [r = 0, g = 0, b = 0] = parts.map((part) => Number.parseInt(part, 16))
  return `rgba(${String(r)},${String(g)},${String(b)},${String(alpha)})`
}

interface TextOptions {
  readonly font: string
  readonly color: string
  readonly align?: CanvasTextAlign
  readonly baseline?: CanvasTextBaseline
  readonly shadow?: boolean
}

const MIN_FONT_SIZE = 26

/**
 * Réduit la taille de police jusqu'à ce que le texte tienne dans `maxWidth`.
 * Sans cela « 26.2 km/h » déborde sur la colonne voisine dans la vue « métriques seules ».
 */
export function fitFontSize(
  ctx: CanvasRenderingContext2D,
  text: string,
  weight: string,
  sizePx: number,
  maxWidth: number
): number {
  if (typeof ctx.measureText !== 'function' || maxWidth <= 0) return sizePx
  let size = sizePx
  while (size > MIN_FONT_SIZE) {
    ctx.font = `${weight} ${String(size)}px ${FONT_STACK}`
    const width = ctx.measureText(text).width
    if (!Number.isFinite(width) || width <= maxWidth) break
    size -= 2
  }
  return size
}

function drawText(
  ctx: CanvasRenderingContext2D,
  text: string,
  x: number,
  y: number,
  options: TextOptions
): void {
  ctx.save()
  ctx.font = `${options.font} ${FONT_STACK}`
  ctx.fillStyle = options.color
  ctx.textAlign = options.align ?? 'left'
  ctx.textBaseline = options.baseline ?? 'top'
  if (options.shadow !== false) {
    // Le calque est posé sur une photo inconnue : l'ombre garantit la lisibilité.
    ctx.shadowColor = 'rgba(0,0,0,0.55)'
    ctx.shadowBlur = TEXT_SHADOW_BLUR
    ctx.shadowOffsetY = TEXT_SHADOW_OFFSET
  }
  ctx.fillText(text, x, y)
  ctx.restore()
}

function drawBackground(ctx: CanvasRenderingContext2D, spec: StorySpec): void {
  const { width, height } = STORY_SIZES[spec.format]
  ctx.clearRect(0, 0, width, height)
  if (spec.background === 'transparent') return

  ctx.save()
  if (spec.background === 'dark') {
    ctx.fillStyle = DARK_BG
  } else {
    const gradient = ctx.createLinearGradient(0, 0, 0, height)
    gradient.addColorStop(0, 'rgba(8,13,26,0)')
    gradient.addColorStop(0.45, 'rgba(8,13,26,0.4)')
    gradient.addColorStop(1, 'rgba(8,13,26,0.94)')
    ctx.fillStyle = gradient
  }
  ctx.fillRect(0, 0, width, height)
  ctx.restore()
}

function drawHeader(ctx: CanvasRenderingContext2D, box: Box, spec: StorySpec): void {
  ctx.save()
  ctx.fillStyle = spec.accent
  ctx.fillRect(box.x, box.y, 104, 10)
  ctx.restore()

  drawText(ctx, spec.subtitle.toUpperCase(), box.x, box.y + 34, {
    font: '600 32px',
    color: MUTED,
  })
  const titleSize = fitFontSize(ctx, spec.title, '700', 76, box.width)
  drawText(ctx, spec.title, box.x, box.y + 80, {
    font: `700 ${String(titleSize)}px`,
    color: WHITE,
  })
}

function drawBrand(ctx: CanvasRenderingContext2D, box: Box, spec: StorySpec): void {
  ctx.save()
  ctx.fillStyle = spec.accent
  ctx.beginPath()
  ctx.arc(box.x + 9, box.y + 22, 9, 0, Math.PI * 2)
  ctx.fill()
  ctx.restore()
  drawText(ctx, spec.brand, box.x + 34, box.y + 6, { font: '500 30px', color: FAINT })
}

function drawMetricGrid(
  ctx: CanvasRenderingContext2D,
  box: Box,
  columns: number,
  large: boolean,
  spec: StorySpec
): void {
  const cellWidth = box.width / columns
  const rowHeight = box.height / Math.max(1, Math.ceil(spec.metrics.length / columns))
  const gutter = large ? 72 : 44
  const baseSize = large ? 92 : 64
  // Une taille commune à toute la grille : des valeurs de tailles différentes
  // côte à côte donneraient une grille bancale.
  const size = spec.metrics.reduce(
    (smallest, metric) =>
      Math.min(smallest, fitFontSize(ctx, metric.value, '700', baseSize, cellWidth - gutter)),
    baseSize
  )
  spec.metrics.forEach((metric, index) => {
    const x = box.x + (index % columns) * cellWidth
    const y = box.y + Math.floor(index / columns) * rowHeight
    ctx.save()
    ctx.fillStyle = spec.accent
    ctx.fillRect(x, y, 44, 6)
    ctx.restore()
    drawText(ctx, metric.label.toUpperCase(), x, y + 24, { font: '600 28px', color: MUTED })
    drawText(ctx, metric.value, x, y + 62, { font: `700 ${String(size)}px`, color: WHITE })
  })
}

function tracePath(ctx: CanvasRenderingContext2D, points: ProjectedRoute['points']): void {
  ctx.beginPath()
  points.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
}

function drawMarker(
  ctx: CanvasRenderingContext2D,
  point: readonly [number, number],
  radius: number,
  fill: string,
  ring: string
): void {
  ctx.save()
  ctx.beginPath()
  ctx.arc(point[0], point[1], radius, 0, Math.PI * 2)
  ctx.fillStyle = fill
  ctx.fill()
  ctx.lineWidth = 6
  ctx.strokeStyle = ring
  ctx.stroke()
  ctx.restore()
}

function drawRoute(ctx: CanvasRenderingContext2D, route: ProjectedRoute, spec: StorySpec): void {
  const { points } = route
  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  // Halo sombre sous le tracé : le calque reste lisible sur une photo claire.
  ctx.strokeStyle = DARK_HALO
  ctx.lineWidth = 28
  tracePath(ctx, points)
  ctx.stroke()
  ctx.strokeStyle = spec.accent
  ctx.lineWidth = 14
  tracePath(ctx, points)
  ctx.stroke()
  ctx.restore()

  const start = points[0]
  const end = points.at(-1)
  if (start) drawMarker(ctx, start, 16, WHITE, DARK_HALO)
  if (end) drawMarker(ctx, end, 18, spec.accent, WHITE)
}

function drawElevation(
  ctx: CanvasRenderingContext2D,
  profile: ElevationProfile,
  box: Box,
  spec: StorySpec
): void {
  const { points, baselineY } = profile
  const first = points[0]
  const last = points.at(-1)
  if (!first || !last) return

  ctx.save()
  const gradient = ctx.createLinearGradient(0, box.y, 0, baselineY)
  gradient.addColorStop(0, withAlpha(spec.accent, 0.65))
  gradient.addColorStop(1, withAlpha(spec.accent, 0.05))
  ctx.beginPath()
  ctx.moveTo(first[0], baselineY)
  for (const [x, y] of points) ctx.lineTo(x, y)
  ctx.lineTo(last[0], baselineY)
  ctx.closePath()
  ctx.fillStyle = gradient
  ctx.fill()
  ctx.restore()

  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.strokeStyle = DARK_HALO
  ctx.lineWidth = 18
  tracePath(ctx, points)
  ctx.stroke()
  ctx.strokeStyle = spec.accent
  ctx.lineWidth = 9
  tracePath(ctx, points)
  ctx.stroke()
  ctx.restore()

  drawText(
    ctx,
    `${String(Math.round(profile.maxElevation))} m`,
    profile.peak[0],
    profile.peak[1] - 44,
    { font: '600 30px', color: WHITE, align: 'center' }
  )
}

function drawVisual(ctx: CanvasRenderingContext2D, box: Box, spec: StorySpec): void {
  if (spec.view === 'profil') {
    const profile = buildElevationProfile(spec.elevation, box)
    if (profile) drawElevation(ctx, profile, box, spec)
    return
  }
  const route = projectRoute(spec.route, box)
  if (route) drawRoute(ctx, route, spec)
}

/**
 * Dessine le calque d'activité dans un contexte 2D de taille `STORY_SIZES[format]`.
 * Le rendu est entièrement vectoriel : aucune tuile externe, donc pas de canvas
 * « tainted » et `toBlob()` reste utilisable pour l'export PNG.
 */
export function renderActivityStory(ctx: CanvasRenderingContext2D, spec: StorySpec): void {
  const layout = computeStoryLayout(spec.view, spec.format, spec.metrics.length)
  drawBackground(ctx, spec)
  if (layout.header) drawHeader(ctx, layout.header, spec)
  if (layout.visual) drawVisual(ctx, layout.visual, spec)
  if (layout.metrics && layout.columns > 0) {
    drawMetricGrid(ctx, layout.metrics, layout.columns, layout.large, spec)
  }
  if (layout.brand) drawBrand(ctx, layout.brand, spec)
}

/** Gabarits proposables selon les données réellement disponibles pour l'activité. */
export function availableStoryViews(
  route: readonly StoryPoint[],
  elevation: readonly StoryElevationPoint[]
): StoryView[] {
  const views: StoryView[] = []
  const hasRoute = projectRoute(route, { x: 0, y: 0, width: 100, height: 100 }) !== null
  const hasElevation =
    buildElevationProfile(elevation, { x: 0, y: 0, width: 100, height: 100 }) !== null
  if (hasRoute) views.push('trace')
  if (hasElevation) views.push('profil')
  views.push('stats')
  if (hasRoute) views.push('minimal')
  return views
}
