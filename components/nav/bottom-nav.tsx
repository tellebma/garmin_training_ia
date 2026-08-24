'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { Activity, CalendarDays, History, LineChart, MessageCircle, User } from 'lucide-react'
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

export function BottomNav() {
  const pathname = usePathname()
  return (
    <nav className="bg-background fixed inset-x-0 bottom-0 z-10 border-t md:hidden">
      <ul className="grid grid-cols-5">
        {items.map((item) => {
          const active = pathname === item.href
          const Icon = item.icon
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                className={cn(
                  'flex h-16 flex-col items-center justify-center gap-1 text-[10px]',
                  active ? 'text-foreground font-medium' : 'text-muted-foreground'
                )}
              >
                <Icon size={20} aria-hidden="true" />
                {item.label}
              </Link>
            </li>
          )
        })}
      </ul>
    </nav>
  )
}
