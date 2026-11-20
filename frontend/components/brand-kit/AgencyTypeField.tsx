'use client'

import React, { useEffect, useState } from 'react'
import Input from '@/components/ui/Input'
import Select from '@/components/ui/Select'

/** Value of the "type your own" entry in the list. Never saved: the typed text is what gets saved. */
export const AGENCY_TYPE_OTHER = '__other__'

type Preset = { value: string; label: string }

interface Props {
  label?: string
  /** What is saved on the brand: one of the preset values, or whatever the user typed. */
  value: string
  onChange: (value: string) => void
  presets: readonly Preset[]
}

/**
 * Agency type: pick one of the ready-made types, or choose "Other" and type your own (for example
 * "Dental clinic", "Solar installer", "Water utilities"). A typed value is saved exactly as typed, and a
 * brand that already has a custom value opens with the "Other" box filled in.
 */
export default function AgencyTypeField({ label = 'Agency type', value, onChange, presets }: Props) {
  const current = value ?? ''
  const isPreset = presets.some((p) => p.value === current)
  const [typing, setTyping] = useState(() => Boolean(current.trim()) && !isPreset)

  // Follow the brand being edited: a preset closes the box, a custom value opens it.
  useEffect(() => {
    if (isPreset) setTyping(false)
    else if (current.trim()) setTyping(true)
  }, [current, isPreset])

  const selected = typing ? AGENCY_TYPE_OTHER : isPreset ? current : ''

  return (
    <div className="w-full space-y-3">
      <Select
        label={label}
        value={selected}
        onChange={(event) => {
          const next = event.target.value
          if (next === AGENCY_TYPE_OTHER) {
            setTyping(true)
            if (isPreset) onChange('') // start the typed entry empty instead of keeping the preset
            return
          }
          setTyping(false)
          onChange(next)
        }}
        placeholder="Select a type"
        options={[...presets.map((p) => ({ value: p.value, label: p.label })), { value: AGENCY_TYPE_OTHER, label: 'Other — type your own…' }]}
      />
      {typing && (
        <Input
          label="Your agency or business type"
          placeholder="e.g. Dental clinic, Solar installer, Water utilities"
          value={isPreset ? '' : current}
          maxLength={100}
          autoFocus={isPreset || !current}
          onChange={(event) => onChange(event.target.value)}
          onBlur={() => onChange(current.trim())}
          hint="Saved exactly as you type it and used to understand the business."
        />
      )}
    </div>
  )
}
