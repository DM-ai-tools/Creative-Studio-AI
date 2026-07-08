'use client'

import { useState } from 'react'
import Select from '@/components/ui/Select'
import { cn } from '@/lib/utils'
import {
  HEYGEN_ANNIE_OFFICE_AVATAR,
  buildHeyGenAvatarSelectGroups,
  flattenHeyGenAvatarSelectGroups,
  isAnnieOption,
} from '@/lib/heygenAvatars'
import CreateAvatarModal from '@/components/brief/CreateAvatarModal'
import type { GenerationCatalog } from '@/types'

interface HeyGenAvatarPickerProps {
  catalog?: Pick<GenerationCatalog, 'heygen_avatar_options' | 'heygen_avatar_featured'> | null
  avatarId: string
  onAvatarChange(id: string): void
  disabled?: boolean
  /** Compact layout for BriefGenerationPanel */
  compact?: boolean
}

export default function HeyGenAvatarPicker({
  catalog,
  avatarId,
  onAvatarChange,
  disabled,
  compact = false,
}: HeyGenAvatarPickerProps) {
  const [createOpen, setCreateOpen] = useState(false)
  const groups = buildHeyGenAvatarSelectGroups(catalog)
  const allOptions = flattenHeyGenAvatarSelectGroups(groups)
  const validIds = new Set(allOptions.map((o) => o.value))
  const selectValue = validIds.has(avatarId) ? avatarId : ''

  const quickPicks = [
    HEYGEN_ANNIE_OFFICE_AVATAR,
    ...allOptions
      .filter((o) => o.value !== HEYGEN_ANNIE_OFFICE_AVATAR.id)
      .slice(0, compact ? 3 : 5)
      .map((o) => ({ id: o.value, label: o.label })),
  ]

  const handleAvatarReady = (lookId: string, _name: string) => {
    onAvatarChange(lookId)
    setCreateOpen(false)
  }

  if (groups.length === 0) {
    return (
      <div className="space-y-2">
        <p className="text-xs text-amber-800">
          No HeyGen avatars — restart the backend after updating .env.
        </p>
        <button
          type="button"
          onClick={() => setCreateOpen(true)}
          className="text-xs font-semibold text-accent underline underline-offset-2"
        >
          + Create your own avatar
        </button>
        <CreateAvatarModal
          open={createOpen}
          onClose={() => setCreateOpen(false)}
          onAvatarReady={handleAvatarReady}
        />
      </div>
    )
  }

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-[10px] font-bold uppercase tracking-wide text-navy">
          Quick pick
        </p>
        <button
          type="button"
          disabled={disabled}
          onClick={() => setCreateOpen(true)}
          className={cn(
            'flex items-center gap-1 text-[10px] font-semibold text-accent bg-accent/10 rounded-lg px-2 py-1 hover:bg-accent/20 transition-colors',
            disabled && 'opacity-50 cursor-not-allowed'
          )}
        >
          <span>＋</span>
          <span>Create avatar</span>
        </button>
      </div>
      <CreateAvatarModal
        open={createOpen}
        onClose={() => setCreateOpen(false)}
        onAvatarReady={handleAvatarReady}
      />
      <div>
        <div className="flex flex-wrap gap-2">
          {quickPicks.map((opt) => {
            const selected = avatarId === opt.id
            const annie = isAnnieOption({ id: opt.id, label: opt.label })
            return (
              <button
                key={opt.id}
                type="button"
                disabled={disabled}
                onClick={() => onAvatarChange(opt.id)}
                className={cn(
                  'rounded-xl border px-3 py-2 text-left text-xs transition-all max-w-[220px]',
                  selected
                    ? 'border-mint bg-[rgba(0,194,168,0.12)] ring-2 ring-mint/40'
                    : 'border-border bg-white hover:border-mint/50',
                  annie && !selected && 'border-mint/40 bg-mint/[0.04]',
                  disabled && 'opacity-50 cursor-not-allowed'
                )}
              >
                <span className="block font-bold text-navy leading-tight">
                  {annie ? '★ Annie' : opt.label.split(' — ').pop() || opt.label}
                </span>
                {!annie && opt.label.includes(' — ') && (
                  <span className="block text-[10px] text-mid truncate">{opt.label}</span>
                )}
                {annie && (
                  <span className="block text-[10px] text-mid">Office standing front</span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <Select
        label={compact ? undefined : 'Avatar (on-screen)'}
        groups={groups}
        placeholder="Select avatar"
        value={selectValue}
        disabled={disabled}
        hint={
          compact
            ? undefined
            : 'Annie is first under “Annie — office presenter”, or use Quick pick above.'
        }
        onChange={(e) => {
          const v = e.target.value
          if (v) onAvatarChange(v)
        }}
      />
    </div>
  )
}
