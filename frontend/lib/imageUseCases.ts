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

/** Preset image aspect ratios — campaign default + per-variant override. */
export const IMAGE_ASPECT_RATIO_OPTIONS = [
  { id: '1:1', label: '1:1', desc: 'Instagram · Facebook feed' },
  { id: '4:3', label: '4:3', desc: 'Fashion retail · portrait feed' },
  { id: '4:5', label: '4:5', desc: 'Instagram portrait feed' },
  { id: '9:16', label: '9:16', desc: 'Reels · Stories · TikTok' },
  { id: '16:9', label: '16:9', desc: 'Website · YouTube · Landscape' },
  { id: '1.91:1', label: '1.91:1', desc: 'Facebook · Google ads' },
  { id: '2:3', label: '2:3', desc: 'Pinterest · Print' },
] as const

export function effectiveVariantAspectRatio(
  slot: Pick<ImageVariantSlot, 'aspect_ratio' | 'aspect_ratio_custom'>,
  campaignDefault: string,
): string {
  const custom = (slot.aspect_ratio_custom || '').trim()
  if (custom) return custom
  const chosen = (slot.aspect_ratio || '').trim()
  const fallback = (campaignDefault || '').trim()
  return chosen || fallback || '1:1'
}

/** Restore preset vs custom ratio fields from saved brief data. */
export function normalizeVariantAspectFromStorage(raw: {
  aspect_ratio?: unknown
  aspect_ratio_custom?: unknown
}): Pick<ImageVariantSlot, 'aspect_ratio' | 'aspect_ratio_custom'> {
  const customStored = String(raw.aspect_ratio_custom || '').trim()
  if (customStored) {
    const preset = String(raw.aspect_ratio || '').trim()
    return {
      aspect_ratio_custom: customStored,
      aspect_ratio: preset || undefined,
    }
  }
  const ar = String(raw.aspect_ratio || '').trim()
  if (ar && !IMAGE_ASPECT_RATIO_OPTIONS.some((o) => o.id === ar)) {
    return { aspect_ratio_custom: ar }
  }
  return { aspect_ratio: ar || undefined }
}

export type VariantReferencePayload = {
  asset_id?: string
  file_url: string
  analysis?: Record<string, unknown>
  is_product_reference?: boolean
}

export type VariantReferenceImage = {
  file_url: string
  asset_id?: string
}

export const MAX_VARIANT_REFERENCE_IMAGES = 5

/** Per-variant refs — supports legacy single-field storage. */
export function variantReferenceImages(
  slot: Pick<
    ImageVariantSlot,
    'reference_images' | 'reference_image_url' | 'reference_image_asset_id'
  >,
): VariantReferenceImage[] {
  const fromArray = (slot.reference_images ?? [])
    .map((r) => ({
      file_url: (r.file_url || '').trim(),
      asset_id: r.asset_id || undefined,
    }))
    .filter((r) => r.file_url)
  if (fromArray.length) return fromArray.slice(0, MAX_VARIANT_REFERENCE_IMAGES)
  const url = (slot.reference_image_url || '').trim()
  if (!url) return []
  return [
    {
      file_url: url,
      asset_id: slot.reference_image_asset_id || undefined,
    },
  ]
}

export function normalizeVariantReferenceImagesFromStorage(raw: {
  reference_images?: unknown
  reference_image_url?: unknown
  reference_image_asset_id?: unknown
}): Pick<ImageVariantSlot, 'reference_images'> {
  if (Array.isArray(raw.reference_images)) {
    const refs = raw.reference_images
      .filter((item): item is Record<string, unknown> => typeof item === 'object' && item !== null)
      .map((item) => ({
        file_url: String(item.file_url || '').trim(),
        asset_id: String(item.asset_id || '').trim() || undefined,
      }))
      .filter((r) => r.file_url)
      .slice(0, MAX_VARIANT_REFERENCE_IMAGES)
    if (refs.length) return { reference_images: refs }
  }
  const url = String(raw.reference_image_url || '').trim()
  if (!url) return {}
  return {
    reference_images: [
      {
        file_url: url,
        asset_id: String(raw.reference_image_asset_id || '').trim() || undefined,
      },
    ],
  }
}

