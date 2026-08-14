/** Ad angle helpers — multi-select angles map to one angle per image variant. */

export const PRODUCT_CATALOG_ANGLE = 'product_hero'

export const OBJECTIVE_DEFAULT_ANGLES: Record<string, string[]> = {
  awareness: ['educational', 'pattern_interrupt', 'curiosity_hook', 'myth_busting', 'contrarian'],
  traffic: ['curiosity_hook', 'pattern_interrupt', 'educational', 'pain_led'],
  lead_generation: ['problem_agitate_solve', 'pain_led', 'social_proof', 'founder_led', 'fear_loss_aversion'],
  conversions: ['offer_urgency', 'fomo_scarcity', 'problem_agitate_solve', 'pain_led', 'testimonial'],
  add_to_cart: ['offer_urgency', 'fomo_scarcity', 'before_after', 'social_proof'],
  retention: ['social_proof', 'founder_led', 'testimonial'],
}

export type CarouselSlotRef = {
  format?: string
  carousel_group?: string
  carousel_index?: number
  carousel_total?: number
}

function anglePool(selected: string[], objectiveId?: string, n = 1, productFocus?: string): string[] {
  if (productFocus === 'product_only') {
    return [PRODUCT_CATALOG_ANGLE]
  }
  const pool = selected.filter(Boolean)
  if (pool.length) return pool
  const defaults =
    OBJECTIVE_DEFAULT_ANGLES[objectiveId ?? ''] ?? OBJECTIVE_DEFAULT_ANGLES.conversions
  return defaults.slice(0, Math.max(n, 2))
}

function inferCarouselGroup(slot: CarouselSlotRef, index: number, slots: CarouselSlotRef[]): string {
  const explicit = (slot.carousel_group || '').trim()
  if (explicit) return explicit

  const card = Number(slot.carousel_index || 0)
  const prev = index > 0 ? slots[index - 1] : undefined
  const prevCard = Number(prev?.carousel_index || 0)
  const prevTotal = Number(prev?.carousel_total || 0)

  // New creative when card index resets to 1, or previous card closed a carousel.
  if (card === 1 || (prev && prevTotal && prevCard >= prevTotal)) {
    return `inferred-${index}`
  }
  if (prev) {
    return inferCarouselGroup(prev, index - 1, slots)
  }
  return `inferred-${index}`
}

function isCarouselSlotRef(slot: CarouselSlotRef): boolean {
  if (slot.format === 'carousel') return true
  if (slot.format === 'static') return false
  return Boolean(slot.carousel_index && slot.carousel_total)
}

/** Lock one selected angle per carousel creative group (all swipe cards share it). */
export function lockAnglesToCarouselGroups(
  assignments: string[],
  slots: CarouselSlotRef[],
  pool: string[]
): string[] {
  if (!slots.length || !pool.length) return assignments

  const out = [...assignments]
  const groupOrder: string[] = []
  const groupToAngle: Record<string, string> = {}

  for (let i = 0; i < Math.min(out.length, slots.length); i++) {
    const slot = slots[i]
    if (!isCarouselSlotRef(slot)) continue

    const group = inferCarouselGroup(slot, i, slots)
    if (!groupToAngle[group]) {
      const groupIdx = groupOrder.length
      groupOrder.push(group)
      groupToAngle[group] = pool[groupIdx % pool.length]
    }
    out[i] = groupToAngle[group]
  }

  return out
}

/** Rotate selected angles across N variants.
 *  Carousel: one angle per creative group (e.g. 4 angles → 4 creatives × 6 cards). */
export function assignAnglesToVariants(
  selected: string[],
  variantCount: number,
  objectiveId?: string,
  slots?: CarouselSlotRef[],
  productFocus?: string
): string[] {
  const n = Math.max(1, Math.min(100, variantCount || 1))
  const pool = anglePool(selected, objectiveId, n, productFocus)
  const base = Array.from({ length: n }, (_, i) => pool[i % pool.length])
  if (!slots?.length) return base
  return lockAnglesToCarouselGroups(base, slots, pool)
}

export function labelForAngle(id: string, options?: { id: string; label: string }[]): string {
  return options?.find((o) => o.id === id)?.label ?? id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
