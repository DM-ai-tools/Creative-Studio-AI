import React from 'react'
import { cn } from '@/lib/utils'

interface BadgeProps {
  variant?: 'green' | 'red' | 'amber' | 'blue' | 'mint' | 'gray' | 'purple' | 'orange'
  size?: 'xs' | 'sm' | 'md'
  dot?: boolean
  children: React.ReactNode
  className?: string
}

const variants: Record<string, { badge: string; dot: string }> = {
  green:  { badge: 'bg-emerald-50 text-emerald-700 border border-emerald-200/80', dot: 'bg-emerald-500' },
  red:    { badge: 'bg-red-50 text-red-700 border border-red-200/80', dot: 'bg-red-500' },
  amber:  { badge: 'bg-amber-50 text-amber-700 border border-amber-200/80', dot: 'bg-amber-500' },
  orange: { badge: 'bg-orange-50 text-orange-700 border border-orange-200/80', dot: 'bg-orange-500' },
  blue:   { badge: 'bg-blue-50 text-blue-700 border border-blue-200/80', dot: 'bg-blue-500' },
  mint:   { badge: 'bg-accent/10 text-[#4a7a20] border border-accent/25', dot: 'bg-accent' },
  gray:   { badge: 'bg-charcoal/[0.05] text-muted border border-border', dot: 'bg-subtle' },
  purple: { badge: 'bg-purple-50 text-purple-700 border border-purple-200/80', dot: 'bg-purple-500' },
}

const sizes: Record<string, string> = {
  xs: 'px-2 py-0.5 text-[9px] rounded-md gap-1',
  sm: 'px-2.5 py-0.5 text-[10px] rounded-full gap-1',
  md: 'px-3 py-1 text-xs rounded-full gap-1.5',
}

export default function Badge({
  variant = 'gray',
  size = 'sm',
  dot = false,
  children,
  className,
}: BadgeProps) {
  const { badge, dot: dotColor } = variants[variant] ?? variants.gray
  return (
    <span
      className={cn(
        'inline-flex items-center font-semibold',
        badge,
        sizes[size],
        className
      )}
    >
      {dot && (
        <span
          className={cn('rounded-full flex-shrink-0', dotColor)}
          style={{ width: 5, height: 5 }}
        />
      )}
      {children}
    </span>
  )
}
