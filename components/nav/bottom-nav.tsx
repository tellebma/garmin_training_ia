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

export function BottomNav() {
  const pathname = usePathname()
  return (
    <nav className="bg-background fixed inset-x-0 bottom-0 z-10 border-t md:hidden">
      <ul className="grid grid-cols-4">
        {items.map((item) => {
          const active = pathname === item.href
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  'flex h-16 items-center justify-center text-xs',
                  active ? 'text-foreground font-medium' : 'text-muted-foreground'
                )}
              >
                {item.label}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
