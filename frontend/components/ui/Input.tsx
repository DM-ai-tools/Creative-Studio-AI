import React, { forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  leftIcon?: React.ReactNode
  rightElement?: React.ReactNode
  labelClassName?: string
}

const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, leftIcon, rightElement, labelClassName, className, id, ...props },
  ref
) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className={cn('label-ui', labelClassName)}>
          {label}
        </label>
      )}
      <div className="relative">
        {leftIcon && (
          <span className="absolute left-3 top-1/2 -translate-y-1/2 text-muted pointer-events-none flex items-center">
            {leftIcon}
          </span>
        )}
        <input
          ref={ref}
          id={inputId}
          {...props}
          className={cn(
            'w-full h-9 border rounded-xl text-sm text-charcoal bg-surface-elevated font-sans',
            'placeholder:text-subtle/70',
            'transition-all duration-200 ease-premium',
            'hover:border-subtle/70',
            leftIcon ? 'pl-9 pr-4' : 'px-3.5',
            rightElement ? 'pr-10' : '',
            error
              ? 'border-red-400 bg-red-50/30'
              : 'border-border',
            className
          )}
        />
        {rightElement && (
          <span className="absolute right-2.5 top-1/2 -translate-y-1/2 flex items-center">
            {rightElement}
          </span>
        )}
      </div>
      {error && (
        <p className="mt-1.5 text-[11px] text-red-600 font-medium flex items-center gap-1">
          <svg className="w-3 h-3 shrink-0" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 1a7 7 0 100 14A7 7 0 008 1zm-.75 4a.75.75 0 011.5 0v3a.75.75 0 01-1.5 0V5zm.75 6.5a.75.75 0 110-1.5.75.75 0 010 1.5z" />
          </svg>
          {error}
        </p>
      )}
      {hint && !error && <p className="mt-1.5 text-[11px] text-muted">{hint}</p>}
    </div>
  )
})

export default Input
