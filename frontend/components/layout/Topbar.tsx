import React from 'react'

interface TopbarProps {
  title: string
  subtitle?: string
  actions?: React.ReactNode
}

export default function Topbar({ title, subtitle, actions }: TopbarProps) {
  return (
    <header className="sticky top-0 z-20 glass-topbar px-6 py-4 flex items-center justify-between gap-4">
      <div className="min-w-0 animate-slide-up">
        <h1 className="text-lg font-bold text-charcoal tracking-tight truncate">{title}</h1>
        {subtitle && <p className="text-sm text-muted mt-0.5 truncate">{subtitle}</p>}
      </div>
      {actions && <div className="flex items-center gap-2 flex-shrink-0">{actions}</div>}
    </header>
  )
}
