import { describe, expect, it } from 'vitest'
import {
  MAX_PROMPT_INTERRUPTIONS,
  postRacePromptSurface,
  promptWindow,
  type PostRacePromptRow,
} from '@/lib/coach/post-race-prompt'

const TODAY = new Date('2026-08-26T09:00:00Z')

function race(overrides: Partial<PostRacePromptRow> = {}): PostRacePromptRow {
  return {
    id: 'race-1',
    race_date: '2026-08-24',
    name: 'Triathlon de Vichy',
    post_race_choice: null,
    post_race_prompt_count: 0,
    post_race_prompt_snoozed_until: null,
    ...overrides,
  }
}

describe('promptWindow', () => {
  it('couvre les 14 derniers jours, bornes incluses', () => {
    expect(promptWindow(TODAY)).toEqual({ from: '2026-08-12', to: '2026-08-26' })
  })
})

describe('postRacePromptSurface', () => {
  it('ouvre la modale pour une course fraîche jamais traitée', () => {
    expect(postRacePromptSurface(race(), TODAY)).toBe('sheet')
  })

  it('se tait dès que l’athlète a choisi', () => {
    expect(postRacePromptSurface(race({ post_race_choice: 'maintain' }), TODAY)).toBeNull()
    // Y compris quand il a explicitement refusé de choisir.
    expect(postRacePromptSurface(race({ post_race_choice: 'dismissed' }), TODAY)).toBeNull()
  })

  it('ne réveille pas une épreuve ancienne', () => {
    // Le cas qui motive la fenêtre : `backfill_races` rattache les courses d'avant l'app.
    expect(postRacePromptSurface(race({ race_date: '2024-06-15' }), TODAY)).toBeNull()
    expect(postRacePromptSurface(race({ race_date: '2026-08-11' }), TODAY)).toBeNull()
  })

  it('accepte une course du jour même et une course du bord de fenêtre', () => {
    expect(postRacePromptSurface(race({ race_date: '2026-08-26' }), TODAY)).toBe('sheet')
    expect(postRacePromptSurface(race({ race_date: '2026-08-12' }), TODAY)).toBe('sheet')
  })

  it('ignore une course encore à venir', () => {
    expect(postRacePromptSurface(race({ race_date: '2026-09-10' }), TODAY)).toBeNull()
  })

  it('respecte un report non échu, et revient le jour dit', () => {
    const snoozed = race({
      post_race_prompt_count: 1,
      post_race_prompt_snoozed_until: '2026-08-28',
    })
    expect(postRacePromptSurface(snoozed, TODAY)).toBeNull()
    expect(postRacePromptSurface(snoozed, new Date('2026-08-28T07:00:00Z'))).toBe('sheet')
  })

  it('cesse d’interrompre après deux reports et passe à la bannière', () => {
    const tired = race({
      post_race_prompt_count: MAX_PROMPT_INTERRUPTIONS,
      post_race_prompt_snoozed_until: '2026-08-31',
    })
    // Même avec un report encore actif : la bannière est permanente, pas une relance.
    expect(postRacePromptSurface(tired, TODAY)).toBe('banner')
  })

  it('traite un compteur absent comme zéro report', () => {
    expect(postRacePromptSurface(race({ post_race_prompt_count: null }), TODAY)).toBe('sheet')
  })
})
