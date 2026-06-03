import React from 'react'
import { cn } from '@/lib/utils'

interface CardProps {
  title?: string
  action?: React.ReactNode
  className?: string
  children: React.ReactNode
  padding?: boolean
  hover?: boolean
}

export default function Card({
  title,
  action,
  className,
  children,
  padding = true,
  hover = false,
}: CardProps) {
  return (
    <div
      className={cn(
        'card-premium overflow-hidden animate-fade-in',
        hover && 'hover:shadow-card-hover',
        className
      )}
    >
      {title && (
        <div className="flex items-center justify-between px-5 py-4 border-b border-border/70 bg-gradient-to-r from-surface/50 to-transparent">
          <h3 className="text-sm font-bold text-charcoal tracking-tight">{title}</h3>
          {action && <div className="text-sm">{action}</div>}
        </div>
      )}
      <div className={padding ? 'p-5' : ''}>{children}</div>
    </div>
  )
}
