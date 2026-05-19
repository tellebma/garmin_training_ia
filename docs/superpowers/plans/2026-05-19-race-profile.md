# Race Profile v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Évoluer le modèle `race_goals` de l'enum mono-distance vers un modèle riche (parent discipline + N legs avec distance + dénivelé), avec migration SQL breaking (table vide en prod), refactor Zod, recalcul Server Action, refactor des 2 UIs (wizard + profile-edit).

**Architecture:** Migration SQL idempotente qui rename `race_distance → discipline` et ajoute 3 colonnes (`total_distance_km`, `total_elevation_gain_m`, `legs jsonb`). Zod schema avec `superRefine` impose les invariants par discipline parent. Frontend auto-génère les legs au changement de discipline, calcule les totaux en live, et applique les contraintes UX (champs disabled sur disciplines à legs fixes).

**Tech Stack:**
- DB : Supabase Postgres + RLS
- Frontend : Next.js 15 App Router, TypeScript strict++, Zod v4, supabase-js
- Tests : Vitest avec mocks Supabase

**Spec source :** [`docs/superpowers/specs/2026-05-19-race-profile-design.md`](../specs/2026-05-19-race-profile-design.md)

---

## Pré-requis avant de démarrer

- Branche dédiée : `git checkout main && git pull && git checkout -b feat/race-profile-v2`
- Vérifier que `select count(*) from public.race_goals` retourne 0 (rangée vide en prod — migration breaking safe). Si > 0 entre la rédaction et l'exécution, stopper et faire un backfill.

---

## Task 1 — Migration DB : rename + 3 nouvelles colonnes

**Files:**
- Create: `supabase/migrations/20260519100000_race_profile_v2.sql`

- [ ] **Step 1: Créer le fichier migration**

```sql
-- 20260519100000_race_profile_v2.sql
-- Race Profile v2 : multi-discipline + per-leg distance/elevation

-- =========================================
-- Drop ancien check (enum mono-discipline) si présent
-- =========================================
alter table public.race_goals drop constraint if exists race_goals_race_distance_check;

-- =========================================
-- Rename : race_distance → discipline (parent type)
-- =========================================
alter table public.race_goals rename column race_distance to discipline;

-- =========================================
-- Nouveau check sur disciplines parent (étendu)
-- =========================================
alter table public.race_goals
  add constraint race_goals_discipline_check
  check (discipline in ('triathlon','duathlon','aquathlon','run','bike','swim','autre'));

-- =========================================
-- Nouvelles colonnes pour le profil géométrique
-- =========================================
alter table public.race_goals
  add column if not exists total_distance_km numeric(7,2)
    check (total_distance_km is null or (total_distance_km > 0 and total_distance_km <= 1000)),
  add column if not exists total_elevation_gain_m integer
    check (total_elevation_gain_m is null or (total_elevation_gain_m >= 0 and total_elevation_gain_m <= 20000)),
  add column if not exists legs jsonb not null default '[]'::jsonb;

comment on column public.race_goals.discipline is
  'Type de course parent : triathlon, duathlon, aquathlon, run, bike, swim, autre.';
comment on column public.race_goals.total_distance_km is
  'Distance totale en km (somme des legs, mise en cache pour query rapide).';
comment on column public.race_goals.total_elevation_gain_m is
  'Dénivelé positif total en mètres (somme des legs, mise en cache).';
comment on column public.race_goals.legs is
  'Détail des segments : [{order:int, discipline:swim|bike|run, distance_km:number, elevation_gain_m:int}].';
```

- [ ] **Step 2: Vérifier table vide AVANT d'appliquer**

Via `mcp__supabase__execute_sql`:
```sql
select count(*) as n from public.race_goals;
```
Expected: `n = 0`. Si != 0 → STOP et faire un backfill manuel d'abord.

- [ ] **Step 3: Appliquer la migration via Supabase MCP**

Via `mcp__supabase__apply_migration` (project_id `peiyrqplymdlmlpsbqzu`, name `20260519100000_race_profile_v2`, query = contenu Step 1).

- [ ] **Step 4: Vérifier le rename + nouveaux columns**

```sql
select column_name, data_type, is_nullable
from information_schema.columns
where table_schema = 'public' and table_name = 'race_goals'
order by ordinal_position;
```
Expected: les colonnes incluent `discipline`, `total_distance_km`, `total_elevation_gain_m`, `legs` ; PAS de colonne `race_distance`.

- [ ] **Step 5: Vérifier le check constraint sur discipline**

```sql
select conname, pg_get_constraintdef(oid)
from pg_constraint
where conrelid = 'public.race_goals'::regclass
  and conname = 'race_goals_discipline_check';
```
Expected: 1 row avec la clause CHECK listant les 7 valeurs autorisées.

- [ ] **Step 6: Test fonctionnel des contraintes**

```sql
-- Doit échouer : discipline invalide
do $$ begin
  insert into public.race_goals (user_id, race_date, discipline, legs)
  values ('00000000-0000-0000-0000-000000000000', current_date + 30, 'invalid_value', '[]'::jsonb);
  raise exception 'should have failed';
exception when check_violation then
  raise notice 'CHECK constraint discipline OK';
end $$;
```
Expected: NOTICE `CHECK constraint discipline OK`. Si la migration applique le check, le DO bloc relâchera l'erreur attendue.

