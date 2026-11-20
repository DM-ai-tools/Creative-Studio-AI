'use client'

import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'

export type UnderlineTab<T extends string> = { id: T; label: React.ReactNode }

/** A tab bar whose underline slides to the chosen tab. `group` keeps two tab bars on one page apart. */
export default function UnderlineTabs<T extends string>({
  tabs,
  value,
  onChange,
  group = 'tabs',
}: {
  tabs: UnderlineTab<T>[]
  value: T
  onChange(id: T): void
  group?: string
}) {
  const reduce = useReducedMotion()
  return (
    <div className="flex gap-1 border-b border-border" role="tablist">
      {tabs.map((tab) => {
        const active = tab.id === value
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.id)}
            className={`relative flex items-center gap-1.5 rounded-t-lg px-4 py-2 text-sm font-semibold transition-colors ${
              active ? 'bg-surface-elevated text-navy' : 'text-mid hover:text-navy'
            }`}
          >
            {tab.label}
            {active && (
              <motion.span
                layoutId={`${group}-underline`}
                className="absolute inset-x-0 -bottom-px h-0.5 bg-accent"
                transition={reduce ? { duration: 0 } : { type: 'spring', stiffness: 500, damping: 36 }}
              />
            )}
          </button>
        )
      })}
    </div>
  )
}
