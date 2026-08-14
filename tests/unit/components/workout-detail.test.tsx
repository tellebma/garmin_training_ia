// @vitest-environment jsdom
import { afterEach, describe, expect, it } from 'vitest'
import { cleanup, render, screen } from '@testing-library/react'
import { WorkoutDetail } from '@/app/(app)/_components/workout-detail'
import type { Sport } from '@/lib/coach/session-templates'
import type { Workout } from '@/lib/coach/workout-types'

afterEach(cleanup)

const z1 = { label: 'Z1', rpe: 2, bpm_low: 120, bpm_high: 135 } as const

const runIntervals: Workout = {
  warmup: { duration_s: 600, target: z1, notes: 'Montée progressive.' },
  main: [
    {
      reps: 6,
      work: {
        duration_s: 240,
        target: { label: 'Z4', rpe: 8, bpm_low: 170, bpm_high: 185 },
        notes: 'Reste sur la pointe.',
      },
      rest: { duration_s: 120, target: z1, notes: 'Trot souple, ne pas marcher.' },
    },
  ],
  cooldown: { duration_s: 600, target: z1 },
  summary_md: 'Séance VMA.',
  technical_focus: 'Foulée tonique.',
}

describe('WorkoutDetail', () => {
  it('renders structured steps instead of raw markdown (issue #187)', () => {
    const { container } = render(<WorkoutDetail workout={runIntervals} sport="run" />)

    expect(screen.getByLabelText('Séance détaillée')).toBeTruthy()
    expect(screen.getByText('Échauffement')).toBeTruthy()
    expect(screen.getByText('Corps de séance')).toBeTruthy()
    expect(screen.getByText('Retour au calme')).toBeTruthy()
    expect(screen.getByText('6 × 4min')).toBeTruthy()
    expect(screen.getByText('170-185 bpm')).toBeTruthy()
    expect(screen.getByText('Séance VMA.')).toBeTruthy()
    expect(screen.getByText(/Foulée tonique./)).toBeTruthy()

    // Plus aucun bloc préformaté ni syntaxe markdown à l'écran.
    expect(container.querySelector('pre')).toBeNull()
    expect(container.textContent).not.toContain('###')
    expect(container.textContent).not.toContain('- 8min')
  })

  it('keeps the zone next to the numeric target', () => {
    render(<WorkoutDetail workout={runIntervals} sport="run" />)
    expect(screen.getAllByText('Z1').length).toBeGreaterThan(0)
    expect(screen.getByText('Z4')).toBeTruthy()
  })

  it('shows the recovery block and its notes on a non-swim set (issue #187)', () => {
    render(<WorkoutDetail workout={runIntervals} sport="run" />)
    expect(screen.getByText('Récup')).toBeTruthy()
    expect(screen.getByText('2min')).toBeTruthy()
    expect(screen.getByText('Trot souple, ne pas marcher.')).toBeTruthy()
  })

  it('renders a swim set with its send-off, its rest notes and the hidden duration', () => {
    const swim: Workout = {
      warmup: { duration_s: 480, distance_m: 400, target: z1 },
      main: [
        {
          reps: 8,
          work: {
            duration_s: 95,
            distance_m: 100,
            target: { label: 'Z4', rpe: 8, pace_per_100m_low_s: 94, pace_per_100m_high_s: 99 },
          },
          rest: { duration_s: 15, target: z1, notes: "Départ toutes les 1'50 à la pendule." },
        },
      ],
      cooldown: { duration_s: 240, distance_m: 200, target: z1 },
      summary_md: 'Séries au seuil.',
    }
    render(<WorkoutDetail workout={swim} sport="swim" />)

    expect(screen.getByText('8 × 100 m')).toBeTruthy()
    expect(screen.getByText("départ 1'50")).toBeTruthy()
    expect(screen.getByText("1'34–1'39 /100m")).toBeTruthy()
    // La durée de nage n'est plus masquée par la distance (issue #187).
    expect(screen.getByText("(1'35)")).toBeTruthy()
    expect(screen.getByText("(8'00)")).toBeTruthy()
    // rest.notes est enfin affiché.
    expect(screen.getByText("Départ toutes les 1'50 à la pendule.")).toBeTruthy()
  })

  it('renders a multi-segment race day with per-segment notes (PR #174)', () => {
    const raceDay: Workout = {
      warmup: {
        duration_s: 900,
        target: { label: 'Z1', rpe: 3 },
        notes: "Échauffement d'avant-course : mobilité, 10 min très souple.",
      },
      main: [
        {
          duration_s: 1560,
          distance_m: 1400,
          target: { label: 'Z3', rpe: 7 },
          notes: 'Natation — 1,4 km · objectif 26min · Z3 / RPE 7 · pars en dessous.',
        },
        {
          duration_s: 300,
          target: { label: 'Z2', rpe: 4 },
          notes: 'T1 (natation → vélo) — objectif 5min : matériel dans l’ordre.',
        },
        {
          duration_s: 9120,
          distance_m: 47_000,
          target: { label: 'Z3', rpe: 7 },
          notes: 'Vélo — 47 km · 2000 m D+ · objectif 2h32 · monte en régularité.',
        },
      ],
      cooldown: { duration_s: 600, target: { label: 'Z1', rpe: 2 }, notes: 'Retour au calme.' },
      summary_md:
        'Objectif de temps : 3h52 (natation 26min + vélo 2h32).\n' +
        'Allure cible : Z3, RPE 7.\n' +
        'Hydratation : boire 500 ml/h, 60 g de glucides/h.',
      technical_focus: 'Ne jamais partir en sur-régime.',
    }
    // Le sport d'un jour de course vient de la base et sort des templates.
    const raceSport = 'triathlon' as unknown as Sport
    render(<WorkoutDetail workout={raceDay} sport={raceSport} />)

    // Un bloc par segment, transitions comprises.
    expect(screen.getByText('26min')).toBeTruthy()
    expect(screen.getByText('2h32')).toBeTruthy()
    expect(screen.getByText('(1.4 km)')).toBeTruthy()
    expect(screen.getByText('(47 km)')).toBeTruthy()
    expect(screen.getByText(/T1 \(natation → vélo\)/)).toBeTruthy()
    expect(screen.getByText(/monte en régularité/)).toBeTruthy()

    // Le résumé multi-ligne devient un paragraphe par ligne.
    expect(screen.getByText(/Objectif de temps : 3h52/)).toBeTruthy()
    expect(screen.getByText('Allure cible : Z3, RPE 7.')).toBeTruthy()
    expect(screen.getByText(/60 g de glucides\/h/)).toBeTruthy()
  })

  it('renders nothing extra when the workout has no summary nor technical focus', () => {
    const bare: Workout = {
      warmup: { duration_s: 600, target: z1 },
      main: [{ duration_s: 1800, target: z1 }],
      cooldown: { duration_s: 600, target: z1 },
      summary_md: '',
      technical_focus: null,
    }
    render(<WorkoutDetail workout={bare} sport="bike" />)
    expect(screen.queryByText(/Focus technique/)).toBeNull()
    expect(screen.getByText('30min')).toBeTruthy()
  })
})
