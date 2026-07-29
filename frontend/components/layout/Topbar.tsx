import React from 'react'
import { cn } from '@/lib/utils'

interface TopbarProps {
  title: string
  subtitle?: string
  actions?: React.ReactNode
  /** Compact version for nested pages */
  compact?: boolean
}

export default function Topbar({ title, subtitle, actions, compact = false }: TopbarProps) {
  return (
    <header
      className={cn(
        'sticky top-0 z-20 flex items-center justify-between gap-4',
        'glass-topbar',
        compact ? 'px-6 py-3' : 'px-6 py-4',
      )}
    >
      <div className="min-w-0 animate-slide-up">
        <h1
          className={cn(
            'font-bold text-charcoal tracking-tight truncate',
            compact ? 'text-[15px]' : 'text-[17px]'
          )}
          style={{ letterSpacing: '-0.015em' }}
        >
          {title}
        </h1>
        {subtitle && (
          <p className="text-[12px] text-muted mt-0.5 truncate font-medium">{subtitle}</p>
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
