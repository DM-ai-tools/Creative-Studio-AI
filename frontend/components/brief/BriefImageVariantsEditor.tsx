'use client'

import React from 'react'
import toast from 'react-hot-toast'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import ImageVariantSlotsPanel from '@/components/brief/ImageVariantSlotsPanel'
import {
  emptyImageVariantSlot,
  resizeImageVariantSlots,
  type ImageVariantSlot,
} from '@/lib/imageUseCases'
import { briefsApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import type { Brief, CatalogOption } from '@/types'

export function slotsFromBrief(brief: Brief): ImageVariantSlot[] {
  const kb = brief.key_benefits ?? {}
  const raw = Array.isArray(kb.image_variants)
    ? (kb.image_variants as Record<string, unknown>[])
    : []
  const count = Math.max(1, Number(kb.target_variant_count) || raw.length || 1)
  if (raw.length === 0) {
    return resizeImageVariantSlots([emptyImageVariantSlot()], count)
  }
  const mapped = raw.map((v) => ({
    use_cases: Array.isArray(v.use_cases) ? (v.use_cases as string[]) : [],
    hook: String(v.hook || ''),
    message: String(v.message || ''),
    image_hook: String(v.image_hook || ''),
    image_headline: String(v.image_headline || ''),
    cta: String(v.cta || ''),
    offer: String(v.offer || ''),
    prompt: String(v.prompt || ''),
    reasoning: String(v.reasoning || ''),
    ad_angle: String(v.ad_angle || ''),
    generated_at: v.generated_at ? String(v.generated_at) : null,
  }))
  return resizeImageVariantSlots(mapped, count)
}

export function serializeImageVariants(slots: ImageVariantSlot[]) {
  return slots.map((s) => ({
    use_cases: s.use_cases,
    hook: s.hook.trim(),
    message: s.message.trim(),
    image_hook: s.image_hook.trim(),
    image_headline: s.image_headline.trim(),
    cta: s.cta.trim(),
    offer: s.offer.trim(),
    prompt: s.prompt.trim(),
    reasoning: s.reasoning.trim() || undefined,
    ad_angle: s.ad_angle || undefined,
    generated_at: s.generated_at ?? undefined,
  }))
}

type Props = {
  brief: Brief
  slots: ImageVariantSlot[]
  onChange(slots: ImageVariantSlot[]): void
  angleOptions?: CatalogOption[]
  onSaved?(): void
}

export default function BriefImageVariantsEditor({
  brief,
  slots,
  onChange,
  angleOptions,
  onSaved,
}: Props) {
  const [saving, setSaving] = React.useState(false)

  const handleSave = async () => {
    setSaving(true)
    try {
      const kb = { ...(brief.key_benefits ?? {}) }
      const serialized = serializeImageVariants(slots)
      await briefsApi.update(brief.id, {
        key_benefits: {
          ...kb,
          image_variants: serialized,
          ...(serialized[0]?.use_cases?.length
            ? { image_use_cases: serialized[0].use_cases }
            : {}),
          ...(serialized[0]?.prompt
            ? { image_prompt_override: serialized[0].prompt }
            : {}),
        },
      })
      toast.success('Image variant plans saved — Generate will use your edits')
      onSaved?.()
    } catch (err: unknown) {
      toast.error(extractApiError(err) || 'Could not save image plans')
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card
      title="Edit image variant plans"
      subtitle="These fields drive the generated image, hook, headline, and caption. Save before Generate."
    >
      <div className="space-y-4">
        <ImageVariantSlotsPanel
          slots={slots}
          onChange={onChange}
          generatingIndex={null}
          onGenerateSlot={() =>
            toast('Regenerate AI plans from Create Brief, then edit and save here')
          }
          onGenerateAll={() =>
            toast('Regenerate AI plans from Create Brief, then edit and save here')
          }
          angleOptions={angleOptions}
        />
        <div className="flex justify-end">
          <Button type="button" variant="primary" isLoading={saving} onClick={() => void handleSave()}>
            Save image plans
          </Button>
        </div>
      </div>
    </Card>
  )
}