- [ ] **Step 7: Commit**

```bash
git add supabase/migrations/20260519100000_race_profile_v2.sql
git commit -m "feat(db): race_profile v2 — multi-discipline + per-leg distance/elevation"
```

---

## Task 2 — Zod schemas refactor + `computeTotals` helper + tests

**Files:**
- Modify: `lib/onboarding/schemas.ts`
- Modify: `tests/unit/onboarding/schemas.test.ts`

- [ ] **Step 1: Refactor `lib/onboarding/schemas.ts` — section `raceSchema`**

Remplace TOUT le bloc `raceSchema` actuel (lignes définissant `RACE_DISTANCES` + `raceSchema`) par le code suivant :

```typescript
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

type ParentRule = {
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

export type RaceInput = z.infer<typeof raceSchema>

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
```

Supprime aussi l'ancien `RACE_DISTANCES` export et toute référence à `race_distance` dans ce fichier.

- [ ] **Step 2: Update import dans les fichiers consommateurs**

Vérifier que les fichiers qui importent `RACE_DISTANCES` ou `RaceInput` ne sont pas cassés. Lister :
```bash
cd /home/tellebma/DEV/garmin_training
grep -rn "RACE_DISTANCES\|race_distance" --include='*.ts' --include='*.tsx' . | grep -v node_modules | grep -v '.next'
```
Si des occurrences sortent, il faut les nettoyer dans la même PR ou dans les tasks UI/Server Action qui suivent.

- [ ] **Step 3: Refactor `tests/unit/onboarding/schemas.test.ts` — remplacer le describe('raceSchema', ...)**

Remplacer le bloc `describe('raceSchema', ...)` existant par :

```typescript
describe('raceSchema', () => {
  const future = new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10)

  const triathlonValid = {
    race_date: future,
    discipline: 'triathlon' as const,
    legs: [
      { order: 1, discipline: 'swim' as const, distance_km: 1.4, elevation_gain_m: 0 },
      { order: 2, discipline: 'bike' as const, distance_km: 53, elevation_gain_m: 2200 },
      { order: 3, discipline: 'run' as const, distance_km: 8, elevation_gain_m: 200 },
    ],
  }

  it('accepts a valid triathlon with 3 legs in correct order', () => {
    expect(raceSchema.safeParse(triathlonValid).success).toBe(true)
  })

  it('rejects triathlon with 2 legs', () => {
    const bad = { ...triathlonValid, legs: triathlonValid.legs.slice(0, 2) }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects triathlon with wrong leg sequence (bike first)', () => {
    const bad = {
      ...triathlonValid,
      legs: [
        { order: 1, discipline: 'bike' as const, distance_km: 53, elevation_gain_m: 2200 },
        { order: 2, discipline: 'swim' as const, distance_km: 1.4, elevation_gain_m: 0 },
        { order: 3, discipline: 'run' as const, distance_km: 8, elevation_gain_m: 200 },
      ],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects past race_date', () => {
    const bad = { ...triathlonValid, race_date: '2000-01-01' }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('accepts run with 1 leg', () => {
    const ok = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 25, elevation_gain_m: 1000 }],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('rejects run with a bike leg', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'bike' as const, distance_km: 25, elevation_gain_m: 1000 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('accepts duathlon with run/bike/run sequence', () => {
    const ok = {
      race_date: future,
      discipline: 'duathlon' as const,
      legs: [
        { order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
        { order: 2, discipline: 'bike' as const, distance_km: 20, elevation_gain_m: 300 },
        { order: 3, discipline: 'run' as const, distance_km: 2.5, elevation_gain_m: 30 },
      ],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('accepts aquathlon with swim/run sequence', () => {
    const ok = {
      race_date: future,
      discipline: 'aquathlon' as const,
      legs: [
        { order: 1, discipline: 'swim' as const, distance_km: 1.5, elevation_gain_m: 0 },
        { order: 2, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
      ],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('accepts autre with 4 mixed legs (swimrun style)', () => {
    const ok = {
      race_date: future,
      discipline: 'autre' as const,
      legs: [
        { order: 1, discipline: 'swim' as const, distance_km: 0.5, elevation_gain_m: 0 },
        { order: 2, discipline: 'run' as const, distance_km: 3, elevation_gain_m: 50 },
        { order: 3, discipline: 'swim' as const, distance_km: 0.8, elevation_gain_m: 0 },
        { order: 4, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 100 },
      ],
    }
    expect(raceSchema.safeParse(ok).success).toBe(true)
  })

  it('rejects autre with 11 legs (max 10)', () => {
    const tooMany = {
      race_date: future,
      discipline: 'autre' as const,
      legs: Array.from({ length: 11 }, (_, i) => ({
        order: i + 1,
        discipline: 'run' as const,
        distance_km: 1,
        elevation_gain_m: 0,
      })),
    }
    expect(raceSchema.safeParse(tooMany).success).toBe(false)
  })

  it('rejects non-sequential leg orders', () => {
    const bad = {
      race_date: future,
      discipline: 'autre' as const,
      legs: [
        { order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
        { order: 3, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 50 },
      ],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects distance ≤ 0', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 0, elevation_gain_m: 0 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects D+ < 0', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: -10 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })

  it('rejects D+ > 20000', () => {
    const bad = {
      race_date: future,
      discipline: 'run' as const,
      legs: [{ order: 1, discipline: 'run' as const, distance_km: 5, elevation_gain_m: 25000 }],
    }
    expect(raceSchema.safeParse(bad).success).toBe(false)
  })
})

describe('computeTotals', () => {
  it('sums Triathlon Madeleine correctly (62.4 km, 2400 m)', () => {
    const legs = [
      { order: 1, discipline: 'swim' as const, distance_km: 1.4, elevation_gain_m: 0 },
      { order: 2, discipline: 'bike' as const, distance_km: 53, elevation_gain_m: 2200 },
      { order: 3, discipline: 'run' as const, distance_km: 8, elevation_gain_m: 200 },
    ]
    expect(computeTotals(legs)).toEqual({
      total_distance_km: 62.4,
      total_elevation_gain_m: 2400,
    })
  })

  it('sums a mono-leg trail (25 km / 1000 m)', () => {
    const legs = [
      { order: 1, discipline: 'run' as const, distance_km: 25, elevation_gain_m: 1000 },
    ]
    expect(computeTotals(legs)).toEqual({
      total_distance_km: 25,
      total_elevation_gain_m: 1000,
    })
  })

  it('rounds distance to 2 decimals', () => {
    const legs = [
      { order: 1, discipline: 'run' as const, distance_km: 1.234, elevation_gain_m: 0 },
      { order: 2, discipline: 'run' as const, distance_km: 2.567, elevation_gain_m: 0 },
    ]
    expect(computeTotals(legs).total_distance_km).toBe(3.8)
  })

  it('returns 0/0 for empty legs', () => {
    expect(computeTotals([])).toEqual({
      total_distance_km: 0,
      total_elevation_gain_m: 0,
    })
  })
})
```

