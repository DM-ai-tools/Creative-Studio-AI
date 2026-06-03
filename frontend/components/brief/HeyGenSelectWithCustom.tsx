'use client'

import Input from '@/components/ui/Input'
import Select from '@/components/ui/Select'
import { HEYGEN_CUSTOM, withCustomOption } from '@/lib/heygenOptions'
import type { CatalogOption } from '@/types'

interface HeyGenSelectWithCustomProps {
  label: string
  options: CatalogOption[]
  value: string
  customValue: string
  onValueChange(id: string): void
  onCustomChange(text: string): void
  customPlaceholder?: string
}

export default function HeyGenSelectWithCustom({
  label,
  options,
  value,
  customValue,
  onValueChange,
  onCustomChange,
  customPlaceholder = 'Type your custom option…',
}: HeyGenSelectWithCustomProps) {
  const selectValue = options.some((o) => o.id === value) || value === HEYGEN_CUSTOM ? value : HEYGEN_CUSTOM
  const showCustom = selectValue === HEYGEN_CUSTOM

  return (
    <div>
      <Select
        label={label}
        options={withCustomOption(options).map((o) => ({ value: o.id, label: o.label }))}
        value={selectValue}
        onChange={(e) => onValueChange(e.target.value)}
      />
      {showCustom && (
        <Input
          className="mt-2"
          placeholder={customPlaceholder}
          value={customValue}
          onChange={(e) => onCustomChange(e.target.value)}
          aria-label={`${label} custom value`}
        />
      )}
    </div>
  )
}
