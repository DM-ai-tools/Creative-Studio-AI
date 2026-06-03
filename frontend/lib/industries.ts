/** Industries a client vertical can belong to (per-brief Meta campaign target). */
export const CLIENT_INDUSTRY_OPTIONS = [
  { value: 'real_estate', label: 'Real Estate' },
  { value: 'property_management', label: 'Property Management' },
  { value: 'hospitality', label: 'Hospitality & Tourism' },
  { value: 'healthcare', label: 'Healthcare' },
  { value: 'retail', label: 'Retail & E-commerce' },
  { value: 'dtc', label: 'DTC E-commerce' },
  { value: 'saas', label: 'SaaS / B2B Tech' },
  { value: 'local', label: 'Local / Trades' },
  { value: 'pro_services', label: 'Professional Services' },
  { value: 'automotive', label: 'Automotive' },
  { value: 'education', label: 'Education' },
  { value: 'fitness', label: 'Fitness & Wellness' },
  { value: 'finance', label: 'Finance & Insurance' },
  { value: 'legal', label: 'Legal' },
  { value: 'food_beverage', label: 'Food & Beverage' },
  { value: 'beauty', label: 'Beauty & Personal Care' },
  { value: 'construction', label: 'Construction & Home Services' },
  { value: 'general', label: 'General / Other' },
] as const

/** Agency's own business type (Brand Kit only). */
export const AGENCY_INDUSTRY_OPTIONS = [
  { value: 'digital_marketing', label: 'Digital Marketing Agency' },
  { value: 'pro_services', label: 'Marketing / Pro Services' },
  { value: 'general', label: 'General Agency' },
] as const

export function clientIndustryLabel(id: string): string {
  return CLIENT_INDUSTRY_OPTIONS.find((o) => o.value === id)?.label ?? formatIndustrySlug(id)
}

/** Agency type from Brand Kit (e.g. digital_marketing → Digital Marketing Agency). */
export function agencyIndustryLabel(id: string): string {
  const fromAgency = AGENCY_INDUSTRY_OPTIONS.find((o) => o.value === id)?.label
  if (fromAgency) return fromAgency
  return clientIndustryLabel(id)
}

/** Fallback when no catalog label exists — never show raw snake_case in UI. */
export function formatIndustrySlug(id: string): string {
  const trimmed = (id || '').trim()
  if (!trimmed) return ''
  return trimmed
    .split('_')
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1).toLowerCase())
    .join(' ')
}

/** Suggested CTA when the user picks a client industry (avoids Shop Now on dental, legal, etc.). */
export const SUGGESTED_CTA_BY_INDUSTRY: Record<string, string> = {
  healthcare: 'Book Appointment',
  fitness: 'Book Now',
  legal: 'Book Consultation',
  finance: 'Get Free Quote',
  property_management: 'Book Free Appraisal',
  real_estate: 'Book Inspection',
  hospitality: 'Book Now',
  education: 'Enroll Now',
  beauty: 'Book Appointment',
  construction: 'Get Free Quote',
  local: 'Book Now',
  pro_services: 'Book Consultation',
  automotive: 'Book Test Drive',
  food_beverage: 'Order Now',
  retail: 'Shop Now',
  dtc: 'Shop Now',
  general: 'Learn More',
}

export function suggestedCtaForIndustry(industryId: string): string {
  return SUGGESTED_CTA_BY_INDUSTRY[industryId] ?? 'Learn More'
}

/** Default video script style id (matches backend `video_script_styles.py`). */
export const VIDEO_STYLE_BY_INDUSTRY: Record<string, string> = {
  dtc: 'fast_cut',
  beauty: 'fast_cut',
  real_estate: 'before_after',
  construction: 'before_after',
  automotive: 'before_after',
  property_management: 'before_after',
  saas: 'founder',
  education: 'founder',
  digital_marketing: 'founder',
  healthcare: 'narrative',
  legal: 'narrative',
  finance: 'narrative',
  pro_services: 'narrative',
  local: 'ugc',
  fitness: 'ugc',
  food_beverage: 'ugc',
  retail: 'ugc',
  hospitality: 'ugc',
  general: 'narrative',
}

export function suggestedVideoStyleForIndustry(industryId: string): string {
  return VIDEO_STYLE_BY_INDUSTRY[industryId] ?? 'narrative'
}
