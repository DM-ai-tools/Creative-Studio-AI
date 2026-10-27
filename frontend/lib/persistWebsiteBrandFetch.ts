import { brandsApi } from '@/lib/api'
import type { Brand, BrandFacts, WebsiteBrandFetchResult } from '@/types'

export function websiteHost(url: string): string {
  try {
    const raw = url.trim()
    const u = new URL(raw.startsWith('http') ? raw : `https://${raw}`)
    return u.hostname.replace(/^www\./i, '').toLowerCase()
  } catch {
    return url.trim().toLowerCase()
  }
}

export function summarizeBrandFacts(facts: BrandFacts | null | undefined): string {
  if (!facts) return ''
  const bits: string[] = []
  if (facts.services?.length) bits.push(`Services: ${facts.services.slice(0, 3).join(', ')}`)
  if (facts.service_areas?.length) bits.push(`Areas: ${facts.service_areas.slice(0, 3).join(', ')}`)
  const rating = facts.reviews?.rating
  const count = facts.reviews?.count
  if (rating != null || count != null) {
    bits.push(`Reviews: ${rating != null ? `${rating}★` : ''}${count != null ? ` (${count})` : ''}`.trim())
  }
  if (facts.rates_or_pricing?.length) bits.push(`Rates: ${facts.rates_or_pricing.slice(0, 2).join(', ')}`)
  if (facts.offers?.length) bits.push(`Offers: ${facts.offers.slice(0, 2).join(', ')}`)
  if (facts.products?.length) bits.push(`Products: ${facts.products.slice(0, 4).join(', ')}`)
  if (facts.do_not_claim?.length) bits.push(`Won't invent: ${facts.do_not_claim.slice(0, 2).join(', ')}`)
  return bits.join(' · ')
}

function industrySlugFrom(result: WebsiteBrandFetchResult, override?: string): string {
  const raw = (override || result.industry || 'general').trim()
  return raw.replace(/\s+/g, '_').toLowerCase() || 'general'
}

export type PersistWebsiteBrandOptions = {
  brands: Brand[]
  /** Form industry / agency type — used when creating or updating */
  industryOverride?: string
}

/** Create or update Brand + Default Kit from Firecrawl fetch (same rules as Brief Composer). */
export async function persistWebsiteBrandFromFetch(
  result: WebsiteBrandFetchResult,
  url: string,
  options: PersistWebsiteBrandOptions
): Promise<{ brand: Brand; created: boolean }> {
  const host = websiteHost(result.source_url || url)
  const industrySlug = industrySlugFrom(result, options.industryOverride)

  const existing = options.brands.find((b) => {
    const vr = (b.voice_rules || {}) as Record<string, unknown>
    const saved = typeof vr.website_url === 'string' ? vr.website_url : ''
    return saved ? websiteHost(saved) === host : false
  })

  const voiceRules = {
    ...((existing?.voice_rules as Record<string, unknown>) || {}),
    website_url: result.source_url || url,
    scraped_from: 'firecrawl',
    scraped_at: new Date().toISOString(),
    brand_facts: result.brand_facts || null,
    scraped_fonts: {
      heading: result.font_heading || '',
      body: result.font_body || '',
    },
  }

  let savedBrand: Brand
  if (existing) {
    savedBrand = await brandsApi.update(existing.id, {
      name: result.brand_name || existing.name,
      primary_color: result.primary_color,
      secondary_color: result.secondary_color,
      logo_url: result.logo_url || existing.logo_url || undefined,
      voice_rules: voiceRules,
      ...(options.industryOverride?.trim() ? { industry: industrySlug } : {}),
    })
    try {
      const kit = await brandsApi.getKit(existing.id)
      await brandsApi.updateKit(existing.id, kit.id, {
        name: kit.name || 'Default Kit',
        colors: {
          ...(kit.colors || {}),
          primary: result.primary_color,
          secondary: result.secondary_color,
        },
        fonts: {
          ...(kit.fonts || {}),
          ...(result.font_heading ? { heading: result.font_heading } : {}),
          ...(result.font_body ? { body: result.font_body } : {}),
        },
        logo_variations: kit.logo_variations || {},
      })
    } catch {
      /* kit optional */
    }
  } else {
    savedBrand = await brandsApi.create({
      name: result.brand_name || host,
      industry: industrySlug,
      primary_color: result.primary_color,
      secondary_color: result.secondary_color,
      language: 'English',
      voice_rules: voiceRules,
    })
    if (result.logo_url) {
      try {
        savedBrand = await brandsApi.update(savedBrand.id, { logo_url: result.logo_url })
      } catch {
        /* logo optional */
      }
    }
    try {
      await brandsApi.createKit(savedBrand.id, {
        name: 'Default Kit',
        colors: {
          primary: result.primary_color,
          secondary: result.secondary_color,
        },
        fonts: {
          ...(result.font_heading ? { heading: result.font_heading } : {}),
          ...(result.font_body ? { body: result.font_body } : {}),
        },
      })
    } catch {
      /* kit optional */
    }
  }

  return { brand: savedBrand, created: !existing }
}
