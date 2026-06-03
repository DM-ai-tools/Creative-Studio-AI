import React from 'react'
import { cn } from '@/lib/utils'

interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger' | 'success'
  size?: 'sm' | 'md' | 'lg'
  isLoading?: boolean
  leftIcon?: React.ReactNode
  rightIcon?: React.ReactNode
}

const variants = {
  primary:
    'bg-accent-gradient text-white shadow-soft hover:shadow-glow hover:brightness-105 active:scale-[0.98] font-semibold border border-accent/30',
  secondary:
    'bg-ink text-white shadow-soft hover:bg-charcoal active:scale-[0.98] font-semibold',
  outline:
    'bg-surface-elevated/80 text-charcoal border border-border hover:border-accent/40 hover:bg-accent/[0.04] font-semibold backdrop-blur-sm',
  ghost: 'bg-transparent text-muted hover:text-charcoal hover:bg-charcoal/[0.04] font-medium',
  danger:
    'bg-red-500 text-white hover:bg-red-600 shadow-soft active:scale-[0.98] font-semibold',
  success:
    'bg-success-gradient text-white shadow-soft hover:shadow-glow-success active:scale-[0.98] font-semibold border border-success/30',
}

const sizes = {
  sm: 'px-3.5 py-2 text-xs rounded-xl gap-1.5',
  md: 'px-5 py-2.5 text-sm rounded-xl gap-2',
  lg: 'px-6 py-3 text-sm rounded-2xl gap-2',
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
        'inline-flex items-center justify-center transition-all duration-200 ease-premium cursor-pointer',
        'disabled:opacity-45 disabled:cursor-not-allowed disabled:transform-none disabled:shadow-none',
        variants[variant],
        sizes[size],
        className
      )}
    >
      {isLoading ? (
        <svg
          className="animate-spin h-4 w-4 shrink-0"
          width="16"
          height="16"
          viewBox="0 0 24 24"
          fill="none"
          aria-hidden="true"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
        </svg>
      ) : (
        leftIcon
      )}
      {children}
      {!isLoading && rightIcon}
    </button>
  )
}
