import React from 'react'
import { cn } from '@/lib/utils'

interface MetricCardProps {
  label: string
  value: string | number
  change?: string
  changeDirection?: 'up' | 'down' | 'neutral'
  isLoading?: boolean
  valueColor?: string
}

export default function MetricCard({
  label,
  value,
  change,
  changeDirection = 'neutral',
  isLoading,
  valueColor,
}: MetricCardProps) {
  if (isLoading) {
    return (
      <div className="card-premium p-5">
        <div className="skeleton h-3 w-24 mb-4 rounded-lg" />
        <div className="skeleton h-9 w-20 mb-2 rounded-lg" />
        <div className="skeleton h-2.5 w-28 rounded-lg" />
      </div>
    )
  }
  return (
    <div className="card-premium p-5 group hover:shadow-card-hover">
      <div className="flex items-start justify-between gap-2">
        <div className="text-[11px] font-bold text-muted uppercase tracking-wider">{label}</div>
        <div className="w-2 h-2 rounded-full bg-accent/40 group-hover:bg-accent transition-colors shadow-[0_0_8px_rgba(163,209,107,0.55)]" />
      </div>
      <div className={cn('text-3xl font-bold text-charcoal mt-2 tracking-tight', valueColor)}>
        {value}
      </div>
      {change && (
        <div
          className={cn(
            'text-xs mt-2 font-medium inline-flex items-center gap-1',
            changeDirection === 'up'
              ? 'text-[#4a7c1f]'
              : changeDirection === 'down'
                ? 'text-red-500'
                : 'text-muted'
          )}
        >
          {changeDirection === 'up' && (
            <span className="text-success">↑</span>
          )}
          {changeDirection === 'down' && <span>↓</span>}
          {change}
        </div>
      )}
    </div>
  )
}
