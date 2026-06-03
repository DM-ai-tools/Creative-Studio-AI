import React, { forwardRef } from 'react'
import { cn } from '@/lib/utils'

interface ComboboxProps extends Omit<React.InputHTMLAttributes<HTMLInputElement>, 'list'> {
  label?: string
  error?: string
  hint?: string
  options: { value: string; label: string }[]
  listId?: string
}

const Combobox = forwardRef<HTMLInputElement, ComboboxProps>(function Combobox(
  { label, error, hint, options, listId, className, id, ...props },
  ref
) {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-')
  const datalistId = listId || `${inputId}-options`

  return (
    <div className="w-full">
      {label && (
        <label htmlFor={inputId} className="block text-xs font-bold text-navy uppercase tracking-wide mb-1.5">
          {label}
        </label>
      )}
      <input
        ref={ref}
        id={inputId}
        list={datalistId}
        {...props}
        className={cn(
          'w-full px-3 py-2 border rounded-lg text-sm text-navy bg-white font-sans',
          'placeholder:text-lt transition-colors',
          error ? 'border-red-400' : 'border-border',
          className
        )}
      />
      <datalist id={datalistId}>
        {options.map((opt) => (
          <option key={opt.value} value={opt.label} />
        ))}
      </datalist>
      {error && <p className="mt-1 text-xs text-red-500">{error}</p>}
      {hint && !error && <p className="mt-1 text-xs text-lt">{hint}</p>}
    </div>
  )
})

export default Combobox
