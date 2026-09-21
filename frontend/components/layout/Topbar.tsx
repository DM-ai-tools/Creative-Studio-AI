import React from 'react'
import { cn } from '@/lib/utils'

interface TopbarProps {
  title: string
  subtitle?: string
  actions?: React.ReactNode
  /** Compact version for nested pages */
  compact?: boolean
  /** Dark header for analytics / usage pages */
  variant?: 'light' | 'dark'
}

export default function Topbar({
  title,
  subtitle,
  actions,
  compact = false,
  variant = 'light',
}: TopbarProps) {
  const isDark = variant === 'dark'
  return (
    <header
      className={cn(
        'sticky top-0 z-20 flex items-center justify-between gap-4',
        isDark
          ? 'bg-[#0c0c0e]/95 backdrop-blur-xl border-b border-[#2a2a2e]'
          : 'glass-topbar',
        compact ? 'px-6 py-3' : 'px-6 py-4',
      )}
    >
      <div className="min-w-0 animate-slide-up">
        <h1
          className={cn(
            'font-bold tracking-tight truncate',
            isDark ? 'text-[#f5f5f7]' : 'text-charcoal',
            compact ? 'text-[15px]' : 'text-[17px]'
          )}
          style={{ letterSpacing: '-0.015em' }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            className={cn(
              'text-[12px] mt-0.5 truncate font-medium',
              isDark ? 'text-[#8e8e93]' : 'text-muted',
            )}
          >
            {subtitle}
          </p>
        )}
      </div>

      {actions && (
        <div className="flex items-center gap-2 shrink-0">
          {actions}
        </div>
      )}
    </header>
  )
}