Aussi : importer `computeTotals` en haut du fichier (`import { ..., computeTotals } from './schemas'` n'existe pas car schemas.test.ts utilise `from '@/lib/onboarding/schemas'`).

- [ ] **Step 4: Run tests, observe pass**

```bash
cd /home/tellebma/DEV/garmin_training
pnpm test --run tests/unit/onboarding/schemas
```
Expected: all PASS (~30 tests : les anciens dispoSchema/personSchema/perfSchema + nouveaux raceSchema + computeTotals).

- [ ] **Step 5: Quality gates**

```bash
pnpm typecheck && pnpm lint
```
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add lib/onboarding/schemas.ts tests/unit/onboarding/schemas.test.ts
git commit -m "feat(race): refactor raceSchema with legs + computeTotals helper"
```

---

## Task 3 — Server Action `saveStepRace` : recalcul totals

**Files:**
- Modify: `app/(app)/onboarding/actions.ts`

- [ ] **Step 1: Update `saveStepRace` dans `app/(app)/onboarding/actions.ts`**

Remplacer le corps de la fonction `saveStepRace` par :

```typescript
export async function saveStepRace(input: RaceInput): Promise<StepResult> {
  const parsed = raceSchema.safeParse(input)
  if (!parsed.success) {
    return {
      success: false,
      errors: z.flattenError(parsed.error).fieldErrors as Record<string, string[]>,
    }
  }
  const userIdOrErr = await requireUserId()
  if (typeof userIdOrErr !== 'string') return userIdOrErr

  const supabase = await createClient()

  // Defense in depth — UI computes totals live, but Server Action recompute
  // to avoid trusting client-supplied totals.
  const { total_distance_km, total_elevation_gain_m } = computeTotals(parsed.data.legs)

  const { data: existing } = await supabase
    .from('race_goals')
    .select('id')
    .eq('user_id', userIdOrErr)
    .eq('is_primary', true)
    .maybeSingle()

  const payload = {
    user_id: userIdOrErr,
    race_date: parsed.data.race_date,
    discipline: parsed.data.discipline,
    name: parsed.data.name ?? null,
    location: parsed.data.location ?? null,
    target_time_seconds: parsed.data.target_time_seconds ?? null,
    legs: parsed.data.legs,
    total_distance_km,
    total_elevation_gain_m,
    is_primary: true,
  }

  const { error } = existing
    ? await supabase.from('race_goals').update(payload).eq('id', existing.id)
    : await supabase.from('race_goals').insert(payload)

  if (error) return { success: false, error: 'save_failed' }

  revalidatePath(ONBOARDING_PATH)
  return { success: true, nextStep: nextStep('race') }
}
```

Add `computeTotals` to the imports at top of file:

```typescript
import {
  // ... existing imports
  computeTotals,
} from '@/lib/onboarding/schemas'
```

- [ ] **Step 2: Quality gates**

```bash
cd /home/tellebma/DEV/garmin_training
pnpm typecheck && pnpm lint
```
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add app/'(app)'/onboarding/actions.ts
git commit -m "feat(race): saveStepRace recomputes totals + writes legs+discipline"
```

---

## Task 4 — UI `step-race-form.tsx` (wizard étape 2) refactor

**Files:**
- Modify: `app/(app)/onboarding/_components/step-race-form.tsx`

- [ ] **Step 1: Replace `step-race-form.tsx` complete content**

Le fichier actuel est un form simple avec champs `race_distance` enum + temps cible. Remplace tout son contenu par :

```typescript
'use client'

import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepRace } from '../actions'
import {
  PARENT_DISCIPLINES,
  LEG_RULES,
  computeTotals,
  type Leg,
  type RaceInput,
} from '@/lib/onboarding/schemas'
import type { Step } from '@/lib/onboarding/steps'

interface Props {
  defaultValues: RaceInput | null
  onDone: (nextStep: Step | null) => void
}

const PARENT_LABEL: Record<(typeof PARENT_DISCIPLINES)[number], string> = {
  triathlon: 'Triathlon',
  duathlon: 'Duathlon',
  aquathlon: 'Aquathlon',
  run: 'Course (route ou trail)',
  bike: 'Vélo',
  swim: 'Natation',
  autre: 'Autre / personnalisé',
}

const LEG_ICON: Record<'swim' | 'bike' | 'run', string> = {
  swim: '🏊',
  bike: '🚴',
  run: '🏃',
}

const LEG_NAME: Record<'swim' | 'bike' | 'run', string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
}

/** Generate empty legs for a given parent discipline based on LEG_RULES.sequence. */
function defaultLegsFor(discipline: (typeof PARENT_DISCIPLINES)[number]): Leg[] {
  const rule = LEG_RULES[discipline]
  if (rule.sequence) {
    return rule.sequence.map((d, i) => ({
      order: i + 1,
      discipline: d,
      distance_km: 0,
      elevation_gain_m: 0,
    }))
  }
  // 'autre' → 1 leg vide par défaut, user ajoute via bouton
  return [{ order: 1, discipline: 'run', distance_km: 0, elevation_gain_m: 0 }]
}

function hmsToSeconds(hms: string): number {
  const [h, m, s] = hms.split(':').map((n) => Number.parseInt(n, 10))
  return h * 3600 + m * 60 + s
}

function secondsToHms(total: number): string {
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

export function StepRaceForm({ defaultValues, onDone }: Readonly<Props>) {
  const [race_date, setRaceDate] = useState(defaultValues?.race_date ?? '')
  const [discipline, setDiscipline] = useState<(typeof PARENT_DISCIPLINES)[number]>(
    defaultValues?.discipline ?? 'triathlon'
  )
  const [name, setName] = useState(defaultValues?.name ?? '')
  const [location, setLocation] = useState(defaultValues?.location ?? '')
  const [targetHms, setTargetHms] = useState(
    defaultValues?.target_time_seconds ? secondsToHms(defaultValues.target_time_seconds) : ''
  )
  const [legs, setLegs] = useState<Leg[]>(
    defaultValues?.legs ?? defaultLegsFor(defaultValues?.discipline ?? 'triathlon')
  )
  const [loading, setLoading] = useState(false)
  const [errors, setErrors] = useState<Record<string, string[]>>({})

  // Re-generate legs whenever discipline changes (UNLESS we are in 'autre' which is user-driven)
  useEffect(() => {
    if (discipline === 'autre') return
    setLegs(defaultLegsFor(discipline))
  }, [discipline])

  const isAutre = discipline === 'autre'
  const totals = computeTotals(legs)

  function updateLeg(index: number, patch: Partial<Leg>) {
    setLegs((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)))
  }

  function addLeg() {
    setLegs((prev) => [
      ...prev,
      { order: prev.length + 1, discipline: 'run', distance_km: 0, elevation_gain_m: 0 },
    ])
  }

  function removeLeg(index: number) {
    setLegs((prev) =>
      prev
        .filter((_, i) => i !== index)
        .map((l, i) => ({ ...l, order: i + 1 })) // renumérote
    )
  }

  async function handleSubmit(e: React.SyntheticEvent<HTMLFormElement>) {
    e.preventDefault()
    setLoading(true)
    setErrors({})
    const target_time_seconds = targetHms ? hmsToSeconds(targetHms) : undefined
    const result = await saveStepRace({
      race_date,
      discipline,
      name: name || undefined,
      location: location || undefined,
      target_time_seconds,
      legs,
    })
    setLoading(false)
    if (!result.success) {
      if ('errors' in result) setErrors(result.errors)
      else toast.error('Erreur de sauvegarde, réessaye')
      return
    }
    onDone(result.nextStep)
  }

  return (
    <form
      onSubmit={(e) => {
        void handleSubmit(e)
      }}
      className="space-y-4"
    >
      <div className="space-y-2">
        <Label htmlFor="race_date">Date de la course</Label>
        <Input
          id="race_date"
          type="date"
          value={race_date}
          onChange={(e) => {
            setRaceDate(e.target.value)
          }}
          required
        />
        {errors.race_date?.[0] && (
          <p className="text-destructive text-xs">{errors.race_date[0]}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor="discipline">Type de course</Label>
        <select
          id="discipline"
          value={discipline}
          onChange={(e) => {
            setDiscipline(e.target.value as (typeof PARENT_DISCIPLINES)[number])
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          {PARENT_DISCIPLINES.map((d) => (
            <option key={d} value={d}>
              {PARENT_LABEL[d]}
            </option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="name">Nom de la course (optionnel)</Label>
        <Input
          id="name"
          value={name}
          onChange={(e) => {
            setName(e.target.value)
          }}
          placeholder="ex: Triathlon de la Madeleine"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="location">Lieu (optionnel)</Label>
        <Input
          id="location"
          value={location}
          onChange={(e) => {
            setLocation(e.target.value)
          }}
          placeholder="ex: La Madeleine, FR"
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="target_hms">Temps cible total (optionnel, hh:mm:ss)</Label>
        <Input
          id="target_hms"
          value={targetHms}
          onChange={(e) => {
            setTargetHms(e.target.value)
          }}
          placeholder="05:30:00"
          pattern="^\d{1,2}:\d{2}:\d{2}$"
        />
      </div>

      <div className="space-y-3 rounded-lg border p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">
            Segments{isAutre ? '' : ` (${String(legs.length)} requis pour ${PARENT_LABEL[discipline]})`}
          </h3>
          {isAutre && (
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={addLeg}
              disabled={legs.length >= 10}
            >
              + Ajouter
            </Button>
          )}
        </div>

        {legs.map((leg, i) => (
          <div key={`${String(leg.order)}-${leg.discipline}`} className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm font-medium">
                <span>{String(i + 1)}.</span>
                {isAutre ? (
                  <select
                    value={leg.discipline}
                    onChange={(e) => {
                      updateLeg(i, {
                        discipline: e.target.value as 'swim' | 'bike' | 'run',
                      })
                    }}
                    className="border-input bg-background h-8 rounded-md border px-2 text-sm"
                  >
                    {(['swim', 'bike', 'run'] as const).map((d) => (
                      <option key={d} value={d}>
                        {LEG_ICON[d]} {LEG_NAME[d]}
                      </option>
                    ))}
                  </select>
                ) : (
                  <span>
                    {LEG_ICON[leg.discipline]} {LEG_NAME[leg.discipline]}
                  </span>
                )}
              </div>
              {isAutre && legs.length > 1 && (
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={() => {
                    removeLeg(i)
                  }}
                >
                  − Retirer
                </Button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs" htmlFor={`leg-${String(i)}-distance`}>
                  Distance (km)
                </Label>
                <Input
                  id={`leg-${String(i)}-distance`}
                  type="number"
                  step="0.01"
                  min={0}
                  max={1000}
                  value={leg.distance_km || ''}
                  onChange={(e) => {
                    updateLeg(i, { distance_km: Number.parseFloat(e.target.value) || 0 })
                  }}
                  required
                />
              </div>
              <div>
                <Label className="text-xs" htmlFor={`leg-${String(i)}-elevation`}>
                  D+ (m)
                </Label>
                <Input
                  id={`leg-${String(i)}-elevation`}
                  type="number"
                  step="1"
                  min={0}
                  max={20000}
                  value={leg.elevation_gain_m || ''}
                  onChange={(e) => {
                    updateLeg(i, { elevation_gain_m: Number.parseInt(e.target.value, 10) || 0 })
                  }}
                  required
                />
              </div>
            </div>
            {errors[`legs.${String(i)}.discipline`]?.[0] && (
              <p className="text-destructive mt-1 text-xs">
                {errors[`legs.${String(i)}.discipline`][0]}
              </p>
            )}
          </div>
        ))}

        <p className="text-muted-foreground border-t pt-2 text-xs">
          Total :{' '}
          <strong>
            {totals.total_distance_km.toFixed(1)} km · {String(totals.total_elevation_gain_m)} m D+
          </strong>
        </p>

        {errors.legs?.[0] && <p className="text-destructive text-xs">{errors.legs[0]}</p>}
      </div>

      <Button type="submit" disabled={loading} className="w-full">
        {loading ? 'Sauvegarde...' : 'Suivant'}
      </Button>
    </form>
  )
}
```

- [ ] **Step 2: Quality gates**

```bash
cd /home/tellebma/DEV/garmin_training
pnpm typecheck && pnpm lint
```
Expected: clean.

- [ ] **Step 3: Build smoke**

```bash
pnpm build
```
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add app/'(app)'/onboarding/_components/step-race-form.tsx
git commit -m "feat(race): wizard step 2 — discipline parent + legs with auto-generation"
```

---

## Task 5 — UI `race-edit-form.tsx` (/profile section Course) refactor

**Files:**
- Modify: `app/(app)/profile/_components/race-edit-form.tsx`

- [ ] **Step 1: Read current race-edit-form.tsx**

```bash
cat /home/tellebma/DEV/garmin_training/app/'(app)'/profile/_components/race-edit-form.tsx
```
Note les sections actuelles : view-mode + edit-mode + null-safe "Ajouter".

- [ ] **Step 2: Replace `race-edit-form.tsx` complete content**

```typescript
'use client'

import { useEffect, useState } from 'react'
import Link from 'next/link'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { saveStepRace } from '@/app/(app)/onboarding/actions'
import {
  PARENT_DISCIPLINES,
  LEG_RULES,
  computeTotals,
  type Leg,
  type RaceInput,
} from '@/lib/onboarding/schemas'

interface Props {
  initial: RaceInput | null
}

const PARENT_LABEL: Record<(typeof PARENT_DISCIPLINES)[number], string> = {
  triathlon: 'Triathlon',
  duathlon: 'Duathlon',
  aquathlon: 'Aquathlon',
  run: 'Course (route ou trail)',
  bike: 'Vélo',
  swim: 'Natation',
  autre: 'Autre / personnalisé',
}

const LEG_ICON: Record<'swim' | 'bike' | 'run', string> = {
  swim: '🏊',
  bike: '🚴',
  run: '🏃',
}

const LEG_NAME: Record<'swim' | 'bike' | 'run', string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
}

