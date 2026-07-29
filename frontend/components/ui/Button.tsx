import React from 'react'
import { cn } from '@/lib/utils'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'success'
  size?: 'xs' | 'sm' | 'md' | 'lg'
  isLoading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

const variants: Record<string, string> = {
  primary: [
    'bg-accent-gradient text-white font-semibold',
    'shadow-[0_1px_2px_rgba(26,26,26,0.12),0_0_0_1px_rgba(163,209,107,0.4),inset_0_1px_0_rgba(255,255,255,0.2)]',
    'hover:brightness-105 hover:shadow-glow-sm',
    'active:scale-[0.975] active:brightness-100',
  ].join(' '),

  secondary: [
    'bg-charcoal text-white font-semibold',
    'shadow-[0_1px_2px_rgba(26,26,26,0.2),0_0_0_1px_rgba(255,255,255,0.05)]',
    'hover:bg-ink hover:shadow-[0_2px_8px_rgba(26,26,26,0.25)]',
    'active:scale-[0.975]',
  ].join(' '),

  outline: [
    'bg-surface-elevated text-charcoal font-semibold',
    'border border-border',
    'shadow-xs',
    'hover:border-accent/40 hover:bg-accent/[0.03] hover:shadow-[0_1px_4px_rgba(163,209,107,0.12)]',
    'active:scale-[0.975] active:bg-accent/[0.06]',
  ].join(' '),

  ghost: [
    'bg-transparent text-muted font-medium',
    'hover:text-charcoal hover:bg-charcoal/[0.05]',
    'active:bg-charcoal/[0.08]',
  ].join(' '),

  danger: [
    'bg-red-500 text-white font-semibold',
    'shadow-[0_1px_2px_rgba(239,68,68,0.2),0_0_0_1px_rgba(239,68,68,0.3)]',
    'hover:bg-red-600 hover:shadow-[0_4px_12px_rgba(239,68,68,0.3)]',
    'active:scale-[0.975]',
  ].join(' '),

  success: [
    'bg-success-gradient text-white font-semibold',
    'shadow-[0_1px_2px_rgba(163,209,107,0.2),0_0_0_1px_rgba(163,209,107,0.4)]',
    'hover:brightness-105 hover:shadow-glow-sm',
    'active:scale-[0.975]',
  ].join(' '),
}

const sizes: Record<string, string> = {
  xs: 'h-7 px-2.5 text-[11px] rounded-lg gap-1',
  sm: 'h-8 px-3.5 text-xs rounded-xl gap-1.5',
  md: 'h-9 px-4 text-sm rounded-xl gap-2',
  lg: 'h-11 px-5 text-sm rounded-2xl gap-2',
}

export default function Button({
  variant = 'primary',
  size = 'md',
  isLoading,
  leftIcon,
  rightIcon,
  children,
  className,
  disabled,
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      disabled={disabled || isLoading}
      className={cn(
        'inline-flex items-center justify-center',
        'transition-all duration-200 ease-premium cursor-pointer select-none',
        'disabled:opacity-40 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50 focus-visible:ring-offset-1',
        variants[variant],
        sizes[size],
        className
      )}
    >
      {isLoading ? (
        <svg
          className="animate-spin shrink-0 w-3.5 h-3.5"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle className="opacity-20" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3.5" />
          <path className="opacity-80" fill="currentColor" d="M4 12a8 8 0 018-8v3.5a4.5 4.5 0 00-4.5 4.5H4z" />
        </svg>
      ) : leftIcon ? (
        <span className="shrink-0 flex items-center">{leftIcon}</span>
      ) : null}
      {children && <span className={isLoading ? 'opacity-70' : ''}>{children}</span>}
      {!isLoading && rightIcon ? (
        <span className="shrink-0 flex items-center opacity-70">{rightIcon}</span>
      ) : null}
    </button>
  )
}
