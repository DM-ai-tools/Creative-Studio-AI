'use client'

import Select from '@/components/ui/Select'
import {
  buildHeyGenAvatarSelectGroups,
  flattenHeyGenAvatarSelectGroups,
} from '@/lib/heygenAvatars'
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
  const groups = buildHeyGenAvatarSelectGroups(catalog)
  const allOptions = flattenHeyGenAvatarSelectGroups(groups)
  const validIds = new Set(allOptions.map((o) => o.value))
  const selectValue = validIds.has(avatarId) ? avatarId : ''

  if (groups.length === 0) {
    return (
      <p className="text-xs text-amber-800">
        No HeyGen avatars — restart the backend after updating .env.
      </p>
    )
  }

  return (
    <Select
      label={compact ? undefined : 'Avatar (on-screen)'}
      groups={groups}
      placeholder="Select avatar"
      value={selectValue}
      disabled={disabled}
      hint={
        compact
          ? undefined
          : 'Vespri positions load from HeyGen (portrait + landscape). Pick a specific position, not only the group id.'
      }
      onChange={(e) => {
        const v = e.target.value
        if (v) onAvatarChange(v)
      }}
    />
  )
}
