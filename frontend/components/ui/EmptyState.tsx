'use client'

import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import { Sparkles, type LucideIcon } from 'lucide-react'

/** A friendly empty screen: a softly floating icon, a title, one line of help and an optional action. */
export default function EmptyState({
  title,
  description,
  action,
  icon: Icon = Sparkles,
  compact = false,
}: {
  title: string
  description: string
  action?: React.ReactNode
  icon?: LucideIcon
  compact?: boolean
}) {
  const reduce = useReducedMotion()
  return (
    <motion.div
      initial={reduce ? false : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: [0.22, 1, 0.36, 1] }}
      className={`flex flex-col items-center justify-center px-6 text-center ${compact ? 'py-8' : 'py-14'}`}
    >
      <div className="relative mb-4">
        <span className="absolute inset-0 -z-10 rounded-3xl bg-accent/20 blur-xl" aria-hidden="true" />
        <motion.div
          animate={reduce ? undefined : { y: [0, -5, 0] }}
          transition={{ duration: 3.2, repeat: Infinity, ease: 'easeInOut' }}
          className="flex h-14 w-14 items-center justify-center rounded-2xl border border-accent/30 bg-white shadow-card"
        >
          <Icon className="h-6 w-6 text-[#6f9b3f]" strokeWidth={1.6} aria-hidden="true" />
        </motion.div>
      </div>
      <p className="mb-1 text-sm font-bold text-charcoal">{title}</p>
      <p className="mb-4 max-w-[260px] text-[12px] leading-relaxed text-muted">{description}</p>
      {action}
    </motion.div>
  )
}