function defaultLegsFor(discipline: (typeof PARENT_DISCIPLINES)[number]): Leg[] {
  const rule = LEG_RULES[discipline]
  if (rule.sequence) {
    return rule.sequence.map((d, i) => ({
      order: i + 1,
      discipline: d,
      distance_km: 0,
      elevation_gain_m: 0,
    }))
  }
  return [{ order: 1, discipline: 'run', distance_km: 0, elevation_gain_m: 0 }]
}

function hmsToSeconds(hms: string): number {
  const [h, m, s] = hms.split(':').map((n) => Number.parseInt(n, 10))
  return h * 3600 + m * 60 + s
}

function secondsToHms(total: number): string {
  const h = Math.floor(total / 3600)
  const m = Math.floor((total % 3600) / 60)
  const s = total % 60
  return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
}

function RaceSummary({ race }: Readonly<{ race: RaceInput }>) {
  const totals = computeTotals(race.legs)
  return (
    <>
      <div className="text-sm font-medium">
        {race.name ?? PARENT_LABEL[race.discipline]} · {race.race_date}
      </div>
      <div className="text-muted-foreground mt-1 flex flex-wrap items-center gap-2 text-xs">
        {race.legs.map((l, i) => (
          <span key={`${String(l.order)}-${l.discipline}`} className="inline-flex items-center gap-1">
            {LEG_ICON[l.discipline]} {l.distance_km} km · {String(l.elevation_gain_m)} m
            {i < race.legs.length - 1 && <span className="mx-1">→</span>}
          </span>
        ))}
      </div>
      <div className="text-muted-foreground mt-2 text-xs">
        Total : <strong>{totals.total_distance_km.toFixed(1)} km · {String(totals.total_elevation_gain_m)} m D+</strong>
        {race.target_time_seconds && (
          <span> · Cible : {secondsToHms(race.target_time_seconds)}</span>
        )}
      </div>
    </>
  )
}

