'use client'

import { useState } from 'react'
import { useRouter } from 'next/navigation'
import { ConnectForm } from '@/components/garmin/connect-form'
import { MfaForm } from '@/components/garmin/mfa-form'
import { Toaster } from '@/components/ui/sonner'

type Stage = { kind: 'form' } | { kind: 'mfa'; challengeId: string }

export default function GarminConnectPage() {
  const router = useRouter()
  const [stage, setStage] = useState<Stage>({ kind: 'form' })

  function handleConnected() {
    router.push('/profile?garmin=connected')
    router.refresh()
  }

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold">Connecter Garmin</h1>
        <p className="text-muted-foreground text-sm">
          Tes identifiants Garmin sont envoyés au serveur via HTTPS, utilisés une seule fois pour
          obtenir un token OAuth, puis effacés. Seul le token est conservé, chiffré.
        </p>
      </header>
      <section className="rounded-lg border p-6">
        {stage.kind === 'form' ? (
          <ConnectForm
            onMfaRequired={(challengeId) => {
              setStage({ kind: 'mfa', challengeId })
            }}
            onConnected={handleConnected}
          />
        ) : (
          <MfaForm
            challengeId={stage.challengeId}
            onConnected={handleConnected}
            onCancel={() => {
              setStage({ kind: 'form' })
            }}
          />
        )}
      </section>
      <Toaster />
    </div>
  )
}
