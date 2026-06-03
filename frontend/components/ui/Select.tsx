import React, { forwardRef } from 'react'
import { cn } from '@/lib/utils'

export type SelectOption = { value: string; label: string }

export type SelectOptionGroup = {
  label: string
  options: SelectOption[]
}

interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  hint?: string
  placeholder?: string
  options?: SelectOption[]
  groups?: SelectOptionGroup[]
}

const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, error, hint, placeholder, options = [], groups, className, id, ...props },
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
      <select
        ref={ref}
        id={inputId}
        {...props}
        className={cn(
          'w-full px-4 py-2.5 border rounded-xl text-sm text-charcoal bg-surface-elevated/90 font-sans',
          'transition-all duration-200 ease-premium cursor-pointer appearance-none',
          'bg-[length:16px] bg-[right_12px_center] bg-no-repeat',
          "bg-[url('data:image/svg+xml;charset=utf-8,%3Csvg xmlns=%27http://www.w3.org/2000/svg%27 fill=%27none%27 viewBox=%270 0 24 24%27 stroke=%27%236B6B73%27%3E%3Cpath stroke-linecap=%27round%27 stroke-linejoin=%27round%27 stroke-width=%272%27 d=%27M19 9l-7 7-7-7%27/%3E%3C/svg%3E')]",
          'pr-10',
          error ? 'border-red-400' : 'border-border hover:border-subtle/80',
          className
        )}
      >
        {placeholder && (
          <option value="" disabled>
            {placeholder}
          </option>
        )}
        {groups?.map((group) => (
          <optgroup key={group.label} label={group.label}>
            {group.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
          </optgroup>
        ))}
        {!groups?.length &&
          options.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
      </select>
      {error && <p className="mt-1.5 text-xs text-red-500 font-medium">{error}</p>}
      {hint && !error && <p className="mt-1.5 text-xs text-muted">{hint}</p>}
    </div>
  )
})

export default Select
