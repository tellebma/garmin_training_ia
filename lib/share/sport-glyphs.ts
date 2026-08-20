/**
 * Pictogrammes de discipline dessinés au trait, pour le calque de partage.
 *
 * Les icônes React de l'app (`SportIcon`, lucide) ne sont pas réutilisables ici :
 * un canvas ne rend pas du JSX, et charger un SVG externe « tainterait » le canvas,
 * ce qui bloquerait `toBlob()` — la contrainte fondatrice du calque (E22). Ces
 * glyphes sont donc des `Path2D` autonomes, sans aucune ressource externe.
 *
 * Chaque glyphe est dessiné centré sur (cx, cy) et tient dans un carré de `size`.
 */

export type GlyphSport = 'swim' | 'bike' | 'run' | 'transition'

const STROKE_RATIO = 0.09

function isGlyphSport(sport: string): sport is GlyphSport {
  return sport === 'swim' || sport === 'bike' || sport === 'run' || sport === 'transition'
}

/** Vagues : trois ondulations superposées. */
function swimPath(cx: number, cy: number, size: number): Path2D {
  const path = new Path2D()
  const half = size / 2
  const step = size / 3
  for (let row = 0; row < 3; row++) {
    const y = cy - step + row * step
    path.moveTo(cx - half, y)
    path.bezierCurveTo(cx - half / 3, y - step / 2, cx + half / 3, y + step / 2, cx + half, y)
  }
  return path
}

/** Vélo : deux roues, un cadre triangulaire, un guidon. */
function bikePath(cx: number, cy: number, size: number): Path2D {
  const path = new Path2D()
  const radius = size * 0.22
  const wheelY = cy + size * 0.16
  const leftX = cx - size * 0.28
  const rightX = cx + size * 0.28
  path.moveTo(leftX + radius, wheelY)
  path.arc(leftX, wheelY, radius, 0, Math.PI * 2)
  path.moveTo(rightX + radius, wheelY)
  path.arc(rightX, wheelY, radius, 0, Math.PI * 2)
  // Cadre : pédalier → selle → guidon → roue arrière.
  path.moveTo(leftX, wheelY)
  path.lineTo(cx - size * 0.04, cy - size * 0.22)
  path.lineTo(cx + size * 0.18, cy - size * 0.22)
  path.lineTo(rightX, wheelY)
  path.moveTo(cx - size * 0.04, cy - size * 0.22)
  path.lineTo(cx + size * 0.06, wheelY)
  return path
}

/** Coureur : tête, buste, bras et jambes en pleine foulée. */
function runPath(cx: number, cy: number, size: number): Path2D {
  const path = new Path2D()
  const headRadius = size * 0.12
  const headY = cy - size * 0.32
  path.moveTo(cx + headRadius * 0.4, headY)
  path.arc(cx - headRadius * 0.6, headY, headRadius, 0, Math.PI * 2)
  // Buste incliné vers l'avant.
  path.moveTo(cx - size * 0.16, cy - size * 0.18)
  path.lineTo(cx + size * 0.06, cy + size * 0.04)
  // Bras.
  path.moveTo(cx - size * 0.12, cy - size * 0.12)
  path.lineTo(cx - size * 0.34, cy - size * 0.02)
  path.moveTo(cx - size * 0.04, cy - size * 0.06)
  path.lineTo(cx + size * 0.22, cy - size * 0.16)
  // Jambes.
  path.moveTo(cx + size * 0.06, cy + size * 0.04)
  path.lineTo(cx - size * 0.12, cy + size * 0.34)
  path.moveTo(cx + size * 0.06, cy + size * 0.04)
  path.lineTo(cx + size * 0.3, cy + size * 0.26)
  return path
}

/** Transition : deux chevrons, comme un passage d'une discipline à l'autre. */
function transitionPath(cx: number, cy: number, size: number): Path2D {
  const path = new Path2D()
  const width = size * 0.2
  for (const offset of [-size * 0.16, size * 0.16]) {
    path.moveTo(cx + offset - width / 2, cy - size * 0.24)
    path.lineTo(cx + offset + width / 2, cy)
    path.lineTo(cx + offset - width / 2, cy + size * 0.24)
  }
  return path
}

const GLYPHS: Record<GlyphSport, (cx: number, cy: number, size: number) => Path2D> = {
  swim: swimPath,
  bike: bikePath,
  run: runPath,
  transition: transitionPath,
}

/**
 * Dessine le pictogramme d'une discipline, halo sombre compris pour rester lisible
 * sur une photo claire. Un sport sans pictogramme n'est simplement pas dessiné.
 */
export function drawSportGlyph(
  ctx: CanvasRenderingContext2D,
  sport: string,
  cx: number,
  cy: number,
  size: number,
  color: string
): void {
  if (!isGlyphSport(sport) || typeof Path2D === 'undefined') return
  const path = GLYPHS[sport](cx, cy, size)
  ctx.save()
  ctx.lineCap = 'round'
  ctx.lineJoin = 'round'
  ctx.strokeStyle = 'rgba(2,6,23,0.55)'
  ctx.lineWidth = size * STROKE_RATIO * 2
  ctx.stroke(path)
  ctx.strokeStyle = color
  ctx.lineWidth = size * STROKE_RATIO
  ctx.stroke(path)
  ctx.restore()
}