export function RaceEditForm({ initial }: Readonly<Props>) {
  const [edit, setEdit] = useState(false)
  const [race_date, setRaceDate] = useState(initial?.race_date ?? '')
  const [discipline, setDiscipline] = useState<(typeof PARENT_DISCIPLINES)[number]>(
    initial?.discipline ?? 'triathlon'
  )
  const [name, setName] = useState(initial?.name ?? '')
  const [location, setLocation] = useState(initial?.location ?? '')
  const [targetHms, setTargetHms] = useState(
    initial?.target_time_seconds ? secondsToHms(initial.target_time_seconds) : ''
  )
  const [legs, setLegs] = useState<Leg[]>(initial?.legs ?? defaultLegsFor('triathlon'))
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!edit) return
    if (discipline === 'autre') return
    setLegs((prev) => {
      // Preserve user-entered values if leg structure matches; else reset
      const matches = LEG_RULES[discipline].sequence?.every((d, i) => prev[i]?.discipline === d)
      return matches ? prev : defaultLegsFor(discipline)
    })
  }, [discipline, edit])

  const isAutre = discipline === 'autre'
  const totals = computeTotals(legs)

  function updateLeg(index: number, patch: Partial<Leg>) {
    setLegs((prev) => prev.map((l, i) => (i === index ? { ...l, ...patch } : l)))
  }

  function addLeg() {
    setLegs((prev) => [
      ...prev,
      { order: prev.length + 1, discipline: 'run', distance_km: 0, elevation_gain_m: 0 },
    ])
  }

  function removeLeg(index: number) {
    setLegs((prev) => prev.filter((_, i) => i !== index).map((l, i) => ({ ...l, order: i + 1 })))
  }

  async function handleSave() {
    setLoading(true)
    const target_time_seconds = targetHms ? hmsToSeconds(targetHms) : undefined
    const r = await saveStepRace({
      race_date,
      discipline,
      name: name || undefined,
      location: location || undefined,
      target_time_seconds,
      legs,
    })
    setLoading(false)
    if (!r.success) {
      toast.error('Erreur de sauvegarde')
      return
    }
    setEdit(false)
    toast.success('Sauvegardé')
  }

  // View-mode
  if (!edit) {
    return (
      <section className="space-y-3 rounded-lg border p-6">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Course cible</h2>
          {initial ? (
            <Button variant="outline" size="sm" onClick={() => { setEdit(true) }}>
              Modifier
            </Button>
          ) : (
            <Button asChild variant="outline" size="sm">
              <Link href="/onboarding">Ajouter</Link>
            </Button>
          )}
        </div>
        {initial ? (
          <RaceSummary race={initial} />
        ) : (
          <p className="text-muted-foreground text-sm">Pas de course définie.</p>
        )}
      </section>
    )
  }

  // Edit-mode
  return (
    <section className="space-y-4 rounded-lg border p-6">
      <h2 className="text-lg font-semibold">Course cible — édition</h2>

      <div className="space-y-2">
        <Label htmlFor="re-race_date">Date</Label>
        <Input
          id="re-race_date"
          type="date"
          value={race_date}
          onChange={(e) => { setRaceDate(e.target.value) }}
        />
      </div>

      <div className="space-y-2">
        <Label htmlFor="re-discipline">Type</Label>
        <select
          id="re-discipline"
          value={discipline}
          onChange={(e) => {
            setDiscipline(e.target.value as (typeof PARENT_DISCIPLINES)[number])
          }}
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
        >
          {PARENT_DISCIPLINES.map((d) => (
            <option key={d} value={d}>{PARENT_LABEL[d]}</option>
          ))}
        </select>
      </div>

      <div className="space-y-2">
        <Label htmlFor="re-name">Nom</Label>
        <Input id="re-name" value={name} onChange={(e) => { setName(e.target.value) }} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="re-location">Lieu</Label>
        <Input id="re-location" value={location} onChange={(e) => { setLocation(e.target.value) }} />
      </div>

      <div className="space-y-2">
        <Label htmlFor="re-target">Temps cible (hh:mm:ss)</Label>
        <Input
          id="re-target"
          value={targetHms}
          onChange={(e) => { setTargetHms(e.target.value) }}
          placeholder="05:30:00"
        />
      </div>

      <div className="space-y-3 rounded-md border p-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold">Segments</h3>
          {isAutre && (
            <Button type="button" variant="outline" size="sm" onClick={addLeg} disabled={legs.length >= 10}>
              + Ajouter
            </Button>
          )}
        </div>
        {legs.map((leg, i) => (
          <div key={`${String(leg.order)}-${leg.discipline}-${String(i)}`} className="rounded-md border p-3">
            <div className="mb-2 flex items-center justify-between">
              <div className="flex items-center gap-2 text-sm">
                <span>{String(i + 1)}.</span>
                {isAutre ? (
                  <select
                    value={leg.discipline}
                    onChange={(e) => {
                      updateLeg(i, { discipline: e.target.value as 'swim' | 'bike' | 'run' })
                    }}
                    className="border-input bg-background h-8 rounded-md border px-2 text-sm"
                  >
                    {(['swim', 'bike', 'run'] as const).map((d) => (
                      <option key={d} value={d}>{LEG_ICON[d]} {LEG_NAME[d]}</option>
                    ))}
                  </select>
                ) : (
                  <span>{LEG_ICON[leg.discipline]} {LEG_NAME[leg.discipline]}</span>
                )}
              </div>
              {isAutre && legs.length > 1 && (
                <Button type="button" variant="ghost" size="sm" onClick={() => { removeLeg(i) }}>
                  − Retirer
                </Button>
              )}
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <Label className="text-xs" htmlFor={`re-leg-${String(i)}-d`}>Distance (km)</Label>
                <Input
                  id={`re-leg-${String(i)}-d`}
                  type="number"
                  step="0.01"
                  min={0}
                  max={1000}
                  value={leg.distance_km || ''}
                  onChange={(e) => {
                    updateLeg(i, { distance_km: Number.parseFloat(e.target.value) || 0 })
                  }}
                />
              </div>
              <div>
                <Label className="text-xs" htmlFor={`re-leg-${String(i)}-e`}>D+ (m)</Label>
                <Input
                  id={`re-leg-${String(i)}-e`}
                  type="number"
                  step="1"
                  min={0}
                  max={20000}
                  value={leg.elevation_gain_m || ''}
                  onChange={(e) => {
                    updateLeg(i, { elevation_gain_m: Number.parseInt(e.target.value, 10) || 0 })
                  }}
                />
              </div>
            </div>
          </div>
        ))}
        <p className="text-muted-foreground border-t pt-2 text-xs">
          Total : <strong>{totals.total_distance_km.toFixed(1)} km · {String(totals.total_elevation_gain_m)} m D+</strong>
        </p>
      </div>

      <div className="flex gap-2">
        <Button onClick={() => { void handleSave() }} disabled={loading}>
          {loading ? 'Sauvegarde...' : 'Enregistrer'}
        </Button>
        <Button variant="outline" onClick={() => { setEdit(false) }} disabled={loading}>
          Annuler
        </Button>
      </div>
    </section>
  )
}
```

- [ ] **Step 3: Vérifier que `app/(app)/profile/page.tsx` passe bien un `RaceInput` (avec `discipline + legs`) à `RaceEditForm`**

```bash
cd /home/tellebma/DEV/garmin_training
grep -n "RaceEditForm\|raceInitial" app/'(app)'/profile/page.tsx
```

L'ancien code passe `race_distance` (enum) et pas `legs`. Il faut update `page.tsx` pour lire les nouvelles colonnes :

Patch `app/(app)/profile/page.tsx` :

```typescript
// Replace interface RaceGoalRow:
interface RaceGoalRow {
  race_date: string
  discipline: 'triathlon' | 'duathlon' | 'aquathlon' | 'run' | 'bike' | 'swim' | 'autre'
  name: string | null
  location: string | null
  target_time_seconds: number | null
  legs: Array<{ order: number; discipline: 'swim' | 'bike' | 'run'; distance_km: number; elevation_gain_m: number }>
}

