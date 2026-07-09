// lib/onboarding/schemas.ts
import { z } from 'zod'

const dateIsoString = z.string().regex(/^\d{4}-\d{2}-\d{2}$/, 'Format attendu YYYY-MM-DD')

export const personSchema = z.object({
  first_name: z.string().trim().min(1, 'Requis').max(80),
  dob: dateIsoString.refine(
    (d) => new Date(d) < new Date(),
    'La date de naissance doit être passée'
  ),
  sex: z.enum(['M', 'F', 'X']),
  city: z.string().trim().max(120).optional(),
  country: z.string().trim().max(80).optional(),
  // Zod v4 : .literal() params only accept string `error`. We use the
  // boolean-refine pattern to get a clean, predictable error message.
  consent_data_processing: z
    .boolean()
    .refine((v) => v, 'Tu dois accepter le traitement des données'),
})

export const PARENT_DISCIPLINES = [
  'triathlon',
  'duathlon',
  'aquathlon',
  'run',
  'bike',
  'swim',
  'autre',
] as const

export const LEG_DISCIPLINES = ['swim', 'bike', 'run'] as const

const legSchema = z.object({
  order: z.number().int().min(1).max(10),
  discipline: z.enum(LEG_DISCIPLINES),
  distance_km: z.number().positive().max(1000),
  elevation_gain_m: z.number().int().min(0).max(20000),
})

export type Leg = z.infer<typeof legSchema>

interface ParentRule {
  count: number | [number, number]
  sequence?: readonly (typeof LEG_DISCIPLINES)[number][]
}

export const LEG_RULES: Record<(typeof PARENT_DISCIPLINES)[number], ParentRule> = {
  triathlon: { count: 3, sequence: ['swim', 'bike', 'run'] },
  duathlon: { count: 3, sequence: ['run', 'bike', 'run'] },
  aquathlon: { count: 2, sequence: ['swim', 'run'] },
  run: { count: 1, sequence: ['run'] },
  bike: { count: 1, sequence: ['bike'] },
  swim: { count: 1, sequence: ['swim'] },
  autre: { count: [1, 10] },
}

export const raceSchema = z
  .object({
    race_date: dateIsoString.refine(
      (d) => new Date(d) > new Date(),
      'La date de course doit être future'
    ),
    discipline: z.enum(PARENT_DISCIPLINES),
    name: z.string().trim().max(160).optional(),
    location: z.string().trim().max(160).optional(),
    target_time_seconds: z.number().int().min(600).max(86400).optional(),
    legs: z.array(legSchema).min(1).max(10),
  })
  .superRefine((data, ctx) => {
    const rule = LEG_RULES[data.discipline]
    if (typeof rule.count === 'number' && data.legs.length !== rule.count) {
      ctx.addIssue({
        code: 'custom',
        path: ['legs'],
        message: `${data.discipline} demande exactement ${String(rule.count)} segment(s)`,
      })
    }
    if (Array.isArray(rule.count)) {
      const [min, max] = rule.count
      if (data.legs.length < min || data.legs.length > max) {
        ctx.addIssue({
          code: 'custom',
          path: ['legs'],
          message: `Entre ${String(min)} et ${String(max)} segments`,
        })
      }
    }
    if (rule.sequence) {
      rule.sequence.forEach((expectedDisc, i) => {
        if (data.legs[i]?.discipline !== expectedDisc) {
          ctx.addIssue({
            code: 'custom',
            path: ['legs', i, 'discipline'],
            message: `Le segment ${String(i + 1)} doit être ${expectedDisc}`,
          })
        }
      })
    }
    data.legs.forEach((leg, i) => {
      if (leg.order !== i + 1) {
        ctx.addIssue({
          code: 'custom',
          path: ['legs', i, 'order'],
          message: `Order doit être ${String(i + 1)}`,
        })
      }
    })
  })

/**
 * Compute total distance + elevation from legs.
 * Used by Server Action (defense in depth) AND by UI (live preview).
 * Distance is rounded to 2 decimals to avoid floating-point drift.
 */
export function computeTotals(legs: Leg[]): {
  total_distance_km: number
  total_elevation_gain_m: number
} {
  return {
    total_distance_km: Math.round(legs.reduce((s, l) => s + l.distance_km, 0) * 100) / 100,
    total_elevation_gain_m: legs.reduce((s, l) => s + l.elevation_gain_m, 0),
  }
}

export const perfSchema = z.object({
  ftp_watts: z.number().int().min(50).max(600).optional(),
  vma_kmh: z.number().min(5).max(30).optional(),
  fc_max_bpm: z.number().int().min(100).max(230).optional(),
  css_per_100m_s: z.number().int().min(40).max(300).optional(),
})

export const DAYS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'] as const

export const dispoSchema = z.object({
  available_days: z.array(z.enum(DAYS)).optional(),
  hours_per_week: z.number().int().min(1).max(30).optional(),
  sports_strengths: z
    .object({
      swim: z.number().int().min(1).max(5),
      bike: z.number().int().min(1).max(5),
      run: z.number().int().min(1).max(5),
    })
    .optional(),
})

export const DISPO_DEFAULTS = {
  available_days: ['mon', 'tue', 'wed', 'thu', 'sat'] as const,
  hours_per_week: 6,
  sports_strengths: { swim: 3, bike: 3, run: 3 },
} satisfies z.infer<typeof dispoSchema>

export type PersonInput = z.infer<typeof personSchema>
export type RaceInput = z.infer<typeof raceSchema>
export type PerfInput = z.infer<typeof perfSchema>
export type DispoInput = z.infer<typeof dispoSchema>
