import type { Metadata } from 'next'
import { requireOnboarded } from '@/lib/onboarding/guard'
import { ChatPanel } from '../_components/chat-panel'

export const metadata: Metadata = {
  title: 'Coach',
}

export default async function CoachPage() {
  await requireOnboarded()

  return (
    <main className="mx-auto flex w-full max-w-2xl flex-col gap-4 p-4 pb-28 md:pb-8">
      <header>
        <h1 className="text-2xl font-semibold">Coach</h1>
        <p className="text-muted-foreground text-sm">
          Tes questions d&apos;entraînement, replacées dans tes données.
        </p>
      </header>
      <ChatPanel />
    </main>
  )
}
