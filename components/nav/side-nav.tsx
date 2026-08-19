'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import {
  Activity,
  CalendarDays,
  History,
  LineChart,
  MessageCircle,
  Shield,
  User,
} from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { cn } from '@/lib/utils'

interface NavItem {
  href: string
  label: string
  icon: LucideIcon
}

const items: NavItem[] = [
  { href: '/today', label: "Aujourd'hui", icon: Activity },
  { href: '/plan', label: 'Plan', icon: CalendarDays },
  { href: '/coach', label: 'Coach', icon: MessageCircle },
  { href: '/stats', label: 'Stats', icon: LineChart },
  { href: '/history', label: 'Historique', icon: History },
  { href: '/profile', label: 'Profil', icon: User },
]

const adminItem: NavItem = { href: '/admin', label: 'Admin', icon: Shield }

export function SideNav({ isAdmin = false }: { readonly isAdmin?: boolean }) {
  const pathname = usePathname()
  const allItems = isAdmin ? [...items, adminItem] : items
  return (
    <aside className="fixed inset-y-0 left-0 hidden w-64 flex-col border-r md:flex">
      <div className="px-6 py-6">
        <h1 className="text-lg font-semibold">Garmin Coach</h1>
      </div>
      <nav className="flex-1 px-3">
        <ul className="space-y-1">
          {allItems.map((item) => {
            const active = pathname === item.href
            const Icon = item.icon
            return (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={cn(
                    'flex items-center gap-2 rounded-md px-3 py-2 text-sm',
                    active
                      ? 'bg-accent text-accent-foreground'
                      : 'text-muted-foreground hover:bg-accent/50'
                  )}
                >
                  <Icon size={16} aria-hidden="true" />
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
