import React, { forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface TextAreaProps extends React.TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  hint?: string
}

const TextArea = forwardRef<HTMLTextAreaElement, TextAreaProps>(function TextArea(
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
      <textarea
        ref={ref}
        id={inputId}
        {...props}
        className={cn(
          'w-full px-4 py-3 border rounded-xl text-sm text-charcoal bg-surface-elevated/90 font-sans resize-y min-h-[100px]',
          'placeholder:text-subtle transition-all duration-200 ease-premium',
          'hover:border-subtle/80',
          error ? 'border-red-400' : 'border-border',
          className
        )}
      />
      {error && <p className="mt-1.5 text-xs text-red-500 font-medium">{error}</p>}
      {hint && !error && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
    </div>
  )
})

export default TextArea
