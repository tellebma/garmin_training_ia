'use client'

import { useCallback, useEffect, useMemo, useRef, useState, useSyncExternalStore } from 'react'
import { Download, Share2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { canSharePng, canvasToPngBlob, downloadBlob, sharePng } from '@/lib/share/export-png'
import { availableStoryViews, renderActivityStory } from '@/lib/share/render-activity-story'
import {
  buildStoryMetrics,
  defaultMetricKeys,
  metricsCapForView,
  STORY_ACCENTS,
  STORY_BACKGROUND_LABELS,
  STORY_FORMAT_LABELS,
  STORY_SIZES,
  STORY_VIEW_LABELS,
  storyFileName,
  type StoryActivity,
  type StoryBackground,
  type StoryElevationPoint,
  type StoryFormat,
  type StoryPoint,
  type StoryView,
} from '@/lib/share/story-layout'
import type { Sport } from '@/lib/dashboard/types'
import { cn } from '@/lib/utils'

const BRAND = 'Garmin Training Coach'

// Damier CSS : rend la transparence du calque visible dans l'aperçu.
const CHECKERBOARD =
  'repeating-conic-gradient(rgba(255,255,255,0.09) 0% 25%, rgba(255,255,255,0.02) 0% 50%) 50% / 24px 24px'

const FORMATS: readonly StoryFormat[] = ['story', 'square']
const BACKGROUNDS: readonly StoryBackground[] = ['transparent', 'gradient', 'dark']

interface ActivityStoryExportProps {
  readonly activity: StoryActivity
  readonly sport: Sport
  readonly sportLabel: string
  readonly route: readonly StoryPoint[]
  readonly elevation: readonly StoryElevationPoint[]
}

type Feedback = { readonly tone: 'ok' | 'muted'; readonly text: string } | null

// La capacité de partage ne change pas au cours de la vie de la page : pas d'abonnement.
const subscribeNever = () => () => {
  /* no-op */
}
const serverFalse = () => false

function OptionChip({
  active,
  onClick,
  children,
  swatch,
}: {
  readonly active: boolean
  readonly onClick: () => void
  readonly children: React.ReactNode
  readonly swatch?: string
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors',
        active
          ? 'border-primary bg-primary/15 text-foreground'
          : 'border-border text-muted-foreground hover:text-foreground'
      )}
    >
      {swatch && (
        <span
          className="size-3 rounded-full border border-white/30"
          style={{ backgroundColor: swatch }}
        />
      )}
      {children}
    </button>
  )
}

function OptionRow({
  label,
  children,
}: {
  readonly label: string
  readonly children: React.ReactNode
}) {
  return (
    <div>
      <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{label}</p>
      <div className="mt-2 flex flex-wrap gap-2">{children}</div>
    </div>
  )
}

