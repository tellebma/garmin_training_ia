'use client'

import { useState, useTransition } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { answerPostRacePrompt, snoozePostRacePrompt } from '@/app/actions/post-race'
import { Button } from '@/components/ui/button'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from '@/components/ui/sheet'
import type { RaceSalute } from '@/lib/coach/race-analysis'

export interface PostRacePromptProps {
  readonly raceGoalId: string
  readonly raceName: string
  readonly salute: RaceSalute
  /** `banner` : l'athlète a déjà reporté deux fois, on n'interrompt plus. */
  readonly surface: 'sheet' | 'banner'
}

const CHOICES = [
  {
    value: 'new_race',
    label: 'Viser une nouvelle course',
    hint: 'Un plan périodisé vers ta prochaine épreuve.',
    href: '/profile',
  },
  {
    value: 'maintain',
    label: 'Maintenir ma forme',
    hint: 'Charge stable, sans chercher à progresser.',
  },
  {
    value: 'improve',
    label: 'Progresser sans objectif',
    hint: 'Charge en hausse régulière, sans date à tenir.',
  },
] as const

const TONE_CLASS: Readonly<Record<RaceSalute['tone'], string>> = {
  cheer: 'text-emerald-600 dark:text-emerald-400',
  neutral: 'text-foreground',
  tender: 'text-amber-600 dark:text-amber-400',
}

/**
 * Le moment où l'athlète choisit la suite (E26).
 *
 * `Sheet` bas d'écran plutôt que dialogue centré : c'est une PWA, et c'est la forme déjà
 * utilisée par la cloche des nouveautés. « Viser une nouvelle course » ferme et navigue
 * vers le formulaire — pas de wizard imbriqué dans un tiroir.
 */
export function PostRaceSheet({ raceGoalId, raceName, salute, surface }: PostRacePromptProps) {
  const [open, setOpen] = useState(surface === 'sheet')
  const [done, setDone] = useState(false)
  const [pending, startTransition] = useTransition()

  function choose(choice: string) {
    if (pending) return
    startTransition(() => {
      void answerPostRacePrompt(raceGoalId, choice).then((result) => {
        if (result.success) {
          setDone(true)
          setOpen(false)
        } else {
          toast.error('Ton choix n’a pas pu être enregistré.')
        }
      })
    })
  }

  function later() {
    if (pending) return
    setOpen(false)
    startTransition(() => {
      void snoozePostRacePrompt(raceGoalId).then((result) => {
        if (result.success) toast.info('On en reparle dans quelques jours.')
      })
    })
  }

  if (done) return null

  const body = (
    <div className="space-y-2">
      {CHOICES.map((choice) =>
        'href' in choice ? (
          <Button
            key={choice.value}
            asChild
            variant="outline"
            className="h-auto w-full justify-start py-3 text-left"
          >
            <Link
              href={choice.href}
              onClick={() => {
                choose(choice.value)
              }}
            >
              <span className="block">
                <span className="block text-sm font-medium">{choice.label}</span>
                <span className="text-muted-foreground block text-xs">{choice.hint}</span>
              </span>
            </Link>
          </Button>
        ) : (
          <button
            key={choice.value}
            type="button"
            disabled={pending}
            onClick={() => {
              choose(choice.value)
            }}
            className="hover:bg-muted/50 w-full rounded-md border p-3 text-left transition-colors"
          >
            <span className="block text-sm font-medium">{choice.label}</span>
            <span className="text-muted-foreground block text-xs">{choice.hint}</span>
          </button>
        )
      )}
    </div>
  )

  if (surface === 'banner') {
    return (
      <section
        data-testid="post-race-banner"
        className="space-y-3 rounded-lg border border-dashed p-4"
      >
        <div>
          <p className="text-sm font-medium">Et maintenant ?</p>
          <p className="text-muted-foreground text-xs">
            Depuis {raceName}, ton plan tourne en maintien. Choisis ton cap quand tu veux.
          </p>
        </div>
        {body}
      </section>
    )
  }

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent side="bottom" data-testid="post-race-sheet">
        <SheetHeader>
          <SheetTitle className={TONE_CLASS[salute.tone]}>{salute.headline}</SheetTitle>
          <SheetDescription>
            {raceName} — {salute.figure}.{' '}
            <Link href={`/history/race/${raceGoalId}`} className="underline">
              Voir le débrief
            </Link>
          </SheetDescription>
        </SheetHeader>
        <div className="space-y-3 px-4 pb-6">
          <p className="text-muted-foreground text-sm">Qu’est-ce qu’on vise maintenant ?</p>
          {body}
          <button
            type="button"
            onClick={later}
            disabled={pending}
            className="text-muted-foreground w-full text-center text-xs underline"
          >
            Plus tard
          </button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