/** Campaign refs plus optional per-variant uploads (variant refs listed first). */
export function referenceImagesPayloadForVariant(
  slot: Pick<
    ImageVariantSlot,
    'reference_images' | 'reference_image_url' | 'reference_image_asset_id'
  >,
  campaignRefs: VariantReferencePayload[],
): VariantReferencePayload[] {
  const variantRefs = variantReferenceImages(slot).map((r) => ({
    asset_id: r.asset_id,
    file_url: r.file_url,
    analysis: {},
  }))
  if (!variantRefs.length) return campaignRefs
  const variantUrls = new Set(variantRefs.map((r) => r.file_url))
  return [...variantRefs, ...campaignRefs.filter((r) => !variantUrls.has(r.file_url))].slice(
    0,
    MAX_VARIANT_REFERENCE_IMAGES,
  )
}

/**
 * Where the brand logo goes inside an ad image. '' keeps the long-standing look (logo in a slim white
 * strip across the top). Every other choice puts the real logo file inside the picture, in a corner the
 * text does not use, in the light or dark version that suits the picture. Static ads and carousel
 * cards only; reels and videos get their logo on the finished video.
 */
export type LogoPositionId =
  | ''
  | 'auto'
  | 'top_left'
  | 'top_right'
  | 'bottom_left'
  | 'bottom_right'
  | 'top_center'
  | 'bottom_center'
  | 'center'
  | 'none'

export const LOGO_POSITION_OPTIONS: { value: LogoPositionId; label: string }[] = [
  { value: '', label: 'White strip on top (current)' },
  { value: 'auto', label: "Auto — designer's choice (varies per image)" },
  { value: 'top_left', label: 'Top left' },
  { value: 'top_right', label: 'Top right' },
  { value: 'bottom_left', label: 'Bottom left' },
  { value: 'bottom_right', label: 'Bottom right' },
  { value: 'top_center', label: 'Top centre' },
  { value: 'bottom_center', label: 'Bottom centre' },
  { value: 'center', label: 'Centre (rare)' },
  { value: 'none', label: 'No logo on the image' },
]

/** The brand's colour palette: up to three colours, set on the Brand page. */
export type PaletteRole = 'primary' | 'secondary' | 'tertiary'
export const PALETTE_ROLES: { id: PaletteRole; label: string }[] = [
  { id: 'primary', label: 'Colour 1' },
  { id: 'secondary', label: 'Colour 2' },
  { id: 'tertiary', label: 'Colour 3' },
]

export function normalizePaletteColors(value: unknown): Partial<Record<PaletteRole, string>> | undefined {
  if (!value || typeof value !== 'object') return undefined
  const out: Partial<Record<PaletteRole, string>> = {}
  for (const { id } of PALETTE_ROLES) {
    const v = String((value as Record<string, unknown>)[id] ?? '').trim()
    if (v) out[id] = v
  }
  return Object.keys(out).length ? out : undefined
}

export function normalizePalette(value: unknown): PaletteRole[] | undefined {
  if (!Array.isArray(value)) return undefined
  const picked = PALETTE_ROLES.map((r) => r.id).filter((id) => value.includes(id))
  return picked.length ? picked : undefined
}

