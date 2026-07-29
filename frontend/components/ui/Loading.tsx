import React from 'react'
import { cn } from '@/lib/utils'

interface SpinnerProps {
  size?: 'xs' | 'sm' | 'md' | 'lg'
  className?: string
  color?: string
}

const spinnerSizes = { xs: 'w-3 h-3', sm: 'w-4 h-4', md: 'w-5 h-5', lg: 'w-7 h-7' }
const spinnerPx    = { xs: 12, sm: 16, md: 20, lg: 28 }

export function Spinner({ size = 'md', className, color = 'text-accent' }: SpinnerProps) {
  return (
    <svg
      className={cn('animate-spin shrink-0', spinnerSizes[size], color, className)}
      width={spinnerPx[size]}
      height={spinnerPx[size]}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3.5" />
      <path
        className="opacity-80"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v3.5a4.5 4.5 0 00-4.5 4.5H4z"
      />
    </svg>
  )
}

export function PageLoader() {
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-mesh z-50">
      <div className="flex flex-col items-center gap-6 animate-fade-in">
        {/* Logo mark */}
        <div className="relative">
          <div
            className="w-14 h-14 rounded-2xl flex items-center justify-center"
            style={{ background: 'linear-gradient(135deg, #A3D16B, #8BB85A)' }}
          >
            <svg className="w-7 h-7 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" strokeLinejoin="round"
                d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09z" />
            </svg>
          </div>
          <div
            className="absolute -inset-2 rounded-3xl opacity-30 animate-pulse-glow"
            style={{ background: 'radial-gradient(circle, rgba(163,209,107,0.6) 0%, transparent 70%)' }}
          />
        </div>

        {/* Brand */}
        <div className="text-center">
          <div className="text-[17px] font-bold text-charcoal tracking-tight">
            Creative<span className="gradient-text">Studio</span>
          </div>
          <p className="text-[12px] text-muted mt-1 font-medium">Loading your workspace…</p>
        </div>

        {/* Progress bar */}
        <div className="w-32 h-0.5 rounded-full bg-border overflow-hidden">
          <div
            className="h-full rounded-full bg-accent-gradient animate-pulse"
            style={{ width: '60%' }}
          />
        </div>
      </div>
    </div>
  )
}

/** Simple shimmer skeleton block */
export function SkeletonLine({ className }: { className?: string }) {
  return <div className={cn('skeleton rounded-lg', className)} />
}

/** Full skeleton card */
export function SkeletonCard({ rows = 3 }: { rows?: number }) {
  return (
    <div className="card-premium p-5 space-y-3 overflow-hidden">
      <SkeletonLine className="h-3.5 w-1/3" />
      <SkeletonLine className="h-7 w-1/2" />
      {rows > 2 && <SkeletonLine className="h-3 w-2/3" />}
      {rows > 3 && <SkeletonLine className="h-3 w-1/2" />}
    </div>
  )
}

/** Section loading placeholder */
export function SectionLoader({ label }: { label?: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 gap-3 text-muted">
      <Spinner size="md" />
      {label && <p className="text-xs font-medium">{label}</p>}
    </div>
  )
}

/** Dot-style inline loading */
export function DotsLoader({ className }: { className?: string }) {
  return (
    <span className={cn('inline-flex items-center gap-1', className)} aria-label="Loading">
      {[0, 0.15, 0.3].map((delay, i) => (
        <span
          key={i}
          className="w-1 h-1 rounded-full bg-current dot-blink"
          style={{ animationDelay: `${delay}s` }}
        />
      ))}
    </span>
  )
}