export function ActivityStoryExport({
  activity,
  sport,
  sportLabel,
  route,
  elevation,
}: ActivityStoryExportProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const views = useMemo(() => availableStoryViews(route, elevation), [route, elevation])
  const allMetrics = useMemo(() => buildStoryMetrics(activity, sport), [activity, sport])

  const initialView: StoryView = views[0] ?? 'stats'
  const [view, setView] = useState<StoryView>(initialView)
  const [format, setFormat] = useState<StoryFormat>('story')
  const [background, setBackground] = useState<StoryBackground>('transparent')
  const [accent, setAccent] = useState<string>(STORY_ACCENTS[0]?.color ?? '#22d3ee')
  const [metricKeys, setMetricKeys] = useState<string[]>(() =>
    defaultMetricKeys(allMetrics, metricsCapForView(initialView))
  )
  const [showTitle, setShowTitle] = useState(true)
  const [showBrand, setShowBrand] = useState(true)
  const [busy, setBusy] = useState(false)
  const [feedback, setFeedback] = useState<Feedback>(null)

  // Capacité navigateur (Web Share niveau 2) : lue après hydratation, `false` côté serveur.
  const shareable = useSyncExternalStore(subscribeNever, canSharePng, serverFalse)

  const metricsCap = metricsCapForView(view)
  const metrics = useMemo(
    () => allMetrics.filter((metric) => metricKeys.includes(metric.key)),
    [allMetrics, metricKeys]
  )

  // Chaque gabarit porte un nombre différent de métriques : on ramène la sélection
  // sous le plafond au changement de vue, pour qu'une puce active soit toujours
  // une puce réellement dessinée.
  const selectView = useCallback((next: StoryView) => {
    setView(next)
    const cap = metricsCapForView(next)
    setMetricKeys((current) => (current.length > cap ? current.slice(0, cap) : current))
  }, [])

  const subtitle = useMemo(
    () =>
      new Date(activity.start_time).toLocaleDateString('fr-FR', {
        weekday: 'long',
        day: 'numeric',
        month: 'long',
        year: 'numeric',
      }),
    [activity.start_time]
  )

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const size = STORY_SIZES[format]
    canvas.width = size.width
    canvas.height = size.height
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    renderActivityStory(ctx, {
      view,
      format,
      background,
      accent,
      title: sportLabel,
      subtitle,
      metrics,
      route,
      elevation,
      brand: BRAND,
      showTitle,
      showBrand,
    })
  }, [
    view,
    format,
    background,
    accent,
    sportLabel,
    subtitle,
    metrics,
    route,
    elevation,
    showTitle,
    showBrand,
  ])

  const toggleMetric = useCallback(
    (key: string) => {
      setMetricKeys((current) => {
        if (current.includes(key)) return current.filter((item) => item !== key)
        if (current.length >= metricsCap) return current
        return [...current, key]
      })
    },
    [metricsCap]
  )

  const exportBlob = useCallback(async () => {
    const canvas = canvasRef.current
    if (!canvas) return null
    return canvasToPngBlob(canvas)
  }, [])

  const onDownload = useCallback(async () => {
    setBusy(true)
    setFeedback(null)
    try {
      const blob = await exportBlob()
      if (!blob) {
        setFeedback({ tone: 'muted', text: "L'image n'a pas pu être générée." })
        return
      }
      downloadBlob(blob, storyFileName(activity, view))
      setFeedback({ tone: 'ok', text: 'PNG téléchargé.' })
    } finally {
      setBusy(false)
    }
  }, [activity, exportBlob, view])

  const onShare = useCallback(async () => {
    setBusy(true)
    setFeedback(null)
    try {
      const blob = await exportBlob()
      if (!blob) {
        setFeedback({ tone: 'muted', text: "L'image n'a pas pu être générée." })
        return
      }
      const fileName = storyFileName(activity, view)
      const result = await sharePng(blob, fileName, `${sportLabel} — ${subtitle}`)
      if (result === 'shared') setFeedback({ tone: 'ok', text: 'Image envoyée au partage.' })
      else if (result === 'cancelled') setFeedback(null)
      else {
        downloadBlob(blob, fileName)
        setFeedback({ tone: 'muted', text: 'Partage indisponible : PNG téléchargé à la place.' })
      }
    } finally {
      setBusy(false)
    }
  }, [activity, exportBlob, sportLabel, subtitle, view])

  const previewClass = format === 'story' ? 'w-[220px]' : 'w-[260px]'

  return (
    <section className="bg-card rounded-lg border p-4">
      <header className="mb-4">
        <h2 className="text-foreground text-base font-semibold">Partager en story</h2>
        <p className="text-muted-foreground mt-0.5 text-xs">
          Un sticker PNG à fond transparent avec ta trace et tes métriques, à superposer sur ta
          photo dans Instagram, WhatsApp ou Snapchat.
        </p>
      </header>

      <div className="flex flex-col gap-6 lg:flex-row">
        <div className="flex justify-center lg:justify-start">
          <div
            className={cn('overflow-hidden rounded-lg border', previewClass)}
            style={{ background: CHECKERBOARD }}
          >
            <canvas
              ref={canvasRef}
              className="block h-auto w-full"
              aria-label={`Aperçu du calque ${STORY_VIEW_LABELS[view]} pour ${sportLabel}`}
            />
          </div>
        </div>

        <div className="flex-1 space-y-4">
          <OptionRow label="Vue">
            {views.map((item) => (
              <OptionChip
                key={item}
                active={item === view}
                onClick={() => {
                  selectView(item)
                }}
              >
                {STORY_VIEW_LABELS[item]}
              </OptionChip>
            ))}
          </OptionRow>

          <OptionRow label="Format">
            {FORMATS.map((item) => (
              <OptionChip
                key={item}
                active={item === format}
                onClick={() => {
                  setFormat(item)
                }}
              >
                {STORY_FORMAT_LABELS[item]}
              </OptionChip>
            ))}
          </OptionRow>

          <OptionRow label="Fond">
            {BACKGROUNDS.map((item) => (
              <OptionChip
                key={item}
                active={item === background}
                onClick={() => {
                  setBackground(item)
                }}
              >
                {STORY_BACKGROUND_LABELS[item]}
              </OptionChip>
            ))}
          </OptionRow>

          <OptionRow label="Couleur">
            {STORY_ACCENTS.map((item) => (
              <OptionChip
                key={item.key}
                active={item.color === accent}
                swatch={item.color}
                onClick={() => {
                  setAccent(item.color)
                }}
              >
                {item.label}
              </OptionChip>
            ))}
          </OptionRow>

          {metricsCap > 0 && allMetrics.length > 0 && (
            <OptionRow label={`Métriques (${String(metrics.length)}/${String(metricsCap)})`}>
              {allMetrics.map((metric) => (
                <OptionChip
                  key={metric.key}
                  active={metricKeys.includes(metric.key)}
                  onClick={() => {
                    toggleMetric(metric.key)
                  }}
                >
                  {metric.label}
                </OptionChip>
              ))}
            </OptionRow>
          )}

          {view !== 'minimal' && (
            <OptionRow label="Habillage">
              <OptionChip
                active={showTitle}
                onClick={() => {
                  setShowTitle((current) => !current)
                }}
              >
                Sport et date
              </OptionChip>
              <OptionChip
                active={showBrand}
                onClick={() => {
                  setShowBrand((current) => !current)
                }}
              >
                Signature
              </OptionChip>
            </OptionRow>
          )}

          <div className="flex flex-wrap items-center gap-2 pt-1">
            <Button
              type="button"
              size="sm"
              disabled={busy}
              onClick={() => {
                void onDownload()
              }}
            >
              <Download size={14} />
              Télécharger le PNG
            </Button>
            {shareable && (
              <Button
                type="button"
                size="sm"
                variant="outline"
                disabled={busy}
                onClick={() => {
                  void onShare()
                }}
              >
                <Share2 size={14} />
                Partager
              </Button>
            )}
            {feedback && (
              <span
                className={cn(
                  'text-xs',
                  feedback.tone === 'ok' ? 'text-emerald-500' : 'text-muted-foreground'
                )}
              >
                {feedback.text}
              </span>
            )}
          </div>
        </div>
      </div>
    </section>
  )
}
