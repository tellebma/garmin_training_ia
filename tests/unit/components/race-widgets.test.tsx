// @vitest-environment jsdom
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { RaceDebriefCard } from '@/app/(app)/_components/race-debrief-card'
import { RaceTimelineTable } from '@/app/(app)/_components/race-timeline-table'
import { RacesWidget } from '@/app/(app)/_components/races-widget'
import { RaceTagForm } from '@/app/(app)/history/[id]/race-tag-form'
import { RaceResultsForm } from '@/app/(app)/history/race/[id]/race-results-form'
import type { RaceHistoryEntry, RaceTimelineEntry } from '@/lib/coach/race-analysis'

const tagActivityAsRace = vi.fn()
const untagActivityRace = vi.fn()
const createRetroactiveRace = vi.fn()
const saveRaceResults = vi.fn()

vi.mock('@/app/actions/race', () => ({
  tagActivityAsRace: (...args: unknown[]) => tagActivityAsRace(...args) as unknown,
  untagActivityRace: (...args: unknown[]) => untagActivityRace(...args) as unknown,
  createRetroactiveRace: (...args: unknown[]) => createRetroactiveRace(...args) as unknown,
  saveRaceResults: (...args: unknown[]) => saveRaceResults(...args) as unknown,
}))

const TIMELINE: RaceTimelineEntry[] = [
  {
    key: 'swim',
    sport: 'swim',
    label: 'Natation',
    isTransition: false,
    durationS: 1800,
    distanceM: 1500,
    elevationGainM: 0,
    hrAvg: 150,
    paceAvgSPerKm: 1200,
    sharePct: 20,
  },
  {
    key: 't1',
    sport: 'transition',
    label: 'T1',
    isTransition: true,
    durationS: 200,
    distanceM: null,
    elevationGainM: null,
    hrAvg: null,
    paceAvgSPerKm: null,
    sharePct: 2,
  },
]

const RACES: RaceHistoryEntry[] = [
  {
    raceGoalId: 'race-1',
    name: 'Triathlon de Vichy',
    raceDate: '2026-08-22',
    discipline: 'triathlon',
    elapsedS: 9130,
    source: 'official',
    targetDeltaS: -120,
    previousDeltaS: -300,
  },
]

afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('RaceTimelineTable', () => {
  it('renders each segment with its share of the race', () => {
    render(<RaceTimelineTable timeline={TIMELINE} />)

    expect(screen.getByText('Natation')).toBeTruthy()
    expect(screen.getByText('T1')).toBeTruthy()
    expect(screen.getByText('30:00')).toBeTruthy()
  })

  it('explains the empty case instead of showing a blank table', () => {
    render(<RaceTimelineTable timeline={[]} />)

    expect(screen.getByText(/Aucun segment exploitable/)).toBeTruthy()
  })
})

describe('RaceDebriefCard', () => {
  it('shows strengths and improvements', () => {
    render(
      <RaceDebriefCard
        debrief={{
          tone: 'watch',
          verdict: 'Objectif manqué de 4 min.',
          strengths: ['Transitions propres'],
          improvements: ['La FC baisse en fin d’épreuve'],
        }}
      />
    )

    expect(screen.getByText('Objectif manqué de 4 min.')).toBeTruthy()
    expect(screen.getByText('Transitions propres')).toBeTruthy()
    expect(screen.getByText('La FC baisse en fin d’épreuve')).toBeTruthy()
  })
})

describe('RacesWidget', () => {
  it('lists races with both deltas', () => {
    render(<RacesWidget races={RACES} />)

    expect(screen.getByRole('link', { name: 'Triathlon de Vichy' })).toBeTruthy()
    expect(screen.getByText('-5:00 vs précédente')).toBeTruthy()
    expect(screen.getByText('-2:00 / objectif')).toBeTruthy()
  })

  it('invites to tag a race when there is none', () => {
    render(<RacesWidget races={[]} />)

    expect(screen.getByText('Aucune course enregistrée')).toBeTruthy()
  })
})