// Replace the SELECT for race:
supabase
  .from('race_goals')
  .select('race_date, discipline, name, location, target_time_seconds, legs')
  .eq('user_id', userId)
  .eq('is_primary', true)
  .maybeSingle<RaceGoalRow>(),

// Replace raceInitial:
const raceInitial: RaceInput | null = race
  ? {
      race_date: race.race_date,
      discipline: race.discipline,
      name: race.name ?? undefined,
      location: race.location ?? undefined,
      target_time_seconds: race.target_time_seconds ?? undefined,
      legs: race.legs,
    }
  : null
```

- [ ] **Step 4: Quality gates + build**

```bash
pnpm typecheck && pnpm lint && pnpm build
```
Expected: clean. Build doit afficher `/profile` et `/onboarding` dans le routing.

- [ ] **Step 5: Commit**

```bash
git add app/'(app)'/profile/_components/race-edit-form.tsx app/'(app)'/profile/page.tsx
git commit -m "feat(race): /profile race section reads + edits legs structure"
```

---

## Task 6 — Push + open PR

- [ ] **Step 1: Full quality gates locally**

```bash
cd /home/tellebma/DEV/garmin_training
pnpm test --run
pnpm typecheck && pnpm lint && pnpm build
```
Expected: tous verts. Tests : ~30+ tests Zod (16 existants + 14 nouveaux raceSchema/computeTotals).

- [ ] **Step 2: Push branch**

```bash
git push -u origin feat/race-profile-v2
```

- [ ] **Step 3: Open PR**

```bash
gh pr create --base main --head feat/race-profile-v2 \
  --title "feat(race): race profile v2 — multi-discipline + per-leg elevation" \
  --body "$(cat <<'EOF'
