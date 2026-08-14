'use client'

import dynamic from 'next/dynamic'

const RoutesFrequencyMap = dynamic(
  () => import('./routes-frequency-map').then((m) => m.RoutesFrequencyMap),
  { ssr: false }
)

interface RoutesFrequencyMapLazyProps {
  readonly polylines: unknown[]
}

export function RoutesFrequencyMapLazy({ polylines }: RoutesFrequencyMapLazyProps) {
  return <RoutesFrequencyMap polylines={polylines} />
}
