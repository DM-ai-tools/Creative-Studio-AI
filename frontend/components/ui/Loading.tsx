import React from 'react'
import { cn } from '@/lib/utils'

interface SpinnerProps {
  size?: 'sm' | 'md' | 'lg'
  className?: string
  color?: string
}

const spinnerSizes = { sm: 'w-4 h-4', md: 'w-6 h-6', lg: 'w-8 h-8' }
const spinnerPixels = { sm: 16, md: 24, lg: 32 }

export function Spinner({ size = 'md', className, color = 'text-accent' }: SpinnerProps) {
  return (
    <svg
      className={cn('animate-spin shrink-0', spinnerSizes[size], color, className)}
      width={spinnerPixels[size]}
      height={spinnerPixels[size]}
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
    >
      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
    </svg>
  )
}

export function PageLoader() {
  return (
    <div className="fixed inset-0 flex items-center justify-center bg-mesh z-50">
      <div className="flex flex-col items-center gap-5 animate-fade-in">
        <div className="text-xl font-bold text-charcoal tracking-tight">
          Creative<span className="gradient-text">Studio</span> AI
        </div>
        <div className="relative">
          <div className="absolute inset-0 rounded-full bg-accent/20 blur-xl animate-pulse-glow" />
          <Spinner size="lg" className="page-loader-spinner relative" />
        </div>
        <p className="text-xs text-muted font-medium">Loading workspace…</p>
      </div>
    </div>
  )
}

export function SkeletonCard() {
  return (
    <div className="card-premium p-5 space-y-3">
      <div className="skeleton h-4 w-1/3 rounded-lg" />
      <div className="skeleton h-8 w-1/2 rounded-lg" />
      <div className="skeleton h-3 w-2/3 rounded-lg" />
    </div>
  )
}
