'use client'

import React from 'react'
import { cn } from '@/lib/utils'

interface ChipToggleProps {
  label: string
  selected: boolean
  onToggle(): void
  disabled?: boolean
}

export function ChipToggle({ label, selected, onToggle, disabled }: ChipToggleProps) {
  return (
    <button
      type="button"
      onClick={onToggle}
      disabled={disabled}
      className={cn(
        'inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-full border transition-all duration-200 ease-premium',
        selected
          ? 'bg-accent/12 text-charcoal border-accent/40 shadow-[0_0_12px_rgba(163,209,107,0.2)]'
          : 'bg-surface-elevated/80 text-muted border-border hover:border-accent/30 hover:text-charcoal',
        disabled && 'opacity-50 cursor-not-allowed'
      )}
    >
      {label}
    </button>
  )
}

interface ChipToggleGroupProps {
  options: { id: string; label: string }[]
  selected: string[]
  onChange(next: string[]): void
  disabled?: boolean
}

export function ChipToggleGroup({ options, selected, onChange, disabled }: ChipToggleGroupProps) {
  const toggle = (id: string) => {
    if (disabled) return
    onChange(selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id])
  }

  return (
    <div className="flex flex-wrap gap-2">
      {options.map((option) => (
        <ChipToggle
          key={option.id}
          label={option.label}
          selected={selected.includes(option.id)}
          onToggle={() => toggle(option.id)}
          disabled={disabled}
        />
      ))}
    </div>
  )
}
