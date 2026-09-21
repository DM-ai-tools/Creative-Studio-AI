import type { Brand, BrandKit, CompetitorCandidate, CompetitorSocialInsight, SocialStyleProfile } from '@/types'

export function socialStyleFromVoiceRules(voiceRules: unknown): SocialStyleProfile | null {
  if (!voiceRules || typeof voiceRules !== 'object') return null
  const profile = (voiceRules as Record<string, unknown>).social_style_profile
  if (!profile || typeof profile !== 'object') return null
  return profile as SocialStyleProfile
}

export function socialStyleFromBrand(brand?: Brand | null, kit?: BrandKit | null): SocialStyleProfile | null {
  if (kit?.colors && typeof kit.colors === 'object') {
    const profile = (kit.colors as Record<string, unknown>).social_style_profile
    if (profile && typeof profile === 'object') return profile as SocialStyleProfile
  }
  return socialStyleFromVoiceRules(brand?.voice_rules)
}

export function socialStyleAccountLabel(profile: SocialStyleProfile | null | undefined): string {
  if (!profile) return ''
  const plat = profile.platform
    ? profile.platform.charAt(0).toUpperCase() + profile.platform.slice(1)
    : 'Social'
  const handle = (profile.handle || '').replace(/^@/, '')
  return handle ? `${plat} · @${handle}` : plat
}

