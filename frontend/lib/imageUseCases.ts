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
  /** static | carousel — from strategy MD Type column when present. */
  format?: string
  /** 1-based index when this slot is one swipe card in a carousel. */
  carousel_index?: number
  carousel_total?: number
  /** Groups cards that belong to the same Meta carousel creative (e.g. creative-1). */
  carousel_group?: string
  /** Fashion retail: model + outfit photo only — feed copy stays off-image. */
  photo_only?: boolean
  /** Client-style retail promo (headline + offer burned on image). */
  retail_promo?: boolean
  aspect_ratio?: string
  /** Retail / ecommerce: product-only catalog shot vs person with product. */
  product_focus?: 'product_only' | 'with_person' | 'product_with_person' | ''
  /** Specific product/model from scraped catalog (e.g. NEO + 20 2026). */
  product_model?: string
  /** ISO timestamp when AI plan was last generated for this variant. */
  generated_at: string | null
}

export function isCarouselSlot(slot: ImageVariantSlot, formats?: string[]): boolean {
  if (slot.format === 'carousel') return true
  if (slot.format === 'static') return false
  const fmts = formats ?? []
  return fmts.includes('carousel') && !fmts.includes('static')
}

export function isLastCarouselCard(
  slot: ImageVariantSlot,
  index: number,
  slots: ImageVariantSlot[],
  formats?: string[]
): boolean {
  if (!isCarouselSlot(slot, formats)) return false
  // Prefer explicit per-creative index/total (Card 6 of 6 in Creative 1, etc.).
  if (slot.carousel_index && slot.carousel_total) {
    return slot.carousel_index >= slot.carousel_total
  }
  // Same carousel_group: last slot in that group.
  if (slot.carousel_group) {
    const groupIdxs = slots
      .map((s, i) => (s.carousel_group === slot.carousel_group ? i : -1))
      .filter((i) => i >= 0)
    return groupIdxs[groupIdxs.length - 1] === index
  }
  const idxs = slots
    .map((s, i) => (isCarouselSlot(s, formats) ? i : -1))
    .filter((i) => i >= 0)
  return idxs[idxs.length - 1] === index
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
    product_focus: '',
    product_model: '',
    generated_at: null,
  }
}

/** Returns a human-readable hint for each product_focus value shown inside a slot card. */
export function productFocusSlotHint(focus: string | undefined): string | null {
  switch (focus) {
    case 'product_only':
      return 'Product-only catalog hero — no people in frame.'
    case 'product_with_person':
      return 'Product fills 60–70% of frame; person adds lifestyle context in the scene.'
    case 'with_person':
      return 'Person / model is the main subject — product clearly visible.'
    default:
      return null
  }
}

export const PRODUCT_FOCUS_OPTIONS = [
  { value: '', label: 'Auto (AI decides)' },
  { value: 'product_only', label: 'Product alone — catalog / studio hero' },
  { value: 'product_with_person', label: 'Product hero + person for lifestyle context' },
  { value: 'with_person', label: 'Person / model is the main subject' },
] as const

export type ProductFocusId = 'product_only' | 'product_with_person' | 'with_person'

export function normalizeProductFocus(value: unknown): ImageVariantSlot['product_focus'] {
  const s = String(value ?? '').trim()
  if (s === 'product_only' || s === 'with_person' || s === 'product_with_person') return s
  return ''
}

export function labelForProductFocus(value: string | undefined): string {
  return PRODUCT_FOCUS_OPTIONS.find((o) => o.value === (value || ''))?.label ?? 'Auto'
}

export type OnImageStyleId =
  | 'auto'
  | 'retail_modern'
  | 'jewellery_luxury'
  | 'fashion_editorial'
  | 'high_contrast'

export const ON_IMAGE_STYLE_OPTIONS: {
  value: OnImageStyleId
  label: string
  hint: string
}[] = [
  {
    value: 'auto',
    label: 'Auto (by industry)',
    hint: 'Jewellery → gold luxury · Fashion promo → editorial white · Else → modern retail',
  },
  {
    value: 'retail_modern',
    label: 'Modern retail',
    hint: 'White sans-serif on dark gradient — bike shops, services, general retail',
  },
  {
    value: 'jewellery_luxury',
    label: 'Jewellery luxury',
    hint: 'Champagne gold serif + script — Adoria-style jeweller ads only',
  },
  {
    value: 'fashion_editorial',
    label: 'Fashion editorial',
    hint: 'White serif caps + offer bar — Runway Secrets / clothing promo',
  },
  {
    value: 'high_contrast',
    label: 'High contrast',
    hint: 'Bold white caps sans + strong CTA — urgency / performance',
  },
]

export function labelForOnImageStyle(value: string | undefined): string {
  return ON_IMAGE_STYLE_OPTIONS.find((o) => o.value === (value || 'auto'))?.label ?? 'Auto'
}

const DANGLING_LAST =
  /^(to|for|and|or|of|a|an|the|with|your|our|my|at|in|on|from|by|is|are)$/i

export function isIncompleteOnImageLine(text: string): boolean {
  const words = text.trim().split(/\s+/).filter(Boolean)
  if (!words.length) return true
  const last = words[words.length - 1].replace(/[^a-zA-Z']/g, '')
  return DANGLING_LAST.test(last)
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
    // Keep short complete lines whole (e.g. "What happens at an Adoria consultation?")
    if (words.length <= max) return text.trim().replace(/[,;:-]+$/, '')
    let out = words.slice(0, max).join(' ').replace(/[,;:-]+$/, '')
    while (DANGLING_LAST.test(out.split(/\s+/).pop() || '')) {
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
    const hookWords = hook.trim().split(/\s+/).filter(Boolean)
    image_hook = hookWords.length <= 8 ? hook.trim() : clip(hook, 6)
    const same = hook.trim().toLowerCase() === message.trim().toLowerCase()
    image_headline = same ? '' : clip(message, 8)
  }

  return {
    image_hook: isIncompleteOnImageLine(image_hook) ? clip(hook, 8) : image_hook,
    image_headline: isIncompleteOnImageLine(image_headline) ? '' : image_headline,
  }
}

export function resizeImageVariantSlots(
  prev: ImageVariantSlot[],
  count: number
): ImageVariantSlot[] {
  const n = Math.max(1, Math.min(100, Math.round(count) || 1))
  if (prev.length === n) return prev
  if (prev.length < n) {
    return [
      ...prev,
      ...Array.from({ length: n - prev.length }, () => emptyImageVariantSlot()),
    ]
  }
  return prev.slice(0, n)
}

/** Split slot indices into carousel creative groups (or chunks of 6) for batched AI plans. */
export function chunkSlotIndicesForGeneration(slots: ImageVariantSlot[]): number[][] {
  if (!slots.length) return []

  const hasGroups = slots.some((s) => (s.carousel_group || '').trim())
  if (hasGroups) {
    const chunks: number[][] = []
    let current: number[] = []
    let group = ''
    for (let i = 0; i < slots.length; i++) {
      const g = (slots[i].carousel_group || '').trim()
      if (g && group && g !== group && current.length) {
        chunks.push(current)
        current = []
      }
      if (g) group = g
      current.push(i)
    }
    if (current.length) chunks.push(current)
    return chunks
  }

  const size = 6
  const chunks: number[][] = []
  for (let i = 0; i < slots.length; i += size) {
    chunks.push(Array.from({ length: Math.min(size, slots.length - i) }, (_, j) => i + j))
  }
  return chunks
}
