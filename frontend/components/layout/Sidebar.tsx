'use client'

import Image from 'next/image'
import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'
import type { User } from '@/types'
import {
  IconDashboard,
  IconPalette,
  IconFileText,
  IconFilm,
  IconShield,
  IconTrending,
  IconRocket,
  IconSettings,
  IconLogOut,
  IconSparkles,
} from '@/components/ui/icons'

interface NavItem {
  href: string
  icon: React.ReactNode
  label: string
  badge?: number
}

const workspaceNav: NavItem[] = [
  { href: '/dashboard', icon: <IconDashboard />, label: 'Dashboard' },
  { href: '/brand-kit', icon: <IconPalette />, label: 'Brand Kit' },
  { href: '/briefs', icon: <IconFileText />, label: 'Briefs' },
  { href: '/variants', icon: <IconFilm />, label: 'Variants' },
  { href: '/brand-safety', icon: <IconShield />, label: 'Brand Safety' },
]

const performanceNav: NavItem[] = [
  { href: '/performance', icon: <IconTrending />, label: 'Performance' },
  { href: '/export', icon: <IconRocket />, label: 'Export to Meta' },
]

const accountNav: NavItem[] = [{ href: '/admin', icon: <IconSettings />, label: 'Admin' }]

function NavSection({ title, items }: { title: string; items: NavItem[] }) {
  const pathname = usePathname()
  return (
    <div className="mb-2">
      <div className="px-4 pt-5 pb-2 text-[10px] font-bold text-subtle/90 uppercase tracking-[0.14em]">
        {title}
      </div>
      <div className="space-y-0.5 px-2">
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link
              key={item.href}
              href={item.href}
              className={cn(
                'relative flex items-center gap-3 px-3 py-2.5 rounded-xl text-[13px] font-medium transition-all duration-200 ease-premium',
                active
                  ? 'nav-item-active text-white pl-4'
                  : 'text-subtle hover:text-white hover:bg-white/[0.06]'
              )}
            >
              <span className={cn(active ? 'text-accent' : 'text-subtle')}>{item.icon}</span>
              <span className="flex-1">{item.label}</span>
              {item.badge ? (
                <span className="bg-accent text-white text-[9px] font-bold px-2 py-0.5 rounded-full shadow-glow">
                  {item.badge}
                </span>
              ) : null}
            </Link>
          )
        })}
      </div>
    </div>
  )
}

interface SidebarProps {
  user: User
  brandName?: string
  /** Human-readable line under brand name (agency type). */
  brandSubtitle?: string
  onLogout(): void
}

export default function Sidebar({ user, brandName, brandSubtitle, onLogout }: SidebarProps) {
  return (
    <aside className="hidden md:flex w-[260px] flex-shrink-0 flex-col h-screen sticky top-0 z-30 bg-sidebar shadow-sidebar border-r border-white/[0.06]">
      {/* Logo */}
      <div className="px-5 py-5 border-b border-white/[0.08]">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-accent-gradient flex items-center justify-center shadow-glow">
            <IconSparkles className="w-4 h-4 text-white" />
          </div>
          <div>
            <div className="text-[15px] font-bold text-white tracking-tight leading-tight">
              Creative<span className="text-accent">Studio</span>
            </div>
            <div className="text-[10px] text-subtle mt-0.5 font-medium">AI Creative Engine</div>
          </div>
        </div>

        <div className="mt-4 pt-4 border-t border-white/[0.08]">
          <p className="text-[9px] font-semibold text-subtle/90 uppercase tracking-[0.12em] mb-2">
            Powered by
          </p>
          <div className="rounded-xl bg-white px-3 py-2.5 shadow-soft">
            <Image
              src="/traffic-radius-logo.png"
              alt="Traffic Radius"
              width={200}
              height={48}
              className="h-10 w-auto max-w-full object-contain object-left"
              priority
            />
          </div>
        </div>
      </div>

      {/* Brand */}
      {brandName && (
        <div className="mx-3 mt-4 px-4 py-3.5 rounded-2xl bg-white/[0.06] border border-white/[0.1] backdrop-blur-sm">
          <p className="text-[9px] font-semibold text-subtle/90 uppercase tracking-[0.12em] mb-2">
            Active brand
          </p>
          <p className="text-[15px] font-bold text-white tracking-tight truncate leading-tight">{brandName}</p>
          {brandSubtitle ? (
            <p className="text-[11px] text-subtle/95 mt-1.5 leading-snug truncate">{brandSubtitle}</p>
          ) : (
            <p className="text-[11px] text-subtle/70 mt-1.5 italic">Complete your brand kit</p>
          )}
        </div>
      )}

      <nav className="flex-1 overflow-y-auto py-2">
        <NavSection title="Workspace" items={workspaceNav} />
        <NavSection title="Performance" items={performanceNav} />
        <NavSection title="Account" items={accountNav} />
      </nav>

      {/* User */}
      <div className="border-t border-white/[0.08] p-4 m-3 mt-0 rounded-2xl bg-white/[0.04]">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-br from-accent to-success flex items-center justify-center text-sm font-bold text-white shadow-soft flex-shrink-0">
            {user.full_name.charAt(0).toUpperCase()}
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-white truncate">{user.full_name}</div>
            <div className="text-[11px] text-subtle capitalize">{user.role}</div>
          </div>
          <button
            onClick={onLogout}
            title="Sign out"
            className="text-subtle hover:text-white transition-colors p-2 rounded-xl hover:bg-white/[0.08]"
          >
            <IconLogOut />
          </button>
        </div>
      </div>
    </aside>
  )
}
