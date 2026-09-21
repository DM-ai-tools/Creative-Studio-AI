import React from 'react'
import { cn } from '@/lib/utils'

interface CardProps {
  title?: string
  subtitle?: string
  action?: React.ReactNode
  className?: string
  children: React.ReactNode
  padding?: boolean
  hover?: boolean
  /** Accent left bar */
  accent?: boolean
  /** Dark surface for usage / analytics pages */
  theme?: 'light' | 'dark'
}

export default function Card({
  title,
  subtitle,
  action,
  className,
  children,
  padding = true,
  hover = false,
  accent = false,
  theme = 'light',
}: CardProps) {
  const isDark = theme === 'dark'
  return (
    <div
      className={cn(
        'relative rounded-2xl overflow-hidden animate-fade-in',
        isDark
          ? 'bg-[#111114] border border-[#2a2a2e] shadow-none'
          : 'bg-surface-elevated border border-border shadow-card',
        hover && 'transition-all duration-250 ease-premium hover:shadow-card-hover hover:border-accent/20 hover:-translate-y-px cursor-pointer',
        className
      )}
    >
      {accent && (
        <div
          className="absolute left-0 top-0 bottom-0 w-[3px]"
          style={{
            background: 'linear-gradient(180deg, #a3d16b, #8bb85a)',
            boxShadow: '0 0 8px rgba(163,209,107,0.45)',
          }}
        />
      )}
      {(title || action) && (
        <div className={cn(
          'flex items-center justify-between gap-3 px-5 py-3.5',
          isDark ? 'border-b border-[#2a2a2e]' : 'border-b border-border/60 bg-gradient-to-r from-surface/60 to-transparent',
        )}>
          <div className="min-w-0">
            <h3 className={cn(
              'text-sm font-bold tracking-tight truncate',
              isDark ? 'text-[#f5f5f7]' : 'text-charcoal',
              accent && 'pl-2'
            )}>
              {title}
            </h3>
            {subtitle && (
              <p className={cn(
                'text-[11px] mt-0.5 truncate',
                isDark ? 'text-[#8e8e93]' : 'text-muted',
                accent && 'pl-2'
              )}>
                {subtitle}
              </p>
            )}
          </div>
          {action && <div className="shrink-0">{action}</div>}
        </div>
      )}
      <div className={padding ? 'p-5' : ''}>{children}</div>
    </div>
  )
}
