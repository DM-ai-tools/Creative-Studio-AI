/** Ad angle helpers — multi-select angles map to one angle per image variant. */

export const OBJECTIVE_DEFAULT_ANGLES: Record<string, string[]> = {
  awareness: ['educational', 'pattern_interrupt', 'curiosity_hook', 'myth_busting', 'contrarian'],
  traffic: ['curiosity_hook', 'pattern_interrupt', 'educational', 'pain_led'],
  lead_generation: ['problem_agitate_solve', 'pain_led', 'social_proof', 'founder_led', 'fear_loss_aversion'],
  conversions: ['offer_urgency', 'fomo_scarcity', 'problem_agitate_solve', 'pain_led', 'testimonial'],
  add_to_cart: ['offer_urgency', 'fomo_scarcity', 'before_after', 'social_proof'],
  retention: ['social_proof', 'founder_led', 'testimonial'],
}

/** Rotate selected angles across N variants — one distinct angle per slot when possible. */
export function assignAnglesToVariants(
  selected: string[],
  variantCount: number,
  objectiveId?: string
): string[] {
  const n = Math.max(1, Math.min(20, variantCount || 1))
  let pool = selected.filter(Boolean)
  if (!pool.length) {
    const defaults = OBJECTIVE_DEFAULT_ANGLES[objectiveId ?? ''] ?? OBJECTIVE_DEFAULT_ANGLES.conversions
    pool = defaults.slice(0, Math.max(n, 2))
  }
  return Array.from({ length: n }, (_, i) => pool[i % pool.length])
}

export function labelForAngle(id: string, options?: { id: string; label: string }[]): string {
  return options?.find((o) => o.id === id)?.label ?? id.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}
