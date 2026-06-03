import React from 'react'
import { cn } from '@/lib/utils'

interface BriefSectionProps {
  title: string
  step?: string
  className?: string
  children: React.ReactNode
}

export default function BriefSection({ title, step, className, children }: BriefSectionProps) {
  return (
    <section className={cn('card-premium overflow-hidden animate-fade-in', className)}>
      <header className="flex items-center justify-between px-5 py-4 border-b border-border/70 bg-gradient-to-r from-accent/[0.04] to-transparent">
        <h3 className="text-sm font-bold text-charcoal tracking-tight">{title}</h3>
        {step && (
          <span className="text-[10px] font-bold uppercase tracking-wider text-accent bg-accent/10 border border-accent/25 px-2.5 py-1 rounded-full">
            {step}
          </span>
        )}
      </header>
      <div className="p-5 md:p-6 space-y-4">{children}</div>
    </section>
  )
}
