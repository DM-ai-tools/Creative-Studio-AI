'use client'

import React from 'react'
import toast from 'react-hot-toast'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import ImageVariantSlotsPanel from '@/components/brief/ImageVariantSlotsPanel'
import {
  emptyImageVariantSlot,
  normalizeLogoPosition,
  normalizePalette,
  normalizePaletteColors,
  normalizeProductFocus,
  normalizeVariantAspectFromStorage,
  normalizeVariantReferenceImagesFromStorage,
  resizeImageVariantSlots,
  type ImageVariantSlot,
} from '@/lib/imageUseCases'
import { brandsApi, briefsApi } from '@/lib/api'
import { useActiveBrand } from '@/hooks/useActiveBrand'
import { extractApiError } from '@/lib/apiErrors'
import type { Brief, BrandFacts, CatalogOption } from '@/types'

function catalogProductsFromBrief(brief: Brief): string[] {
  const kb = (brief.key_benefits ?? {}) as Record<string, unknown>
  const voice = kb.voice_rules as Record<string, unknown> | undefined
  const facts = (voice?.brand_facts ?? kb.brand_facts) as BrandFacts | undefined
  return Array.isArray(facts?.products)
    ? facts!.products!.map((p) => String(p).trim()).filter(Boolean)
    : []
}

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
    format: v.format ? String(v.format) : undefined,
    carousel_index: v.carousel_index ? Number(v.carousel_index) : undefined,
    carousel_total: v.carousel_total ? Number(v.carousel_total) : undefined,
    product_focus: normalizeProductFocus(v.product_focus),
    product_model: String(v.product_model || ''),
    logo_corner: normalizeLogoPosition(v.logo_corner) || undefined,
    palette: normalizePalette(v.palette),
    palette_colors: normalizePaletteColors(v.palette_colors),
    brief_complete: v.brief_complete ? true : undefined,
    prompt_source: (['strategy', 'ai', 'user'] as const).find((p) => p === v.prompt_source),
    ...normalizeVariantAspectFromStorage(v),
    ...normalizeVariantReferenceImagesFromStorage(v),
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
    format: s.format || undefined,
    carousel_index: s.carousel_index || undefined,
    carousel_total: s.carousel_total || undefined,
    aspect_ratio: s.aspect_ratio || undefined,
    aspect_ratio_custom: s.aspect_ratio_custom?.trim() || undefined,
    reference_images: s.reference_images?.length
      ? s.reference_images.map((r) => ({
          file_url: r.file_url.trim(),
          asset_id: r.asset_id || undefined,
        }))
      : undefined,
    product_focus: s.product_focus || undefined,
    product_model: s.product_model?.trim() || undefined,
    logo_corner: s.logo_corner || undefined,
    palette: s.palette?.length ? s.palette : undefined,
    palette_colors: s.palette_colors && Object.keys(s.palette_colors).length ? s.palette_colors : undefined,
    brief_complete: s.brief_complete || undefined,
    prompt_source: s.prompt_source || undefined,
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
  const { activeBrandId } = useActiveBrand()
  const colourBrandId = brief.brand_id || activeBrandId || ''
  const [brandColors, setBrandColors] = React.useState<{ primary?: string; secondary?: string; tertiary?: string }>({})
  React.useEffect(() => {
    if (!colourBrandId) return
    let cancelled = false
    void (async () => {
      let primary: string | undefined
      let secondary: string | undefined
      try {
        const brand = await brandsApi.get(colourBrandId)
        primary = brand.primary_color || undefined
        secondary = brand.secondary_color || undefined
      } catch {
        try {
          const found = (await brandsApi.list()).find((b) => b.id === colourBrandId)
          primary = found?.primary_color || undefined
          secondary = found?.secondary_color || undefined
        } catch {
          /* fall through to the Brand Kit colours */
        }
      }
      let kit: Record<string, unknown> = {}
      try {
        kit = ((await brandsApi.getKit(colourBrandId)).colors ?? {}) as Record<string, unknown>
      } catch {
        /* no kit yet */
      }
      if (cancelled) return
      setBrandColors({
        primary: primary || String(kit.primary || '') || undefined,
        secondary: secondary || String(kit.secondary || '') || undefined,
        tertiary: String(kit.tertiary || '') || undefined,
      })
    })()
    return () => {
      cancelled = true
    }
  }, [colourBrandId])

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
            toast('Regenerate AI plans from New project, then edit and save here')
          }
          onGenerateAll={() =>
            toast('Regenerate AI plans from New project, then edit and save here')
          }
          angleOptions={angleOptions}
          catalogProducts={catalogProductsFromBrief(brief)}
          brandId={colourBrandId || undefined}
          brandColors={brandColors}
          logoCorner={normalizeLogoPosition((brief.key_benefits as Record<string, unknown> | undefined)?.image_logo_corner)}
          defaultAspectRatio={
            String(
              (brief.key_benefits as Record<string, unknown> | undefined)?.image_aspect_ratio || '',
            ).trim() || '1:1'
          }
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
