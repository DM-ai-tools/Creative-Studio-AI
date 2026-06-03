import React from 'react'
import { cn } from '@/lib/utils'

interface BadgeProps {
  variant?: 'green' | 'red' | 'amber' | 'blue' | 'mint' | 'gray' | 'purple'
  size?: 'sm' | 'md'
  children: React.ReactNode
  className?: string
}

const variants = {
  green: 'bg-success/15 text-[#4a7c1f] border border-success/25',
  red: 'bg-red-500/10 text-red-700 border border-red-200',
  amber: 'bg-amber-500/10 text-amber-800 border border-amber-200',
  blue: 'bg-accent/15 text-[#3d5c22] border border-accent/30',
  mint: 'bg-accent/15 text-[#3d5c22] border border-accent/30',
  gray: 'bg-charcoal/[0.06] text-muted border border-border',
  purple: 'bg-purple-500/10 text-purple-700 border border-purple-200',
}

export default function Badge({ variant = 'gray', size = 'sm', children, className }: BadgeProps) {
  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-semibold border',
        size === 'sm' ? 'px-2.5 py-0.5 text-[10px]' : 'px-3 py-1 text-xs',
        variants[variant],
        className
      )}
    >
      {children}
    </span>
  )
}
