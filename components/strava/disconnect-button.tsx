'use client'

import { useRouter } from 'next/navigation'
import { disconnectStrava } from '@/app/actions/strava-auth'
import { Button } from '@/components/ui/button'

export function StravaDisconnectButton() {
  const router = useRouter()

  async function handleDisconnect() {
    await disconnectStrava()
    router.refresh()
  }

  return (
    <Button
      variant="outline"
      onClick={() => {
        void handleDisconnect()
      }}
    >
      Déconnecter Strava
    </Button>
  )
}
