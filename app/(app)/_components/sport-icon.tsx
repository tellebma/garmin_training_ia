// app/(app)/_components/sport-icon.tsx
import {
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
}

export const SPORT_LABEL: Record<Sport, string> = {
  swim: 'Natation',
  bike: 'Vélo',
  run: 'Course',
  brick: 'Brick',
  rest: 'Repos',
  race: 'Jour J',
}

export const SESSION_TYPE_LABEL: Record<SessionType, string> = {
  endurance: 'Endurance',
  threshold: 'Seuil',
  intervals: 'Intervalles',
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
  const Icon = SPORT_ICON[sport]
  return <Icon size={size} className={className} aria-label={SPORT_LABEL[sport]} />
}