## Contexte

Évolution du modèle \`race_goals\` (livré dans E3) pour supporter tout type de course avec dénivelé par segment.

- **Spec** : [\`docs/superpowers/specs/2026-05-19-race-profile-design.md\`](./docs/superpowers/specs/2026-05-19-race-profile-design.md)
- **Plan** : [\`docs/superpowers/plans/2026-05-19-race-profile.md\`](./docs/superpowers/plans/2026-05-19-race-profile.md)

## Changements

### Database
- Migration breaking (vérifié vide en prod) : \`race_distance\` enum → \`discipline\` parent ('triathlon','duathlon','aquathlon','run','bike','swim','autre')
- 3 nouvelles colonnes : \`total_distance_km\`, \`total_elevation_gain_m\`, \`legs jsonb\`

### Frontend
- Zod \`raceSchema\` refactor avec \`superRefine\` + \`LEG_RULES\` (invariants par parent)
- Helper \`computeTotals\` (somme legs)
- Server Action \`saveStepRace\` recompute totals avant upsert (defense in depth)
- \`step-race-form.tsx\` : select discipline auto-génère N legs, support \`autre\` (1-10 legs avec add/remove + select discipline par leg)
- \`race-edit-form.tsx\` : même structure que wizard + view-mode compact chevron \`🏊 1.4 km · 0 m → 🚴 53 km · 2200 m → 🏃 8 km · 200 m\`

### Tests
- ~14 nouveaux tests Vitest : Zod (triathlon valide, mauvaise séquence, run avec leg bike, autre 11 legs, etc.) + computeTotals

## Pas mergé jusqu'à validation

Cette migration est **breaking** sur \`race_goals\`. Vérifié vide en prod (count=0 au moment de la rédaction). Si une race est insérée entre maintenant et le merge, elle perdrait son \`race_distance\` (rename → \`discipline\`).
EOF
)"
```

