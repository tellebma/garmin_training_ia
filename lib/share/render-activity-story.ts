import { drawSportGlyph } from './sport-glyphs'
import {
  buildStorySegmentLines,
  hasDistinctDisciplines,
  sliceRouteBySegments,
  type StorySegment,
  type StorySegmentLine,
} from './story-segments'
import {
  buildElevationProfile,
  computeStoryLayout,
  metricsCapForView,
  projectRoute,
  STORY_SIZES,
  type Box,
  type ElevationProfile,
  type ProjectedRoute,
  type StoryBackground,
  type StoryBlockKind,
  type StoryFormat,
  type StoryElevationPoint,
  type StoryLayout,
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
  /**
   * Segments d'un multisport, dans l'ordre de l'épreuve. Vide pour une activité
   * simple : le gabarit « disciplines » disparaît et le tracé reste monochrome.
   */
  readonly segments?: readonly StorySegment[]
  readonly route: readonly StoryPoint[]
  readonly elevation: readonly StoryElevationPoint[]
  readonly brand: string
  /** Ligne « sport · date » au-dessus du sticker (défaut : affichée). */
  readonly showTitle?: boolean
  /** Signature en bas du sticker (défaut : affichée). */
  readonly showBrand?: boolean
  /** Pictogrammes de discipline devant chaque ligne (défaut : affichés). */
  readonly showSportIcons?: boolean
}

const FONT_STACK = "system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
const WHITE = '#ffffff'
const MUTED = 'rgba(255,255,255,0.82)'
const FAINT = 'rgba(255,255,255,0.62)'
const DARK_HALO = 'rgba(2,6,23,0.55)'
const DARK_BG = '#080d1a'

const TEXT_SHADOW_BLUR = 26
const TEXT_SHADOW_OFFSET = 3
const MIN_FONT_SIZE = 22

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

/**
 * Réduit la taille de police jusqu'à ce que le texte tienne dans `maxWidth`.
 * Sans cela « 2:03 /100m » déborde de sa colonne dans la ligne de métriques.
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

/** Largeur moyenne d'un caractère, quand `measureText` n'est pas exploitable. */
const FALLBACK_CHAR_RATIO = 0.6

function measureTextWidth(
  ctx: CanvasRenderingContext2D,
  text: string,
  weight: string,
  sizePx: number
): number {
  if (typeof ctx.measureText !== 'function') return text.length * sizePx * FALLBACK_CHAR_RATIO
  ctx.font = `${weight} ${String(sizePx)}px ${FONT_STACK}`
  const width = ctx.measureText(text).width
  return Number.isFinite(width) ? width : text.length * sizePx * FALLBACK_CHAR_RATIO
}

function clamp(value: number, min: number, max: number): number {
  if (min > max) return (min + max) / 2
  return Math.min(max, Math.max(min, value))
}

