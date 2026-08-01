'use client'

import dynamic from 'next/dynamic'
import type { ActivityStoryExportProps } from './activity-story-export'

/**
 * Le calque n'existe qu'après une action de l'utilisateur : son code (rendu canvas,
 * projection, export) n'a pas à peser sur le premier chargement de la fiche d'activité.
 */
const ActivityStoryExport = dynamic(
  () => import('./activity-story-export').then((m) => m.ActivityStoryExport),
  {
    ssr: false,
    loading: () => (
      <section className="bg-card rounded-lg border p-4">
        <div className="bg-muted h-5 w-40 animate-pulse rounded" />
        <div className="bg-muted mt-2 h-3 w-full max-w-md animate-pulse rounded" />
        <div className="bg-muted mt-4 h-[390px] w-[220px] animate-pulse rounded-lg" />
      </section>
    ),
  }
)

export function ActivityStoryExportLazy(props: ActivityStoryExportProps) {
  return <ActivityStoryExport {...props} />
}
