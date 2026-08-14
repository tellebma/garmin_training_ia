// app/(app)/_components/sport-icon.tsx
import {
  Activity,
  Waves,
  Bike,
  Footprints,
  RotateCw,
  MinusCircle,
  Trophy,
  type LucideIcon,
} from 'lucide-react'
import type { Sport, SessionType, Phase } from '@/lib/dashboard/types'

export const SPORT_ICON: Record<Sport, LucideIcon> = {
  swim: Waves,
  bike: Bike,
  run: Footprints,
  brick: RotateCw,
  rest: MinusCircle,
  race: Trophy,
  triathlon: Trophy,
  duathlon: Trophy,
  aquathlon: Trophy,
}

export const SPORT_LABEL: Record<Sport, string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
  brick: 'Brick',
  rest: 'Repos',
  race: 'Jour J',
  triathlon: 'Triathlon',
  duathlon: 'Duathlon',
  aquathlon: 'Aquathlon',
}

// Un sport inconnu (valeur ajoutée en base avant le front, cf. la migration
// multisport) ne doit jamais faire planter le rendu : sans ce garde-fou,
// `<Icon />` avec un composant `undefined` casse toute la page (page blanche
// sur /plan). Les vues partielles forcent un lookup tolérant tout en gardant
// l'exhaustivité des maps ci-dessus.
const SPORT_ICON_LOOSE: Partial<Record<string, LucideIcon>> = SPORT_ICON
const SPORT_LABEL_LOOSE: Partial<Record<string, string>> = SPORT_LABEL

export function sportLabelFor(sport: string): string {
  return SPORT_LABEL_LOOSE[sport] ?? sport
}

export const SESSION_TYPE_LABEL: Record<SessionType, string> = {
  endurance: 'Endurance',
  threshold: 'Seuil',
  intervals: 'Intervalles',
  pma: 'PMA',
  sprint: 'Sprint',
  strides: 'Côtes & accélérations',
  long: 'Sortie longue',
  recovery: 'Récupération',
  race: 'Course',
  rest: 'Repos',
}

export const PHASE_LABEL: Record<Phase, string> = {
  base: 'Base',
  build: 'Build',
  peak: 'Peak',
  taper: 'Taper',
  race: 'Jour J',
}

interface SportIconProps {
  sport: Sport
  className?: string
  size?: number
}

export function SportIcon({ sport, className, size = 20 }: Readonly<SportIconProps>) {
  const Icon = SPORT_ICON_LOOSE[sport] ?? Activity
  return <Icon size={size} className={className} aria-label={sportLabelFor(sport)} />
}
