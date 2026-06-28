import type { ActivitySample } from '@/lib/coach/activity-analysis'
import type { Sport } from '@/lib/dashboard/types'
import { paceUnitForSport, speedToSportValue } from '@/lib/dashboard/format'

export type MetricKey = 'heart_rate_bpm' | 'elevation_m' | 'power_w' | 'cadence_rpm' | 'speed'

export interface MetricDescriptor {
  key: MetricKey
  name: string
  unit: string
  color: string
  inverted: boolean
}

export interface ChartPoint {
  x: number
  heart_rate_bpm: number | null
  elevation_m: number | null
  power_w: number | null
  cadence_rpm: number | null
  speed: number | null
}

export function hasDistance(samples: ActivitySample[]): boolean {
  return samples.some((s) => typeof s.distance_m === 'number')
}

function hasSampleMetric(samples: ActivitySample[], key: keyof ActivitySample): boolean {
  return samples.some((s) => typeof s[key] === 'number')
}

export function availableMetrics(samples: ActivitySample[], sport: Sport): MetricDescriptor[] {
  const descriptors: MetricDescriptor[] = []
  if (hasSampleMetric(samples, 'heart_rate_bpm')) {
    descriptors.push({
      key: 'heart_rate_bpm',
      name: 'FC',
      unit: 'bpm',
      color: 'var(--chart-1)',
      inverted: false,
    })
  }
  if (hasSampleMetric(samples, 'elevation_m')) {
    descriptors.push({
      key: 'elevation_m',
      name: 'Altitude',
      unit: 'm',
      color: 'var(--chart-2)',
      inverted: false,
    })
  }
  if (hasSampleMetric(samples, 'power_w')) {
    descriptors.push({
      key: 'power_w',
      name: 'Puissance',
      unit: 'W',
      color: 'var(--chart-3)',
      inverted: false,
    })
  }
  if (hasSampleMetric(samples, 'cadence_rpm')) {
    descriptors.push({
      key: 'cadence_rpm',
      name: 'Cadence',
      unit: 'rpm',
      color: 'var(--chart-4)',
      inverted: false,
    })
  }
  if (hasSampleMetric(samples, 'speed_m_s')) {
    const unit = paceUnitForSport(sport)
    descriptors.push({
      key: 'speed',
      name: unit === 'km/h' ? 'Vitesse' : 'Allure',
      unit,
      color: 'var(--chart-5)',
      inverted: unit !== 'km/h',
    })
  }
  return descriptors
}

export function buildChartData(
  samples: ActivitySample[],
  sport: Sport,
  xBasis: 'time' | 'distance'
): ChartPoint[] {
  return samples.map((s, index) => {
    let x: number
    if (xBasis === 'distance' && typeof s.distance_m === 'number') {
      x = s.distance_m / 1000
    } else if (typeof s.elapsed_s === 'number') {
      x = s.elapsed_s / 60
    } else {
      x = index
    }
    return {
      x,
      heart_rate_bpm: s.heart_rate_bpm,
      elevation_m: s.elevation_m,
      power_w: s.power_w,
      cadence_rpm: s.cadence_rpm,
      speed: speedToSportValue(sport, s.speed_m_s),
    }
  })
}
