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
  consent_data_processing: z.literal(true, 'Tu dois accepter le traitement des données'),
})

export const RACE_DISTANCES = ['sprint', 'olympique', 'half_ironman', 'ironman', 'autre'] as const

export const raceSchema = z.object({
  race_date: dateIsoString.refine(
    (d) => new Date(d) > new Date(),
    'La date de course doit être future'
  ),
  race_distance: z.enum(RACE_DISTANCES),
  name: z.string().trim().max(160).optional(),
  location: z.string().trim().max(160).optional(),
  target_time_seconds: z.number().int().min(600).max(86400).optional(),
})

export const perfSchema = z.object({
  ftp_watts: z.number().int().min(50).max(600).optional(),
  vma_kmh: z.number().min(5).max(30).optional(),
  fc_max_bpm: z.number().int().min(100).max(230).optional(),
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