/** Extract @handle for input display — never show raw profile URL when handle is known. */
export function socialAccountHandleInput(
  profile: { handle?: string; profile_url?: string } | null | undefined
): string {
  if (!profile) return ''
  const handle = (profile.handle || '').replace(/^@/, '').trim()
  if (handle) return `@${handle}`
  const url = (profile.profile_url || '').trim()
  if (!url) return ''
  const ig = url.match(/instagram\.com\/([^/?#]+)/i)
  if (ig?.[1] && ig[1] !== 'p') return `@${ig[1]}`
  const fb = url.match(/facebook\.com\/([^/?#]+)/i)
  if (fb?.[1] && !['pages', 'profile.php', 'people'].includes(fb[1].toLowerCase())) {
    return `@${fb[1]}`
  }
  return ''
}

/** Pre-fill input from saved social profile — shows @handle like the saved account label. */
export function socialStyleInputValue(profile: SocialStyleProfile | null | undefined): string {
  return socialAccountHandleInput(profile)
}

export function competitorInsightsFromVoiceRules(voiceRules: unknown): CompetitorSocialInsight[] {
  if (!voiceRules || typeof voiceRules !== 'object') return []
  const raw = (voiceRules as Record<string, unknown>).competitor_social_insights
  if (Array.isArray(raw)) {
    return raw.filter((item) => item && typeof item === 'object') as CompetitorSocialInsight[]
  }
  if (raw && typeof raw === 'object') return [raw as CompetitorSocialInsight]
  return []
}

export function competitorInsightsFromBrand(
  brand?: Brand | null,
  kit?: BrandKit | null
): CompetitorSocialInsight[] {
  if (kit?.colors && typeof kit.colors === 'object') {
    const raw = (kit.colors as Record<string, unknown>).competitor_social_insights
    if (Array.isArray(raw)) {
      return raw.filter((item) => item && typeof item === 'object') as CompetitorSocialInsight[]
    }
  }
  return competitorInsightsFromVoiceRules(brand?.voice_rules)
}

export function competitorAccountLabel(insight: CompetitorSocialInsight | null | undefined): string {
  if (!insight) return ''
  const plat = insight.platform
    ? insight.platform.charAt(0).toUpperCase() + insight.platform.slice(1)
    : 'Social'
  const handle = (insight.handle || '').replace(/^@/, '')
  return handle ? `${plat} · @${handle}` : plat
}

export function summarizeCompetitorInsight(insight: CompetitorSocialInsight | null | undefined): string {
  if (!insight) return ''
  const bits: string[] = []
  if (insight.platform && insight.handle) {
    bits.push(competitorAccountLabel(insight))
  }
  if (insight.posting_logic?.trim()) bits.push(insight.posting_logic.trim())
  if (insight.post_count_analyzed != null) {
    bits.push(`${insight.post_count_analyzed} posts analyzed`)
  }
  return bits.join(' · ')
}

export function competitorInputValue(insight: CompetitorSocialInsight | null | undefined): string {
  return socialAccountHandleInput(insight)
}

export function buildSavedSocialAccountOptions(
  brands: Array<{ id: string; name: string; voice_rules?: unknown }>
): Array<{ value: string; label: string; brandId: string; profile: SocialStyleProfile }> {
  const out: Array<{ value: string; label: string; brandId: string; profile: SocialStyleProfile }> = []
  for (const brand of brands) {
    const profile = socialStyleFromVoiceRules(brand.voice_rules)
    if (!profile || (!profile.handle && !profile.profile_url)) continue
    const handle = (profile.handle || '').replace(/^@/, '').trim()
    if (!handle) continue
    const key = `${brand.id}::${handle}`
    out.push({
      value: key,
      brandId: brand.id,
      profile,
      label: `${brand.name} — ${socialStyleAccountLabel(profile)}`,
    })
  }
  return out.sort((a, b) => a.label.localeCompare(b.label))
}

export function buildSavedCompetitorOptions(
  insights: CompetitorSocialInsight[]
): Array<{ value: string; label: string; insight: CompetitorSocialInsight }> {
  return insights
    .map((insight) => {
      const handle = (insight.handle || '').replace(/^@/, '').trim()
      if (!handle) return null
      const platform = (insight.platform || 'social').toLowerCase()
      return {
        value: `${platform}::${handle}`,
        label: `${competitorAccountLabel(insight)} ✓ analyzed`,
        insight,
      }
    })
    .filter(Boolean) as Array<{ value: string; label: string; insight: CompetitorSocialInsight }>
}

export function competitorCandidatesFromBrand(
  brand?: Brand | null,
  kit?: BrandKit | null
): CompetitorCandidate[] {
  if (kit?.colors && typeof kit.colors === 'object') {
    const raw = (kit.colors as Record<string, unknown>).competitor_candidates
    if (Array.isArray(raw)) {
      return raw.filter((item) => item && typeof item === 'object') as CompetitorCandidate[]
    }
  }
  if (brand?.voice_rules && typeof brand.voice_rules === 'object') {
    const raw = (brand.voice_rules as Record<string, unknown>).competitor_candidates
    if (Array.isArray(raw)) {
      return raw.filter((item) => item && typeof item === 'object') as CompetitorCandidate[]
    }
  }
  return []
}

export function buildCompetitorCandidateOptions(
  candidates: CompetitorCandidate[]
): Array<{ value: string; label: string; candidate: CompetitorCandidate }> {
  return candidates
    .map((candidate) => {
      const handle = (candidate.handle || '').replace(/^@/, '').trim()
      if (!handle) return null
      const platform = (candidate.platform || 'facebook').toLowerCase()
      const name = (candidate.name || handle).trim()
      const platLabel = platform.charAt(0).toUpperCase() + platform.slice(1)
      return {
        value: `suggest::${platform}::${handle}`,
        label: `${name} · ${platLabel} · suggested`,
        candidate,
      }
    })
    .filter(Boolean) as Array<{ value: string; label: string; candidate: CompetitorCandidate }>
}

export function candidateInputValue(candidate: CompetitorCandidate | null | undefined): string {
  if (!candidate) return ''
  const url = (candidate.profile_url || '').trim()
  if (url) return url
  const handle = (candidate.handle || '').replace(/^@/, '').trim()
  const platform = (candidate.platform || 'facebook').toLowerCase()
  if (!handle) return ''
  if (platform === 'instagram') return `@${handle}`
  return `https://www.facebook.com/${handle}`
}

export function summarizeSocialStyle(profile: SocialStyleProfile | null | undefined): string {
  if (!profile) return ''
  const bits: string[] = []
  if (profile.platform && profile.handle) {
    bits.push(`${profile.platform} @${profile.handle.replace(/^@/, '')}`)
  }
  if (profile.prompt_guidance?.trim()) {
    bits.push(profile.prompt_guidance.trim())
  }
  if (profile.post_count_analyzed != null) {
    bits.push(`${profile.post_count_analyzed} posts analyzed`)
  }
  return bits.join(' · ')
}

const SOCIAL_NAMED_COLORS: Record<string, string> = {
  black: '#0A0A0A',
  dark: '#0A0A0A',
  charcoal: '#1A1A1A',
  gold: '#C9A962',
  golden: '#C9A962',
  champagne: '#D4AF37',
  bronze: '#B8860B',
  white: '#FFFFFF',
  navy: '#0F1B3D',
  blue: '#2563EB',
}

function normalizeSocialHex(value: string | undefined): string {
  const raw = (value || '').trim()
  if (/^#[0-9A-Fa-f]{6}$/.test(raw)) return raw.toUpperCase()
  const match = raw.match(/#[0-9A-Fa-f]{6}/)
  return match ? match[0].toUpperCase() : ''
}

function parseSocialColorToken(token: string): string {
  const hex = normalizeSocialHex(token)
  if (hex) return hex
  const lower = token.toLowerCase()
  for (const [name, namedHex] of Object.entries(SOCIAL_NAMED_COLORS)) {
    if (lower.includes(name)) return namedHex
  }
  return ''
}

function isDarkSocialHex(value: string): boolean {
  const hex = normalizeSocialHex(value)
  if (!hex) return false
  if (['#0A0A0A', '#000000', '#1A1A1A', '#111111', '#0F0F0F'].includes(hex)) return true
  const r = parseInt(hex.slice(1, 3), 16)
  const g = parseInt(hex.slice(3, 5), 16)
  const b = parseInt(hex.slice(5, 7), 16)
  return 0.299 * r + 0.587 * g + 0.114 * b < 70
}

function isGoldSocialColor(value: string): boolean {
  const lower = value.toLowerCase()
  return ['gold', 'champagne', 'bronze', 'gilded'].some((k) => lower.includes(k))
}

export function resolveSocialStyleColors(profile: SocialStyleProfile | null | undefined): {
  cta: string
  background: string
} {
  if (!profile) return { cta: '', background: '' }

  let cta = normalizeSocialHex(profile.effective_primary_color)
  let background = normalizeSocialHex(profile.effective_secondary_color)
  if (cta || background) return { cta, background }

  const themes = profile.visual_themes
  const paletteRaw = Array.isArray(themes)
    ? themes
    : themes && typeof themes === 'object' && Array.isArray(themes.color_palette)
      ? themes.color_palette
      : []

  const parsed = paletteRaw.map((item) => parseSocialColorToken(String(item))).filter(Boolean)
  const guidance = [
    profile.prompt_guidance || '',
    themes && typeof themes === 'object' && !Array.isArray(themes) ? themes.typography_style || '' : '',
    themes && typeof themes === 'object' && !Array.isArray(themes) ? themes.cta_style || '' : '',
    paletteRaw.join(' '),
  ]
    .join(' ')
    .toLowerCase()

  if (
    guidance.includes('black and gold') ||
    guidance.includes('black & gold') ||
    guidance.includes('gold on black') ||
    guidance.includes('black background')
  ) {
    cta = cta || '#C9A962'
    background = background || '#0A0A0A'
  }

  for (const color of parsed) {
    if (isGoldSocialColor(color) || ['#C9A962', '#D4AF37', '#B8860B'].includes(color)) {
      cta = cta || color
    } else if (isDarkSocialHex(color)) {
      background = background || color
    } else if (color !== '#FFFFFF' && !cta) {
      cta = color
    } else if (!background) {
      background = color
    }
  }

  return { cta, background }
}

export function socialStyleAestheticLabel(profile: SocialStyleProfile | null | undefined): string {
  if (!profile) return ''
  const mode = (profile.aesthetic_mode || '').toLowerCase()
  if (mode === 'gold_on_dark') return 'Gold on dark'
  if (mode === 'gold_on_white') return 'Gold on white'
  const colors = resolveSocialStyleColors(profile)
  if (colors.cta && colors.background === '#0A0A0A') return 'Gold on dark'
  if (colors.cta && colors.background === '#FFFFFF') return 'Gold on white'
  if (colors.cta && colors.background) return 'Gold accent'
  return ''
}

export function hasSocialStyleSummary(profile: SocialStyleProfile | null | undefined): boolean {
  if (!profile) return false
  const colors = resolveSocialStyleColors(profile)
  return Boolean(summarizeSocialStyle(profile) || colors.cta || colors.background)
}

/** Keep social-style keys when saving Brand Kit colours. */
export function preserveSocialStyleKitColors(colors: Record<string, unknown> | undefined): Record<string, unknown> {
  if (!colors || typeof colors !== 'object') return {}
  const kept: Record<string, unknown> = {}
  for (const key of [
    'social_style_profile',
    'social_style_fetched_at',
    'social_primary',
    'social_secondary',
    'competitor_social_insights',
    'competitor_social_fetched_at',
  ] as const) {
    if (colors[key] != null) kept[key] = colors[key]
  }
  return kept
}
