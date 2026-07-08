'use client'

import React from 'react'
import { cn } from '@/lib/utils'

interface LogoUploadZoneProps {
  label: string
  hint: string
  previewUrl: string | null
  variant: 'dark' | 'light'
  emptyLabel: string
  uploadLabel: string
  isUploading: boolean
  disabled?: boolean
  disabledHint?: string
  onChange(event: React.ChangeEvent<HTMLInputElement>): void
}

export default function LogoUploadZone({
  label,
  hint,
  previewUrl,
  variant,
  emptyLabel,
  uploadLabel,
  isUploading,
  disabled,
  disabledHint,
  onChange,
}: LogoUploadZoneProps) {
  const isDark = variant === 'dark'

  return (
    <label
      className={cn(
        'group relative flex flex-col h-full rounded-2xl border-2 border-dashed transition-all duration-200 cursor-pointer overflow-hidden min-h-[160px]',
        disabled && 'opacity-50 cursor-not-allowed',
        isDark
          ? 'border-white/15 bg-charcoal hover:border-accent/50 hover:bg-charcoal/90'
          : 'border-border bg-white hover:border-accent/40 hover:shadow-soft'
      )}
    >
      <input
        type="file"
        accept="image/png,image/jpeg,image/webp,image/svg+xml"
        className="sr-only"
        disabled={disabled || isUploading}
        onChange={onChange}
      />
      <div className="px-4 pt-4 pb-2">
        <p className={cn('text-xs font-bold uppercase tracking-wider', isDark ? 'text-subtle' : 'text-muted')}>
          {label}
        </p>
        <p className={cn('text-[11px] mt-1 leading-snug', isDark ? 'text-subtle/80' : 'text-muted')}>{hint}</p>
      </div>
      <div className="flex-1 flex flex-col items-center justify-center px-6 pb-5 gap-3">
        {previewUrl ? (
          <img src={previewUrl} alt="" className="max-h-14 max-w-full object-contain" />
        ) : (
          <div
            className={cn(
              'w-12 h-12 rounded-xl flex items-center justify-center',
              isDark ? 'bg-white/10 text-subtle' : 'bg-surface text-muted'
            )}
          >
            <svg className="w-6 h-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth="1.5">
              <path d="M12 16V4m0 0l-4 4m4-4l4 4M4 20h16" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
        )}
        <span
          className={cn(
            'text-xs font-semibold text-center',
            isDark ? 'text-white/90 group-hover:text-accent' : 'text-charcoal group-hover:text-accent'
          )}
        >
          {isUploading ? 'Uploading…' : disabled && disabledHint ? disabledHint : previewUrl ? uploadLabel : emptyLabel}
        </span>
      </div>
    </label>
  )
}
