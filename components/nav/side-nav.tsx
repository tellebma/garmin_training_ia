'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

const items = [
  { href: '/today', label: 'Aujourd’hui' },
  { href: '/plan', label: 'Plan' },
  { href: '/stats', label: 'Stats' },
  { href: '/profile', label: 'Profil' },
]

export function SideNav() {
  const pathname = usePathname()
  return (
    <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r md:flex">
      <div className="px-6 py-6">
        <h1 className="text-lg font-semibold">Garmin Coach</h1>
      </div>
      <nav className="flex-1 px-3">
        <ul className="space-y-1">
          {items.map((item) => {
            const active = pathname === item.href
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    'block rounded-md px-3 py-2 text-sm',
                    active
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent/50'
                  )}
                >
                  {item.label}
                </Link>
              </li>
            )
          })}
        </ul>
      </nav>
    </aside>
  )
}