- [ ] **Step 4: Wait for CI + final review**

```bash
gh pr checks
```
Expected: all green.

---

## Quality gates de référence

| Couche | Commande | Doit retourner |
|---|---|---|
| Frontend lint | `pnpm lint` | 0 errors |
| Frontend types | `pnpm typecheck` | 0 errors |
| Frontend tests | `pnpm test --run` | All passed (~30+) |
| Frontend build | `pnpm build` | Compiled successfully |

---

## Cas d'erreur fréquents (anticipés)

| Symptôme | Cause probable | Fix |
|---|---|---|
| `pnpm typecheck` : `RACE_DISTANCES` not found | Ancien import oublié dans un fichier | Le grep step 2 task 2 doit signaler ; nettoyer tous les usages |
| Test triathlon valide → fail | Probablement `LEG_RULES.sequence` mal ordonnée | Vérifier : `['swim','bike','run']` exact |
| Wizard wizard step 2 : changement discipline ne reset pas les legs | useEffect dépendance manquante | Bien avoir `useEffect(() => {...}, [discipline])` |
| `useEffect` infini en `autre` | useEffect modifie legs qui re-render | La garde `if (discipline === 'autre') return` doit être la 1ère ligne |
| `computeTotals` retourne `NaN` | `distance_km` vide en string | `Number.parseFloat(e.target.value) \|\| 0` dans onChange |
| Migration error : `race_distance` column doesn't exist | Migration appliquée 2 fois OU table déjà migrée | Vérifier `\d race_goals` dans Supabase ; si déjà OK, `git rev-parse HEAD` et marquer task 1 done |
| `/profile` crash : `legs is undefined` | Race existante en DB avec \`legs = '[]'::jsonb\` (defaut migration) | OK car table était vide ; sinon backfill via `update race_goals set legs = '[...]' where ...` |
