'use client'

import React from 'react'
import Button from '@/components/ui/Button'
import { cn } from '@/lib/utils'
import type { CatalogOption } from '@/types'

type Props = {
  options: CatalogOption[]
  selected: string[]
  onChange(next: string[]): void
  onSuggest(): void
  suggesting?: boolean
  suggestionReason?: string | null
  disabled?: boolean
}

export default function AdAngleSelector({
  options,
  selected,
  onChange,
  onSuggest,
  suggesting,
  suggestionReason,
  disabled,
}: Props) {
  const toggle = (id: string) => {
    if (disabled) return
    onChange(selected.includes(id) ? selected.filter((v) => v !== id) : [...selected, id])
  }

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[11px] text-mid leading-relaxed max-w-2xl">
          Select <strong>one or more</strong> ad angles — each image variant gets a{' '}
          <strong>different angle</strong> so you can test what works in the same campaign.
        </p>
        <Button
          type="button"
          size="sm"
          variant="outline"
          isLoading={suggesting}
          disabled={disabled || suggesting}
          onClick={onSuggest}
        >
          Suggest with AI
        </Button>
      </div>

      {suggestionReason ? (
        <div className="rounded-lg border border-accent/25 bg-accent/5 px-3 py-2">
          <p className="text-[10px] font-bold text-navy uppercase tracking-wide mb-0.5">AI suggestion</p>
          <p className="text-[11px] text-charcoal leading-relaxed">{suggestionReason}</p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
        {options.map((opt) => {
          const on = selected.includes(opt.id)
          return (
            <label
              key={opt.id}
              className={cn(
                'flex items-start gap-3 rounded-xl border px-3 py-2.5 cursor-pointer transition-all',
                on
                  ? 'border-accent/50 bg-accent/8 shadow-sm'
                  : 'border-border bg-surface hover:border-accent/30 hover:bg-accent/[0.03]',
                disabled && 'opacity-50 cursor-not-allowed'
              )}
            >
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 rounded border-border text-accent focus:ring-accent/40"
                checked={on}
                disabled={disabled}
                onChange={() => toggle(opt.id)}
              />
              <span className="min-w-0">
                <span className="block text-xs font-semibold text-charcoal leading-snug">{opt.label}</span>
              </span>
            </label>
          )
        })}
      </div>

      {selected.length > 0 ? (
        <p className="text-[10px] text-mid">
          {selected.length} angle{selected.length !== 1 ? 's' : ''} selected — variants will rotate through these.
        </p>
      ) : (
        <p className="text-[10px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          No angles selected — click <strong>Suggest with AI</strong> or pick manually. If left empty, AI picks
          angles from your campaign objective when you generate variants.
        </p>
      )}
    </div>
  )
}
