import { AlertTriangle, ExternalLink } from 'lucide-react'
import { cn } from '@/lib/utils'

interface GarminStatusBannerProps {
  status: string | null
  errorMessage?: string | null
  /** Last known-good activities sync timestamp, used for the freshness banner (#126). */
  lastActivitiesSyncAt?: string | null
  /** Injectable "now" for deterministic tests; defaults to `new Date()`. */
  now?: Date
  className?: string
}

interface BannerContent {
  title: string
  description: string
  steps?: { label: string; href?: string }[]
  variant: 'warning' | 'error'
}

// Mirrors GARMIN_SYNC_STALE_DAYS in worker/src/garmin_sync/coach/cron.py — keep
// both in sync if the threshold changes (see PR description for the rationale).
const GARMIN_SYNC_STALE_DAYS = 3

function daysSinceSync(iso: string | null | undefined, now: Date): number | null {
  if (!iso) return null
  const diffMs = now.getTime() - new Date(iso).getTime()
  return Math.floor(diffMs / 86_400_000)
}

function getBannerContent(status: string | null, daysStale: number | null): BannerContent | null {
  if (status === 'garmin_no_display_name') {
    return {
      variant: 'warning',
      title: 'Configuration Garmin incomplète',
      description:
        "Ton compte Garmin Connect n'a pas de display name (nom affiché). C'est obligatoire pour récupérer tes métriques quotidiennes (sommeil, HRV, body battery).",
      steps: [
        {
          label: 'Va sur Garmin Connect → Paramètres → Profil',
          href: 'https://connect.garmin.com/modern/settings/personal-information',
        },
        { label: 'Renseigne un display name (ex. ton prénom)' },
        { label: 'Sauvegarde, puis relance la synchronisation' },
      ],
    }
  }
  if (status === 'auth_failed') {
    return {
      variant: 'error',
      title: 'Reconnexion Garmin requise',
      description:
        'Ton token Garmin est expiré ou révoqué. Reconnecte-toi pour reprendre la synchronisation.',
      steps: [{ label: 'Va dans Profil → Garmin', href: '/profile/garmin' }],
    }
  }
  if (status === 'rate_limited') {
    return {
      variant: 'warning',
      title: 'Synchronisation Garmin temporairement bloquée',
      description:
        "L'API Garmin a temporairement limité les requêtes. La prochaine synchronisation automatique réessaiera demain matin (05:00 UTC).",
    }
  }
  if (daysStale !== null && daysStale > GARMIN_SYNC_STALE_DAYS) {
    return {
      variant: 'warning',
      title: 'Données Garmin non synchronisées',
      description:
        `Ta dernière synchronisation Garmin remonte à ${String(daysStale)} jours. ` +
        'Ton plan et ton briefing peuvent donc reposer sur des données périmées ' +
        "tant que la synchronisation n'a pas repris.",
      steps: [{ label: 'Vérifie ta connexion Garmin', href: '/profile/garmin' }],
    }
  }
  return null
}

export function GarminStatusBanner({
  status,
  errorMessage,
  lastActivitiesSyncAt,
  now,
  className,
}: Readonly<GarminStatusBannerProps>) {
  const daysStale = daysSinceSync(lastActivitiesSyncAt, now ?? new Date())
  const content = getBannerContent(status, daysStale)
  if (!content) return null

  const colorClass =
    content.variant === 'error'
      ? 'border-red-500/40 bg-red-500/5 text-red-700 dark:text-red-300'
      : 'border-amber-500/40 bg-amber-500/5 text-amber-800 dark:text-amber-200'

  return (
    <aside role="alert" className={cn('rounded-lg border px-4 py-3', colorClass, className)}>
      <div className="flex items-start gap-3">
        <AlertTriangle size={18} className="mt-0.5 shrink-0" aria-hidden="true" />
        <div className="flex-1 space-y-2">
          <p className="text-sm font-semibold">{content.title}</p>
          <p className="text-xs opacity-90">{content.description}</p>
          {content.steps && content.steps.length > 0 && (
            <ol className="ml-4 list-decimal space-y-1 text-xs">
              {content.steps.map((step) => (
                <li key={step.label}>
                  {step.href ? (
                    <a
                      href={step.href}
                      target={step.href.startsWith('http') ? '_blank' : undefined}
                      rel={step.href.startsWith('http') ? 'noreferrer' : undefined}
                      className="inline-flex items-center gap-1 underline underline-offset-2 hover:opacity-80"
                    >
                      {step.label}
                      {step.href.startsWith('http') && (
                        <ExternalLink size={12} aria-hidden="true" />
                      )}
                    </a>
                  ) : (
                    step.label
                  )}
                </li>
              ))}
            </ol>
          )}
          {errorMessage && <p className="font-mono text-[10px] opacity-60">{errorMessage}</p>}
        </div>
      </div>
    </aside>
  )
}