describe('RaceTagForm', () => {
  beforeEach(() => {
    tagActivityAsRace.mockResolvedValue({ success: true })
    untagActivityRace.mockResolvedValue({ success: true })
    createRetroactiveRace.mockResolvedValue({ success: true })
  })

  it('tags the activity on the race scheduled that day', async () => {
    const user = userEvent.setup()
    render(
      <RaceTagForm
        activityId="act-1"
        activityDate="2026-08-22"
        activitySport="brick"
        race={null}
        candidates={[{ id: 'race-1', name: 'Triathlon de Vichy', discipline: 'triathlon' }]}
      />
    )

    await user.click(screen.getByRole('button', { name: /Triathlon de Vichy/ }))

    await waitFor(() => {
      expect(tagActivityAsRace).toHaveBeenCalledWith({
        activityId: 'act-1',
        raceGoalId: 'race-1',
      })
    })
  })

  it('creates a retroactive race when none exists', async () => {
    const user = userEvent.setup()
    render(
      <RaceTagForm
        activityId="act-1"
        activityDate="2026-08-22"
        activitySport="run"
        race={null}
        candidates={[]}
      />
    )

    await user.click(screen.getByRole('button', { name: /Créer une course/ }))
    await user.type(screen.getByLabelText(/Nom de l’épreuve/), 'Premier triathlon')
    await user.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => {
      expect(createRetroactiveRace).toHaveBeenCalledWith(
        expect.objectContaining({ name: 'Premier triathlon', discipline: 'run' })
      )
    })
  })

  it('offers to untag an activity already linked to a race', async () => {
    const user = userEvent.setup()
    render(
      <RaceTagForm
        activityId="act-1"
        activityDate="2026-08-22"
        activitySport="brick"
        race={{ id: 'race-1', name: 'Triathlon de Vichy', discipline: 'triathlon' }}
        candidates={[]}
      />
    )

    expect(screen.getByRole('link', { name: /Voir la vue course/ })).toBeTruthy()
    await user.click(screen.getByRole('button', { name: /Ce n’est pas une course/ }))

    await waitFor(() => {
      expect(untagActivityRace).toHaveBeenCalledWith('act-1')
    })
  })

  it('surfaces a failure without losing the form', async () => {
    tagActivityAsRace.mockResolvedValue({ success: false, error: 'boom' })
    const user = userEvent.setup()
    render(
      <RaceTagForm
        activityId="act-1"
        activityDate="2026-08-22"
        activitySport="brick"
        race={null}
        candidates={[{ id: 'race-1', name: null, discipline: 'triathlon' }]}
      />
    )

    await user.click(screen.getByRole('button', { name: /Course du jour/ }))

    await waitFor(() => {
      expect(screen.getByText(/Action impossible/)).toBeTruthy()
    })
  })
})

describe('RaceResultsForm', () => {
  beforeEach(() => {
    saveRaceResults.mockResolvedValue({ success: true })
  })

  it('parses typed clocks before saving them', async () => {
    const user = userEvent.setup()
    render(<RaceResultsForm raceGoalId="race-1" initialResults={null} />)

    await user.type(screen.getByLabelText('Temps officiel'), '2:32:10')
    await user.type(screen.getByLabelText('Classement scratch'), '42')
    await user.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => {
      expect(saveRaceResults).toHaveBeenCalledWith(
        expect.objectContaining({ officialTimeS: 9130, overallRank: 42 })
      )
    })
  })

  it('starts collapsed when results already exist and reports a failure', async () => {
    saveRaceResults.mockResolvedValue({ success: false, error: 'nope' })
    const user = userEvent.setup()
    render(
      <RaceResultsForm
        raceGoalId="race-1"
        initialResults={{
          official_time_s: 9130,
          swim_time_s: null,
          t1_time_s: null,
          bike_time_s: null,
          t2_time_s: null,
          run_time_s: null,
          overall_rank: null,
          overall_finishers: null,
          category: null,
          category_rank: null,
          category_finishers: null,
          bib_number: null,
          results_url: null,
          weather: null,
          nutrition: null,
          gear: null,
          incidents: null,
          comment: null,
        }}
      />
    )

    expect(screen.queryByLabelText('Temps officiel')).toBeNull()
    await user.click(screen.getByRole('button', { name: /Résultats officiels/ }))
    await user.click(screen.getByRole('button', { name: 'Enregistrer' }))

    await waitFor(() => {
      expect(screen.getByText(/Enregistrement impossible/)).toBeTruthy()
    })
  })
})
