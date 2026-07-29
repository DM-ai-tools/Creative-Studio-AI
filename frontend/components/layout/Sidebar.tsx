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
  IconHistory,
} from '@/components/ui/icons'

interface NavItem {
  href: string
  icon: React.ReactNode
  label: string
}

const workspaceNav: NavItem[] = [
  { href: '/dashboard', icon: <IconDashboard />, label: 'Dashboard' },
  { href: '/brand-kit', icon: <IconPalette />, label: 'Brand Kit' },
  { href: '/briefs', icon: <IconFileText />, label: 'Briefs' },
  { href: '/variants', icon: <IconFilm />, label: 'Variants' },
  { href: '/history', icon: <IconHistory />, label: 'History' },
  { href: '/brand-safety', icon: <IconShield />, label: 'Brand Safety' },
]

const performanceNav: NavItem[] = [
  { href: '/performance', icon: <IconTrending />, label: 'Performance' },
  { href: '/export', icon: <IconRocket />, label: 'Export to Meta' },
]

const accountNav: NavItem[] = [
  { href: '/admin', icon: <IconSettings />, label: 'Admin' },
]

const allNav = [...workspaceNav, ...performanceNav, ...accountNav]

function NavGroup({
  title,
  items,
  collapsed,
}: {
  title: string
  items: NavItem[]
  collapsed?: boolean
}) {
  const pathname = usePathname()
  return (
    <div>
      {!collapsed && (
        <p className="px-3 pt-4 pb-1.5 text-[10px] font-semibold uppercase tracking-[0.12em] text-white/30 select-none">
          {title}
        </p>
      )}
      <div className={cn('space-y-0.5', collapsed ? 'px-1.5' : 'px-2')}>
        {items.map((item) => {
          const active = pathname === item.href || pathname.startsWith(item.href + '/')
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                'group relative flex items-center rounded-lg text-[13px] font-medium',
                'transition-colors duration-150',
                collapsed ? 'justify-center h-9 w-9 mx-auto' : 'gap-2.5 px-2.5 py-2',
                active
                  ? 'bg-white/[0.08] text-white'
                  : 'text-white/50 hover:text-white hover:bg-white/[0.05]'
              )}
            >
              {active && !collapsed && (
                <span className="absolute left-0 top-1/2 -translate-y-1/2 w-[2px] h-4 rounded-full bg-accent" />
              )}
              <span className={cn('shrink-0', active ? 'text-accent' : 'text-white/40 group-hover:text-white/70')}>
                {item.icon}
              </span>
              {!collapsed && <span className="truncate">{item.label}</span>}
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
  brandSubtitle?: string
  onLogout(): void
  collapsed?: boolean
  onToggleCollapse?(): void
}

export default function Sidebar({
  user,
  brandName,
  brandSubtitle,
  onLogout,
  collapsed = false,
  onToggleCollapse,
}: SidebarProps) {
  return (
    <aside
      className={cn(
        'flex h-full flex-col border-r border-white/[0.06]',
        collapsed ? 'w-14' : 'w-[240px]'
      )}
      style={{
        background: 'linear-gradient(180deg, #18181b 0%, #111113 100%)',
      }}
    >
      {/* Header — logo + collapse (Linear-style) */}
      <div className={cn('flex items-center border-b border-white/[0.06]', collapsed ? 'justify-center px-1.5 py-3' : 'justify-between px-3 py-3')}>
        <div className={cn('flex items-center min-w-0', collapsed ? 'justify-center' : 'gap-2.5')}>
          <div
            className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0"
            style={{
              background: 'linear-gradient(135deg, #a3d16b 0%, #8bb85a 100%)',
            }}
          >
            <IconSparkles className="w-3.5 h-3.5 text-white" />
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="text-[13px] font-semibold text-white tracking-tight leading-none truncate">
                Creative<span className="text-accent">Studio</span>
              </div>
              <div className="text-[10px] text-white/35 mt-0.5 truncate">AI Creative Engine</div>
            </div>
          )}
        </div>

        {!collapsed && onToggleCollapse && (
          <button
            type="button"
            onClick={onToggleCollapse}
            title="Hide sidebar"
            className="shrink-0 w-7 h-7 rounded-md flex items-center justify-center text-white/35 hover:text-white hover:bg-white/[0.08] transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>
        )}
      </div>

      {/* Expand when collapsed */}
      {collapsed && onToggleCollapse && (
        <div className="px-1.5 py-2 flex justify-center border-b border-white/[0.06]">
          <button
            type="button"
            onClick={onToggleCollapse}
            title="Show sidebar"
            className="w-9 h-9 rounded-lg flex items-center justify-center text-white/40 hover:text-white hover:bg-white/[0.08] transition-colors"
          >
            <svg className="w-3.5 h-3.5 rotate-180" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M15.75 19.5L8.25 12l7.5-7.5" />
            </svg>
          </button>
        </div>
      )}

      {/* Partner — only when expanded, minimal */}
      {!collapsed && (
        <div className="px-3 pt-3 pb-1">
          <p className="text-[9px] font-semibold text-white/25 uppercase tracking-[0.1em] mb-1.5 px-0.5">
            Powered by
          </p>
          <div className="rounded-lg bg-white/95 px-2.5 py-1.5">
            <Image
              src="/traffic-radius-logo.png"
              alt="Traffic Radius"
              width={140}
              height={28}
              className="h-6 w-auto max-w-full object-contain object-left"
              priority
            />
          </div>
        </div>
      )}

      {/* Active brand — only expanded */}
      {!collapsed && brandName && (
        <div className="mx-2.5 mt-2 px-2.5 py-2 rounded-lg bg-white/[0.04] border border-white/[0.06]">
          <div className="flex items-center gap-1.5 mb-0.5">
            <span className="w-1.5 h-1.5 rounded-full bg-accent shrink-0" />
            <p className="text-[9px] font-semibold uppercase tracking-[0.1em] text-white/30">Active brand</p>
          </div>
          <p className="text-[12px] font-semibold text-white truncate">{brandName}</p>
          {brandSubtitle && (
            <p className="text-[10px] text-white/40 mt-0.5 truncate">{brandSubtitle}</p>
          )}
        </div>
      )}

      {/* Nav */}
      <nav className="flex-1 overflow-y-auto overflow-x-hidden py-2">
        {collapsed ? (
          <NavGroup title="" items={allNav} collapsed />
        ) : (
          <>
            <NavGroup title="Workspace" items={workspaceNav} />
            <NavGroup title="Analytics" items={performanceNav} />
            <NavGroup title="Account" items={accountNav} />
          </>
        )}
      </nav>

      {/* User */}
      <div className={cn('border-t border-white/[0.06]', collapsed ? 'p-1.5' : 'p-2.5')}>
        {collapsed ? (
          <button
            type="button"
            onClick={onLogout}
            title={`Sign out · ${user.full_name}`}
            className="w-9 h-9 mx-auto rounded-lg flex items-center justify-center text-[11px] font-bold text-white bg-accent/90 hover:bg-accent transition-colors"
          >
            {user.full_name.charAt(0).toUpperCase()}
          </button>
        ) : (
          <div className="flex items-center gap-2 px-1.5 py-1">
            <div className="w-7 h-7 rounded-lg flex items-center justify-center text-[11px] font-bold text-white shrink-0 bg-accent">
              {user.full_name.charAt(0).toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <div className="text-[12px] font-medium text-white/90 truncate">{user.full_name}</div>
              <div className="text-[10px] text-white/35 capitalize">{user.role}</div>
            </div>
            <button
              type="button"
              onClick={onLogout}
              title="Sign out"
              className="text-white/30 hover:text-white/70 p-1.5 rounded-md hover:bg-white/[0.06] transition-colors shrink-0"
            >
              <IconLogOut />
            </button>
          </div>
        )}
      </div>
    </aside>
  )
}