interface TextOptions {
  readonly font: string
  readonly color: string
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
  ctx.textAlign = 'center'
  ctx.textBaseline = 'top'
  // Le calque est posé sur une photo inconnue : l'ombre garantit la lisibilité.
  ctx.shadowColor = 'rgba(0,0,0,0.55)'
  ctx.shadowBlur = TEXT_SHADOW_BLUR
  ctx.shadowOffsetY = TEXT_SHADOW_OFFSET
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

function centerX(box: Box): number {
  return box.x + box.width / 2
}

function drawTitle(ctx: CanvasRenderingContext2D, box: Box, spec: StorySpec, scale: number): void {
  const text = `${spec.title} · ${spec.subtitle}`.toUpperCase()
  const size = fitFontSize(ctx, text, '600', 36 * scale, box.width)
  drawText(ctx, text, centerX(box), box.y, { font: `600 ${String(size)}px`, color: MUTED })
}

function drawBrand(ctx: CanvasRenderingContext2D, box: Box, spec: StorySpec, scale: number): void {
  const size = fitFontSize(ctx, spec.brand, '500', 32 * scale, box.width)
  drawText(ctx, spec.brand, centerX(box), box.y, { font: `500 ${String(size)}px`, color: FAINT })
}

/** Police commune à toutes les valeurs : des tailles différentes rendraient la pile bancale. */
function commonValueSize(
  ctx: CanvasRenderingContext2D,
  metrics: readonly StoryMetric[],
  base: number,
  maxWidth: number
): number {
  return metrics.reduce(
    (smallest, metric) => Math.min(smallest, fitFontSize(ctx, metric.value, '700', base, maxWidth)),
    base
  )
}

function drawMetricsRow(
  ctx: CanvasRenderingContext2D,
  box: Box,
  metrics: readonly StoryMetric[],
  scale: number
): void {
  const cellWidth = box.width / metrics.length
  const labelSize = 34 * scale
  const valueSize = commonValueSize(ctx, metrics, 84 * scale, cellWidth - 40 * scale)
  metrics.forEach((metric, index) => {
    const x = box.x + cellWidth * (index + 0.5)
    drawText(ctx, metric.label, x, box.y, { font: `600 ${String(labelSize)}px`, color: MUTED })
    drawText(ctx, metric.value, x, box.y + labelSize + 18 * scale, {
      font: `700 ${String(valueSize)}px`,
      color: WHITE,
    })
  })
}

function drawMetricsStack(
  ctx: CanvasRenderingContext2D,
  box: Box,
  metrics: readonly StoryMetric[],
  scale: number
): void {
  const lineHeight = box.height / metrics.length
  const labelSize = 36 * scale
  const valueSize = commonValueSize(ctx, metrics, 96 * scale, box.width)
  const x = centerX(box)
  metrics.forEach((metric, index) => {
    const y = box.y + lineHeight * index
    drawText(ctx, metric.label, x, y, { font: `600 ${String(labelSize)}px`, color: MUTED })
    drawText(ctx, metric.value, x, y + labelSize + 10 * scale, {
      font: `700 ${String(valueSize)}px`,
      color: WHITE,
    })
  })
}

/**
 * Une ligne par discipline : pictogramme + nom dans la teinte de la discipline,
 * puis ses métriques en gros. C'est ce bloc qui rend les trois efforts d'un
 * triathlon distinguables, là où le calque n'affichait qu'un total agrégé.
 */
function drawSegments(
  ctx: CanvasRenderingContext2D,
  box: Box,
  lines: readonly StorySegmentLine[],
  spec: StorySpec,
  scale: number
): void {
  const lineHeight = box.height / lines.length
  const labelSize = 34 * scale
  const valueSize = commonValueSize(ctx, lines, 64 * scale, box.width)
  const glyphSize = labelSize * 1.5
  const x = centerX(box)

  lines.forEach((line, index) => {
    const y = box.y + lineHeight * index
    if (spec.showSportIcons !== false) {
      // Le pictogramme se pose à gauche du libellé, l'ensemble restant centré.
      // Une discipline sans pictogramme (sport inconnu) garde son libellé seul.
      const labelWidth = measureTextWidth(ctx, line.label, '600', labelSize)
      drawSportGlyph(
        ctx,
        line.sport,
        x - labelWidth / 2 - glyphSize * 0.75,
        y + labelSize / 2,
        glyphSize,
        line.color
      )
    }
    drawText(ctx, line.label, x, y, { font: `600 ${String(labelSize)}px`, color: line.color })
    drawText(ctx, line.value, x, y + labelSize + 14 * scale, {
      font: `700 ${String(valueSize)}px`,
      color: WHITE,
    })
  })
}

function tracePath(ctx: CanvasRenderingContext2D, points: ProjectedRoute['points']): void {
  ctx.beginPath()
  points.forEach(([x, y], index) => {
    if (index === 0) ctx.moveTo(x, y)
    else ctx.lineTo(x, y)
  })
}

/** Trait d'accent doublé d'un halo sombre : lisible aussi bien sur ciel que sur bitume. */
function strokeWithHalo(
  ctx: CanvasRenderingContext2D,
  points: ProjectedRoute['points'],
  accent: string,
  lineWidth: number
): void {
  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.strokeStyle = DARK_HALO
  ctx.lineWidth = lineWidth * 2
  tracePath(ctx, points)
  ctx.stroke()
  ctx.strokeStyle = accent
  ctx.lineWidth = lineWidth
  tracePath(ctx, points)
  ctx.stroke()
  ctx.restore()
}

/**
 * Tracé de l'activité. Sur un multisport, chaque discipline prend sa teinte —
 * on lit la nage, le vélo et la course sur une seule trace. Le découpage repose
 * sur le temps écoulé des points ; s'il n'est pas fiable, le tracé retombe sur
 * la couleur d'accent, d'un seul tenant.
 */
function drawRoute(
  ctx: CanvasRenderingContext2D,
  route: ProjectedRoute,
  spec: StorySpec,
  lineWidth: number
): void {
  const slices = sliceRouteBySegments(route, spec.segments ?? [])
  if (slices.length === 0) {
    strokeWithHalo(ctx, route.points, spec.accent, lineWidth)
    return
  }
  for (const slice of slices) {
    strokeWithHalo(ctx, slice.points, slice.color, lineWidth)
  }
}

function drawElevation(
  ctx: CanvasRenderingContext2D,
  profile: ElevationProfile,
  box: Box,
  spec: StorySpec,
  scale: number
): void {
  const { points, baselineY } = profile
  const first = points[0]
  const last = points.at(-1)
  if (!first || !last) return

  ctx.save()
  const gradient = ctx.createLinearGradient(0, box.y, 0, baselineY)
  gradient.addColorStop(0, withAlpha(spec.accent, 0.6))
  gradient.addColorStop(1, withAlpha(spec.accent, 0.04))
  ctx.beginPath()
  ctx.moveTo(first[0], baselineY)
  for (const [x, y] of points) ctx.lineTo(x, y)
  ctx.lineTo(last[0], baselineY)
  ctx.closePath()
  ctx.fillStyle = gradient
  ctx.fill()
  ctx.restore()

  strokeWithHalo(ctx, points, spec.accent, 10 * scale)

  // Le sommet peut tomber sur le tout premier ou le tout dernier point (montée ou
  // descente pure) : sans recentrage, l'annotation déborde de la zone sûre du calque.
  const label = `${String(Math.round(profile.maxElevation))} m`
  const size = 32 * scale
  const half = Math.min(measureTextWidth(ctx, label, '600', size), box.width) / 2
  const x = clamp(profile.peak[0], box.x + half, box.x + box.width - half)
  drawText(ctx, label, x, Math.max(0, profile.peak[1] - 52 * scale), {
    font: `600 ${String(size)}px`,
    color: WHITE,
  })
}

/**
 * `kind` est typé `StoryBlockKind` (et non `string`) pour que l'ajout d'un futur bloc
 * casse la compilation ici plutôt que de ne rien dessiner en silence.
 */
function drawBlock(
  ctx: CanvasRenderingContext2D,
  kind: StoryBlockKind,
  box: Box,
  spec: StorySpec,
  scale: number,
  metrics: readonly StoryMetric[]
): void {
  switch (kind) {
    case 'title':
      drawTitle(ctx, box, spec, scale)
      return
    case 'brand':
      drawBrand(ctx, box, spec, scale)
      return
    case 'metricsRow':
      if (metrics.length > 0) drawMetricsRow(ctx, box, metrics, scale)
      return
    case 'metricsStack':
      if (metrics.length > 0) drawMetricsStack(ctx, box, metrics, scale)
      return
    case 'route': {
      const route = projectRoute(spec.route, box)
      if (route) drawRoute(ctx, route, spec, 16 * scale)
      return
    }
    case 'segments': {
      const lines = buildStorySegmentLines(spec.segments ?? [])
      if (lines.length > 0) drawSegments(ctx, box, lines, spec, scale)
      return
    }
    case 'elevation': {
      const profile = buildElevationProfile(spec.elevation, box)
      if (profile) drawElevation(ctx, profile, box, spec, scale)
      return
    }
  }
}

function drawBlocks(ctx: CanvasRenderingContext2D, layout: StoryLayout, spec: StorySpec): void {
  const metrics = spec.metrics.slice(0, metricsCapForView(spec.view))
  for (const { kind, box } of layout.blocks) {
    drawBlock(ctx, kind, box, spec, layout.scale, metrics)
  }
}

/**
 * Dessine le calque d'activité dans un contexte 2D de taille `STORY_SIZES[format]`.
 * Le rendu est entièrement vectoriel : aucune tuile externe, donc pas de canvas
 * « tainted » et `toBlob()` reste utilisable pour l'export PNG.
 */
export function renderActivityStory(ctx: CanvasRenderingContext2D, spec: StorySpec): void {
  const layout = computeStoryLayout(spec.view, spec.format, spec.metrics.length, {
    segmentCount: buildStorySegmentLines(spec.segments ?? []).length,
    // `exactOptionalPropertyTypes` : ne transmettre les options que si elles sont définies.
    ...(spec.showTitle === undefined ? {} : { showTitle: spec.showTitle }),
    ...(spec.showBrand === undefined ? {} : { showBrand: spec.showBrand }),
  })
  drawBackground(ctx, spec)
  drawBlocks(ctx, layout, spec)
}

/** Gabarits proposables selon les données réellement disponibles pour l'activité. */
export function availableStoryViews(
  route: readonly StoryPoint[],
  elevation: readonly StoryElevationPoint[],
  segments: readonly StorySegment[] = []
): StoryView[] {
  const probe: Box = { x: 0, y: 0, width: 100, height: 100 }
  const hasRoute = projectRoute(route, probe) !== null
  const hasElevation = buildElevationProfile(elevation, probe) !== null
  const views: StoryView[] = []
  // Le gabarit multisport passe devant : sur un triathlon, c'est la vue qui dit
  // quelque chose — les autres agrègent trois efforts en une moyenne.
  if (hasDistinctDisciplines(segments) && buildStorySegmentLines(segments).length > 0) {
    views.push('disciplines')
  }
  if (hasRoute) views.push('trace', 'stats-trace')
  if (hasElevation) views.push('profil')
  views.push('stats')
  if (hasRoute) views.push('minimal')
  return views
}
