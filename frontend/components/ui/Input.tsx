import React, { forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
}

const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, error, hint, className, id, ...props },
  ref
) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')
  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="label-ui">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        {...props}
        className={cn(
          'w-full px-4 py-2.5 border rounded-xl text-sm text-charcoal bg-surface-elevated/90 font-sans',
          'placeholder:text-subtle transition-all duration-200 ease-premium',
          'hover:border-subtle/80',
          error ? 'border-red-400 focus:ring-red-500/20' : 'border-border',
          className
        )}
      />
      {error && <p className="mt-1.5 text-xs text-red-500 font-medium">{error}</p>}
      {hint && !error && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
    </div>
  )
})

export default Input
