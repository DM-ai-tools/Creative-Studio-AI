/** Shared catalogue of image use-case chips for brief image variants. */

export type ImageUseCaseOption = { id: string; label: string; group: string }

export const IMAGE_USE_CASES: ImageUseCaseOption[] = [
  { id: 'hero_product', label: 'Hero product view', group: 'Brand' },
  { id: 'lifestyle', label: 'Lifestyle image', group: 'Brand' },
  { id: 'product_vibe', label: 'Product in environment', group: 'Brand' },
  { id: 'product_person', label: 'Product with person', group: 'Brand' },
  { id: 'feature_explanation', label: 'Feature explanation', group: 'Brand' },
  { id: 'material_composition', label: 'Material & composition', group: 'Conversion' },
  { id: 'detail_texture', label: 'Detail / texture close-up', group: 'Conversion' },
  { id: 'size_scale', label: 'Size & scale reference', group: 'Conversion' },
  { id: 'multi_angle', label: 'Multi-angle / 360° view', group: 'Conversion' },
  { id: 'color_swatch', label: 'Colour swatch grid', group: 'Conversion' },
  { id: 'packaging_unbox', label: 'Packaging & unboxing', group: 'Conversion' },
  { id: 'comparison', label: 'Comparison imagery', group: 'Conversion' },
  { id: 'platform_crop', label: 'Platform crop variant', group: 'Conversion' },
  { id: 'bs_emotional_using', label: 'People using product', group: 'Best Sellers' },
  { id: 'bs_explaining', label: 'Explaining the product', group: 'Best Sellers' },
  { id: 'bs_ecosystem', label: 'Product in ecosystem', group: 'Best Sellers' },
  { id: 'bs_emotional_appeal', label: 'Emotional buyer appeal', group: 'Best Sellers' },
  { id: 'bs_real_life', label: 'Real-life application', group: 'Best Sellers' },
  { id: 'bs_segments', label: 'Audience segmentation', group: 'Best Sellers' },
  { id: 'bs_price_feature', label: 'Price / feature highlight', group: 'Decision' },
  { id: 'bs_emotion_decision', label: 'Emotion-driven decision', group: 'Decision' },
  { id: 'bs_envision', label: 'Envisioning the need', group: 'Decision' },
  { id: 'bs_skim_vs_buyer', label: 'Skim-scroller vs serious buyer', group: 'Decision' },
  { id: 'bs_artistic', label: 'Artistic perspective', group: 'Decision' },
  { id: 'virtual_tryon', label: 'Virtual try-on (AR)', group: 'Templates' },
]

export const IMAGE_USE_CASE_GROUPS = IMAGE_USE_CASES.map((u) => u.group).filter(
  (g, i, arr) => arr.indexOf(g) === i
)

export function labelForUseCase(id: string): string {
  return (
    IMAGE_USE_CASES.find((u) => u.id === id)?.label ??
    id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
  )
}

/** One creative direction for a single image variant. */
export type ImageVariantSlot = {
  use_cases: string[]
  hook: string
  message: string
  /** On-image CTA button text for this variant only. */
  cta: string
  offer: string
  prompt: string
  reasoning: string
  /** Assigned ad angle id for this variant (e.g. pattern_interrupt). */
  ad_angle: string
  /** ISO timestamp when AI plan was last generated for this variant. */
  generated_at: string | null
}

export function emptyImageVariantSlot(): ImageVariantSlot {
  return {
    use_cases: [],
    hook: '',
    message: '',
    cta: '',
    offer: '',
    prompt: '',
    reasoning: '',
    ad_angle: '',
    generated_at: null,
  }
}

export function resizeImageVariantSlots(
  prev: ImageVariantSlot[],
  count: number
): ImageVariantSlot[] {
  const n = Math.max(1, Math.min(20, Math.round(count) || 1))
  if (prev.length === n) return prev
  if (prev.length < n) {
    return [
      ...prev,
      ...Array.from({ length: n - prev.length }, () => emptyImageVariantSlot()),
    ]
  }
  return prev.slice(0, n)
}
