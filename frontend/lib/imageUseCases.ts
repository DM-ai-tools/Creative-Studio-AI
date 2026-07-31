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
  /** Full post hook (shown as-is on the variant / feed). */
  hook: string
  /** Full post headline (shown as-is on the variant / feed). */
  message: string
  /** Catchy related line burned onto the photo (max ~6 words). */
  image_hook: string
  /** Catchy related headline burned onto the photo (max ~8 words). */
  image_headline: string
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
    image_hook: '',
    image_headline: '',
    cta: '',
    offer: '',
    prompt: '',
    reasoning: '',
    ad_angle: '',
    generated_at: null,
  }
}

/** Fallback catchy on-image lines when AI omits image_hook / image_headline.
 * Same idea as the full hook/headline — never invent a new FOMO angle.
 */
export function relatedOnImageLines(hook: string, message: string): {
  image_hook: string
  image_headline: string
} {
  const clip = (text: string, max: number) => {
    const words = text.trim().split(/\s+/).filter(Boolean)
    if (!words.length) return ''
    let out = words.slice(0, max).join(' ').replace(/[,;:-]+$/, '')
    while (/\b(to|for|and|or|of|a|the|with)$/i.test(out)) {
      const parts = out.split(/\s+/)
      if (parts.length <= 1) break
      out = parts.slice(0, -1).join(' ')
    }
    return out
  }

  const combined = `${hook} ${message}`.toLowerCase()
  let image_hook = ''
  let image_headline = ''

  if (/big four|big bank|bank offer|bank rate/.test(combined)) {
    image_hook = "Big banks aren't your only option"
    image_headline = 'Access lower broker rates'
  } else if (/broker/.test(combined) && /rate/.test(combined)) {
    image_hook = 'Broker-only rates beat banks'
    image_headline = 'See what you could save'
  } else if (/rate/.test(combined) && /save|saving|lower|cheaper/.test(combined)) {
    image_hook = 'Still overpaying on rates?'
    image_headline = 'Lock a better home loan'
  } else if (/first home|homebuyer|home buyer|home loan/.test(combined)) {
    image_hook = 'Ready for a better loan?'
    image_headline = 'Compare broker-only rates'
  } else if (/refinance|refi/.test(combined)) {
    image_hook = 'Refinance before rates move'
    image_headline = 'Check your broker options'
  } else {
    image_hook = clip(hook, 6)
    image_headline = clip(message, 8)
  }

  return {
    image_hook: clip(image_hook, 7),
    image_headline: clip(image_headline, 8),
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
