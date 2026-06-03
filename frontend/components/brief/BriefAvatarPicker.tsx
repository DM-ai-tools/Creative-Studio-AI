'use client'

import React from 'react'
import { cn } from '@/lib/utils'
import type { CatalogOption } from '@/types'

interface BriefAvatarPickerProps {
  options: CatalogOption[]
  value: string
  onChange(id: string): void
  disabled?: boolean
}

function displayName(label: string): string {
  const parts = label.split(' — ')
  return parts.length > 1 ? parts[parts.length - 1] : label
}

function initials(label: string): string {
  const name = displayName(label)
  const words = name.split(/\s+/).filter(Boolean)
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase()
  return name.slice(0, 2).toUpperCase()
}

export default function BriefAvatarPicker({ options, value, onChange, disabled }: BriefAvatarPickerProps) {
  if (!options.length) {
    return (
      <p className="text-xs text-mid">
        No HeyGen avatars configured. Add HEYGEN_AVATAR_OPTIONS in backend .env and restart the API.
      </p>
    )
  }

  const shown = options.slice(0, 24)

  return (
    <div className="grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 gap-3 max-h-[280px] overflow-y-auto pr-1">
      {shown.map((opt) => {
        const selected = value === opt.id
        const isFemale = (opt.gender || opt.label.toLowerCase()).includes('female')
        return (
          <button
            key={opt.id}
            type="button"
            disabled={disabled}
            onClick={() => onChange(opt.id)}
            className={cn(
              'flex flex-col items-center gap-1.5 p-2 rounded-xl border transition-all text-center',
              selected
                ? 'border-mint bg-[rgba(0,194,168,0.1)] ring-2 ring-mint/40'
                : 'border-border hover:border-mint/50 bg-white',
              disabled && 'opacity-50 cursor-not-allowed'
            )}
          >
            <span
              className={cn(
                'w-12 h-12 rounded-full flex items-center justify-center text-sm font-bold text-white',
                isFemale ? 'bg-gradient-to-br from-pink-400 to-rose-600' : 'bg-gradient-to-br from-sky-500 to-navy'
              )}
            >
              {initials(opt.label)}
            </span>
            <span className="text-[9px] font-semibold text-navy leading-tight line-clamp-2">
              {displayName(opt.label)}
            </span>
          </button>
        )
      })}
    </div>
  )
}
