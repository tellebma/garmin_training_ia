'use client'

import { useState } from 'react'
import { Bell } from 'lucide-react'
import { markChangelogSeen } from '@/app/actions/changelog'
import type { ChangelogEntry } from '@/lib/changelog/parse'
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
  SheetTrigger,
} from '@/components/ui/sheet'

const MAX_VISIBLE_ENTRIES = 5

interface ChangelogBellProps {
  entries: ChangelogEntry[]
  latestVersion: string | null
  initialLastSeenVersion: string | null
}

export function ChangelogBell({
  entries,
  latestVersion,
  initialLastSeenVersion,
}: Readonly<ChangelogBellProps>) {
  const [lastSeenVersion, setLastSeenVersion] = useState(initialLastSeenVersion)
  const hasUnread = latestVersion !== null && latestVersion !== lastSeenVersion
  const visibleEntries = entries.slice(0, MAX_VISIBLE_ENTRIES)

  function onOpenChange(open: boolean) {
    if (open && latestVersion && latestVersion !== lastSeenVersion) {
      setLastSeenVersion(latestVersion)
      void markChangelogSeen(latestVersion)
    }
  }

  return (
    <Sheet onOpenChange={onOpenChange}>
      <SheetTrigger asChild>
        <button
          type="button"
          aria-label="Nouveautés"
          className="relative rounded-md border p-2 text-sm"
        >
          <Bell size={16} aria-hidden="true" />
          {hasUnread && (
            <span
              data-testid="changelog-unread-dot"
              className="absolute -top-0.5 -right-0.5 h-2 w-2 rounded-full bg-red-500"
            />
          )}
        </button>
      </SheetTrigger>
      <SheetContent side="right">
        <SheetHeader>
          <SheetTitle>Nouveautés</SheetTitle>
          <SheetDescription>Les dernières améliorations de l&rsquo;app.</SheetDescription>
        </SheetHeader>
        <div className="mt-4 space-y-6 px-4">
          {visibleEntries.map((entry) => (
            <div key={entry.version}>
              <p className="text-sm font-semibold">
                {entry.version}{' '}
                <span className="text-muted-foreground font-normal">— {entry.date}</span>
              </p>
              <ul className="text-muted-foreground mt-2 list-disc space-y-1 pl-4 text-sm">
                {entry.bullets.map((bullet) => (
                  <li key={bullet}>{bullet}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
      </SheetContent>
    </Sheet>
  )
}