export function normalizeLogoPosition(value: unknown): LogoPositionId {
  const s = String(value ?? '').trim()
  return LOGO_POSITION_OPTIONS.some((o) => o.value === s) ? (s as LogoPositionId) : ''
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
  /** Optional override — e.g. 3:4 or 1200x628 (takes priority over preset). */
  aspect_ratio_custom?: string
  /** Optional reference images for this variant only (max 5). */
  reference_images?: VariantReferenceImage[]
  /** @deprecated Legacy single ref — use reference_images. */
  reference_image_url?: string
  /** @deprecated Legacy single ref — use reference_images. */
  reference_image_asset_id?: string
  /** Retail / ecommerce: product-only catalog shot vs person with product. */
  product_focus?: 'product_only' | 'with_person' | 'product_with_person' | ''
  /** Specific product/model from scraped catalog (e.g. NEO + 20 2026). */
  product_model?: string
  /** Where the brand logo sits inside this image. Empty = follow the campaign setting. */
  logo_corner?: LogoPositionId
  /** Which of the brand's colours this image uses. Empty / missing = all of them. */
  palette?: PaletteRole[]
  /** Colour codes typed on this variant; they replace the brand's colour in that slot (or fill an empty third one). */
  palette_colors?: Partial<Record<PaletteRole, string>>
  /**
   * Where the prompt text came from. 'strategy' = the short scene note copied from the MD file (still to
   * be expanded by Generate AI); 'ai' = written by the prompt-writing AI; 'user' = typed or edited by hand.
   * Only hand-written prompts are kept exactly as written; the other two are scenes to build on.
   */
  prompt_source?: 'strategy' | 'ai' | 'user'
  /** The prompt is a full designer brief read from the MD file: Generate AI builds on it and keeps its exact text. */
  brief_complete?: boolean
  /** The MD file's own hook / primary text. Generate AI must not replace it with an invented angle. */
  strategy_hook?: string
  strategy_message?: string
  /** ISO timestamp when AI plan was last generated for this variant. */
  generated_at: string | null
}

/**
 * What "Generate AI" does with a slot's prompt. A prompt a person wrote or edited is kept exactly. The short
 * scene note copied from the strategy file is replaced by the AI's expansion of it (before this, the note
 * always won, so the AI's prompt was thrown away and the image was made from a one-line note).
 */
export function promptAfterAiPlan(
  slot: Pick<ImageVariantSlot, 'prompt' | 'prompt_source' | 'brief_complete'>,
  aiPrompt: string | undefined,
): { prompt: string; prompt_source: ImageVariantSlot['prompt_source'] } {
  const prior = (slot.prompt || '').trim()
  const ai = (aiPrompt || '').trim()
  if (prior && slot.prompt_source !== 'strategy') return { prompt: prior, prompt_source: slot.prompt_source }
  if (ai) return { prompt: slot.brief_complete ? ensureBriefText(ai, prior) : ai, prompt_source: 'ai' }
  return { prompt: prior, prompt_source: slot.prompt_source }
}

/**
 * A designer brief spells out the exact words for the image (headline, callouts, message, CTA). The AI's
 * rewrite must carry every one of them: any line of the brief whose words are missing from the AI prompt is
 * added back, word for word.
 */
export function ensureBriefText(aiPrompt: string, brief: string): string {
  const have = aiPrompt.toLowerCase().replace(/\s+/g, ' ')
  const keys = ['Main headline:', 'Subheadline:', 'Supporting text:', 'Benefit callouts:', 'Message:', 'CTA button:']
  const missing: string[] = []
  for (const line of brief.split('\n')) {
    const key = keys.find((k) => line.startsWith(k))
    if (!key) continue
    const text = line.slice(key.length).trim().replace(/^"|"$/g, '').replace(/\s+/g, ' ')
    if (text && !have.includes(text.toLowerCase())) missing.push(`${key} ${line.slice(key.length).trim()}`)
  }
  if (!missing.length) return aiPrompt
  return `${aiPrompt}\n\nText that must appear on the image exactly as written:\n${missing.join('\n')}`
}

/**
 * The copy Generate AI leaves on a slot. Text that came from the strategy file is the source of truth, so the
 * AI cannot swap a carousel's "What happens at an Adoria consultation?" for an angle of its own.
 */
export function copyAfterAiPlan(
  slot: Pick<ImageVariantSlot, 'hook' | 'message' | 'strategy_hook' | 'strategy_message'>,
  ai: { hook?: string; message?: string },
): { hook: string; message: string; fromStrategy: boolean } {
  const fromStrategy = Boolean((slot.strategy_hook || '').trim())
  return {
    hook: (slot.strategy_hook || '').trim() || ai.hook || slot.hook,
    message: (slot.strategy_message || '').trim() || ai.message || slot.message,
    fromStrategy,
  }
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
