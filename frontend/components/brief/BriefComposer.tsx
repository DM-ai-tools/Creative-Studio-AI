'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import React, { useEffect, useMemo, useState, useRef } from 'react'
import { useForm, type FieldErrors } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import Select from '@/components/ui/Select'
import TextArea from '@/components/ui/TextArea'
import { ChipToggle, ChipToggleGroup } from '@/components/ui/ChipToggle'
import BriefSection from '@/components/brief/BriefSection'
import ReferenceImagesPanel from '@/components/brief/ReferenceImagesPanel'
import AdAngleSelector from '@/components/brief/AdAngleSelector'
import ImageVariantSlotsPanel from '@/components/brief/ImageVariantSlotsPanel'
import ModelSelectorBlock from '@/components/brief/ModelSelectorBlock'
import StrategyPreviewPanel from '@/components/brief/StrategyPreviewPanel'
import HeyGenProductionPipeline from '@/components/brief/HeyGenProductionPipeline'
import CreativeStudioTab from '@/components/brief/CreativeStudioTab'
import HeroAiImageTab from '@/components/brief/HeroAiImageTab'
import {
  emptyImageVariantSlot,
  isCarouselSlot,
  isLastCarouselCard,
  isIncompleteOnImageLine,
  chunkSlotIndicesForGeneration,
  relatedOnImageLines,
  resizeImageVariantSlots,
  normalizeProductFocus,
  type ImageVariantSlot,
  type ProductFocusId,
} from '@/lib/imageUseCases'
import { IMAGE_VISUAL_STYLE_OPTIONS, type ImageVisualStyleId } from '@/lib/imageVisualStyles'
import { defaultHeyGenSettings } from '@/components/brief/HeyGenVideoSettingsCard'
import { findVespriAvatar, HEYGEN_VESPRI_AVATAR_ID } from '@/lib/heygenAvatars'
import { heygenSettingsForApi, type HeyGenVideoSettings } from '@/lib/heygenOptions'
import {
  VIDEO_DURATION_OPTIONS,
  durationOptionsForVideoModel,
  isSeedanceVideoModel,
  SEEDANCE_MAX_DURATION_SECONDS,
  type BriefGenerationSettings,
} from '@/components/brief/BriefGenerationPanel'
import { useApi } from '@/hooks/useApi'
import { useActiveBrand } from '@/hooks/useActiveBrand'
import { API_CACHE_TTL, clearApiCache, clearBriefListCaches, patchApiCache } from '@/lib/apiCache'
import { brandsApi, briefsApi, generationApi, assetsApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import {
  aspectHintFromFormats,
  isLandscapeVideoFormat,
  isPortraitVideoFormat,
  isLandscapePlacement,
  isPortraitPlacement,
  isVideoFormat,
  mapCreativeFormatOptions,
  mapPlacementOptions,
} from '@/lib/creativeFormats'
import { buildModelSelectGroups } from '@/lib/modelCatalog'
import { buildBriefExportPayload, downloadBriefExcel } from '@/lib/exportBriefExcel'
import { assignAnglesToVariants } from '@/lib/adAngles'
import type { AdFormat, Brand, BrandFacts, BrandKit, BriefReferenceImage, CatalogOption, CompetitorCandidate, CompetitorSocialInsight, PerformanceStatsContext, SocialStyleProfile, StrategyParseResult, StrategyPreviewResult, WebsiteBrandFetchResult } from '@/types'
import {
  buildCompetitorCandidateOptions,
  buildSavedCompetitorOptions,
  buildSavedSocialAccountOptions,
  candidateInputValue,
  competitorAccountLabel,
  competitorCandidatesFromBrand,
  competitorInputValue,
  competitorInsightsFromBrand,
  socialStyleAccountLabel,
  socialStyleFromBrand,
  socialStyleInputValue,
  summarizeCompetitorInsight,
} from '@/lib/socialStyle'

const schema = z
  .object({
    brand_id: z.string().optional(),
    title: z.string().min(2, 'Industry required'),
    niche: z.string().optional(),
    brand_source: z.enum(['brand', 'website']),
    website_url: z.string().optional(),
    objective_id: z.string().min(1, 'Select an objective'),
    target_variant_count: z.coerce.number().int().min(1).max(100),
    offer: z.string().optional(),
    product_name: z.string().optional(),
    cta: z.string().optional(),
    audience_type: z.string().optional(),
    geography: z.string().optional(),
    age_range: z.string().optional(),
    languages: z.string().optional(),
    placements: z.array(z.string()).optional(),
    formats: z.array(z.string()).min(1, 'Select at least one creative format'),
    hook_frameworks: z.array(z.string()).optional(),
    notes: z.string().max(2000).optional(),
    ad_copy_tone: z.string().optional(),
  })
  .superRefine((data, ctx) => {
    if (data.brand_source === 'brand' && !(data.brand_id || '').trim()) {
      ctx.addIssue({ code: 'custom', path: ['brand_id'], message: 'Select a brand' })
    }
    if (data.brand_source === 'website' && !(data.website_url || '').trim()) {
      ctx.addIssue({ code: 'custom', path: ['website_url'], message: 'Enter a website URL' })
    }
  })

type FormData = z.infer<typeof schema>

function campaignLabel(industry: string, niche?: string): string {
  const i = industry.trim()
  const n = (niche || '').trim()
  return n ? `${i} — ${n}` : i
}

function brandFactsFromVoiceRules(voiceRules: unknown): BrandFacts | null {
  if (!voiceRules || typeof voiceRules !== 'object') return null
  const facts = (voiceRules as Record<string, unknown>).brand_facts
  if (!facts || typeof facts !== 'object') return null
  return facts as BrandFacts
}

function socialStyleFromVoiceRules(voiceRules: unknown): SocialStyleProfile | null {
  if (!voiceRules || typeof voiceRules !== 'object') return null
  const profile = (voiceRules as Record<string, unknown>).social_style_profile
  if (!profile || typeof profile !== 'object') return null
  return profile as SocialStyleProfile
}

function summarizeSocialStyle(profile: SocialStyleProfile | null | undefined): string {
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

function resolveSocialStyleColors(profile: SocialStyleProfile | null | undefined): {
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

function socialStyleAestheticLabel(profile: SocialStyleProfile | null | undefined): string {
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

function hasSocialStyleSummary(profile: SocialStyleProfile | null | undefined): boolean {
  if (!profile) return false
  const colors = resolveSocialStyleColors(profile)
  return Boolean(summarizeSocialStyle(profile) || colors.cta || colors.background)
}

function summarizeBrandFacts(facts: BrandFacts | null | undefined): string {
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

function websiteHost(url: string): string {
  try {
    const raw = url.trim()
    const u = new URL(raw.startsWith('http') ? raw : `https://${raw}`)
    return u.hostname.replace(/^www\./i, '').toLowerCase()
  } catch {
    return url.trim().toLowerCase()
  }
}

// Australian geographic targeting options — states first, then major cities grouped by state.
const AU_GEO_GROUPS = [
  {
    label: 'Whole State / Territory',
    options: [
      { value: 'NSW', label: 'New South Wales (NSW)' },
      { value: 'VIC', label: 'Victoria (VIC)' },
      { value: 'QLD', label: 'Queensland (QLD)' },
      { value: 'WA', label: 'Western Australia (WA)' },
      { value: 'SA', label: 'South Australia (SA)' },
      { value: 'TAS', label: 'Tasmania (TAS)' },
      { value: 'ACT', label: 'Australian Capital Territory (ACT)' },
      { value: 'NT', label: 'Northern Territory (NT)' },
    ],
  },
  {
    label: 'NSW — Cities & Regions',
    options: [
      { value: 'Sydney NSW', label: 'Sydney' },
      { value: 'Western Sydney NSW', label: 'Western Sydney' },
      { value: 'North Shore Sydney NSW', label: 'North Shore' },
      { value: 'Inner West Sydney NSW', label: 'Inner West' },
      { value: 'Eastern Suburbs Sydney NSW', label: 'Eastern Suburbs' },
      { value: 'South West Sydney NSW', label: 'South West Sydney' },
      { value: 'Newcastle NSW', label: 'Newcastle' },
      { value: 'Wollongong NSW', label: 'Wollongong' },
      { value: 'Central Coast NSW', label: 'Central Coast' },
      { value: 'Hunter Valley NSW', label: 'Hunter Valley' },
    ],
  },
  {
    label: 'VIC — Cities & Regions',
    options: [
      { value: 'Melbourne VIC', label: 'Melbourne' },
      { value: 'Inner Melbourne VIC', label: 'Inner Melbourne' },
      { value: 'South East Melbourne VIC', label: 'South East Melbourne' },
      { value: 'Western Melbourne VIC', label: 'Western Melbourne' },
      { value: 'Mornington Peninsula VIC', label: 'Mornington Peninsula' },
      { value: 'Geelong VIC', label: 'Geelong' },
      { value: 'Ballarat VIC', label: 'Ballarat' },
      { value: 'Bendigo VIC', label: 'Bendigo' },
    ],
  },
  {
    label: 'QLD — Cities & Regions',
    options: [
      { value: 'Brisbane QLD', label: 'Brisbane' },
      { value: 'Gold Coast QLD', label: 'Gold Coast' },
      { value: 'Sunshine Coast QLD', label: 'Sunshine Coast' },
      { value: 'Cairns QLD', label: 'Cairns' },
      { value: 'Townsville QLD', label: 'Townsville' },
      { value: 'Toowoomba QLD', label: 'Toowoomba' },
    ],
  },
  {
    label: 'WA — Cities & Regions',
    options: [
      { value: 'Perth WA', label: 'Perth' },
      { value: 'South Perth WA', label: 'South Perth' },
      { value: 'Northern Suburbs Perth WA', label: 'Northern Suburbs (Perth)' },
      { value: 'Southern Suburbs Perth WA', label: 'Southern Suburbs (Perth)' },
      { value: 'Fremantle WA', label: 'Fremantle' },
      { value: 'Mandurah WA', label: 'Mandurah' },
    ],
  },
  {
    label: 'SA — Cities & Regions',
    options: [
      { value: 'Adelaide SA', label: 'Adelaide' },
      { value: 'Northern Adelaide SA', label: 'Northern Adelaide' },
      { value: 'Southern Adelaide SA', label: 'Southern Adelaide' },
    ],
  },
  {
    label: 'TAS — Cities & Regions',
    options: [
      { value: 'Hobart TAS', label: 'Hobart' },
      { value: 'Launceston TAS', label: 'Launceston' },
    ],
  },
  {
    label: 'ACT & NT',
    options: [
      { value: 'Canberra ACT', label: 'Canberra' },
      { value: 'Darwin NT', label: 'Darwin' },
    ],
  },
]

interface BriefComposerProps {
  defaultBrandId?: string
}

const FALLBACK_OBJECTIVES: CatalogOption[] = [
  { id: 'conversions', label: 'Conversions (Purchase)' },
  { id: 'add_to_cart', label: 'Add to Cart' },
  { id: 'lead_generation', label: 'Lead Generation' },
  { id: 'traffic', label: 'Traffic' },
  { id: 'awareness', label: 'Awareness' },
]

const FALLBACK_HOOK_FRAMEWORKS: CatalogOption[] = [
  { id: 'problem_agitate_solve', label: 'Problem-Agitate-Solve' },
  { id: 'ugc_style', label: 'UGC-Style' },
  { id: 'pattern_interrupt', label: 'Pattern Interrupt' },
  { id: 'social_proof', label: 'Social Proof' },
  { id: 'founder_led', label: 'Founder-Led' },
  { id: 'before_after', label: 'Before / After' },
  { id: 'testimonial', label: 'Testimonial / Review' },
  { id: 'offer_urgency', label: 'Offer / Urgency' },
  { id: 'educational', label: 'Educational / How-to' },
  { id: 'myth_busting', label: 'Myth Busting' },
  { id: 'curiosity_hook', label: 'Curiosity Hook' },
  { id: 'pain_led', label: 'Pain-Led Hook' },
  { id: 'fear_loss_aversion', label: 'Fear / Loss Aversion' },
  { id: 'fomo_scarcity', label: 'FOMO / Scarcity' },
  { id: 'contrarian', label: 'Contrarian / Unpopular Opinion' },
  { id: 'product_hero', label: 'Product Hero / Catalog' },
]

function optionLabel(options: CatalogOption[], id: string): string {
  return options.find((option) => option.id === id)?.label ?? id
}

function labelsForIds(options: CatalogOption[], ids: string[]): string {
  if (!ids.length) return '—'
  return ids.map((id) => optionLabel(options, id)).join(', ')
}

function PillRadio({
  options,
  value,
  onChange,
  disabled,
}: {
  options: CatalogOption[]
  value: string
  onChange(id: string): void
  disabled?: boolean
}) {
  return (
    <div className="flex flex-wrap gap-2">
      {options.map((opt) => (
        <ChipToggle
          key={opt.id}
          label={opt.label}
          selected={value === opt.id}
          disabled={disabled}
          onToggle={() => onChange(opt.id)}
        />
      ))}
    </div>
  )
}

export default function BriefComposer(_props: BriefComposerProps) {
  const router = useRouter()
  const { activeBrandId, setActiveBrandId } = useActiveBrand()
  const { data: brands, refetch: refetchBrands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands',
    ttlMs: API_CACHE_TTL.brands,
  })
  const { data: catalog } = useApi(() => generationApi.getCatalog(false), [], {
    cacheKey: 'generation/catalog-v7',
    ttlMs: API_CACHE_TTL.catalog,
  })

  const [mediaType, setMediaType] = useState<'image' | 'video' | 'creative_studio' | 'hero_ai_image'>('image')
  const [imageVariantSlots, setImageVariantSlots] = useState<ImageVariantSlot[]>([
    emptyImageVariantSlot(),
    emptyImageVariantSlot(),
  ])
  const [generatingSlotIndex, setGeneratingSlotIndex] = useState<number | null>(null)
  const [generatingAllSlots, setGeneratingAllSlots] = useState(false)
  const [imageIcpText, setImageIcpText] = useState<string | null>(null)
  const [imageCampaignOffer, setImageCampaignOffer] = useState('')
  const [imageCampaignHook, setImageCampaignHook] = useState('')
  const [imageCampaignHeadline, setImageCampaignHeadline] = useState('')
  const [imageProductFocus, setImageProductFocus] = useState<ProductFocusId | ''>('')
  const [imageVisualStyle, setImageVisualStyle] = useState<ImageVisualStyleId>('')
  const [suggestingAngles, setSuggestingAngles] = useState(false)
  const [angleSuggestionReason, setAngleSuggestionReason] = useState<string | null>(null)
  const [websiteBrand, setWebsiteBrand] = useState<WebsiteBrandFetchResult | null>(null)
  const [fetchingWebsiteBrand, setFetchingWebsiteBrand] = useState(false)
  const [brandSearch, setBrandSearch] = useState('')
  const [socialHandleUrl, setSocialHandleUrl] = useState('')
  const [briefSocialStyle, setBriefSocialStyle] = useState<SocialStyleProfile | null>(null)
  const [fetchingSocialStyle, setFetchingSocialStyle] = useState(false)
  const [competitorHandleUrl, setCompetitorHandleUrl] = useState('')
  const [useCompetitorInsights, setUseCompetitorInsights] = useState(false)
  const [fetchingCompetitor, setFetchingCompetitor] = useState(false)
  const [discoveringCompetitors, setDiscoveringCompetitors] = useState(false)
  const [selectedBrandKit, setSelectedBrandKit] = useState<BrandKit | null>(null)
  const [selectedSocialAccountKey, setSelectedSocialAccountKey] = useState('')
  const [socialAccountModeNew, setSocialAccountModeNew] = useState(false)
  const [selectedCompetitorKey, setSelectedCompetitorKey] = useState('')
  const [competitorModeNew, setCompetitorModeNew] = useState(true)
  const [strategyParsed, setStrategyParsed] = useState<StrategyParseResult | null>(null)
  const [parsingStrategy, setParsingStrategy] = useState(false)
  const [strategyFileName, setStrategyFileName] = useState('')
  const [strategyFilePending, setStrategyFilePending] = useState<File | null>(null)
  const [briefReferenceImages, setBriefReferenceImages] = useState<BriefReferenceImage[]>([])
  const [exactProductReference, setExactProductReference] = useState(false)
  const [imageRatio, setImageRatio] = useState<string>('1:1')
  const [imageRatioCustom, setImageRatioCustom] = useState<string>('')
  const [genSettings, setGenSettings] = useState<BriefGenerationSettings>({
    copyModel: 'claude',
    imageModel: '',
    videoModel: 'heygen-video-agent',
    videoDurationSeconds: 30,
    heygenAvatarId: '',
    heygenVoiceId: '',
    higgsfieldVoicePreset: 'serene_female',
    promptLlmModel: '',
  })
  const [heygenSettings, setHeygenSettings] = useState<HeyGenVideoSettings>(defaultHeyGenSettings())
  const [approvedAvatarScript, setApprovedAvatarScript] = useState<string | null>(null)
  const createVideoButtonRef = useRef<HTMLDivElement>(null)
  /** Prevents double Create brief clicks while soft-nav is wedged / in-flight. */
  const creatingBriefRef = useRef(false)
  const [generatingNotes, setGeneratingNotes] = useState(false)
  const [scriptBuildMode, setScriptBuildMode] = useState<'manual' | 'pdf' | 'custom' | 'website'>('manual')
  const [pdfFile, setPdfFile] = useState<File | null>(null)
  const [customPrompt, setCustomPrompt] = useState('')
  const [referenceImageFile, setReferenceImageFile] = useState<File | null>(null)
  const [referenceImagePreview, setReferenceImagePreview] = useState<string | null>(null)
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [strategyPreview, setStrategyPreview] = useState<StrategyPreviewResult | null>(null)
  const [avatarExportSnapshot, setAvatarExportSnapshot] = useState<{
    icpText: string | null
    generatedFullScript: string | null
    spokenScript: string | null
    statsImageUrl: string | null
    statsImageUrls: string[]
    performanceStats: PerformanceStatsContext | null
    performanceStatsPerImage: PerformanceStatsContext[]
  }>({
    icpText: null,
    generatedFullScript: null,
    spokenScript: null,
    statsImageUrl: null,
    statsImageUrls: [],
    performanceStats: null,
    performanceStatsPerImage: [],
  })

  const {
    register,
    handleSubmit,
    watch,
    setValue,
    formState: { errors, isSubmitting },
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      // A new brief must start without inheriting the previously active brand.
      // The user must search for and select a brand explicitly.
      brand_id: '',
      title: '',
      niche: '',
      brand_source: 'brand',
      website_url: '',
      target_variant_count: 2,
      placements: [],
      formats: [],
      hook_frameworks: [],
      notes: '',
      cta: '',
      ad_copy_tone: '',
      objective_id: '',
    },
  })

  const watchedBrandId = watch('brand_id')

  useEffect(() => {
    if (!catalog) return
    const objectives = catalog.objectives?.length ? catalog.objectives : FALLBACK_OBJECTIVES
    if (objectives[0] && !watch('objective_id')) {
      setValue('objective_id', objectives[0].id)
    }
    setGenSettings((prev) => ({
      ...prev,
      copyModel: catalog.copy_models[0]?.id ?? prev.copyModel,
      videoModel:
        catalog.video_models.find((m) => m.id === 'heygen-video-agent')?.id ??
        catalog.video_models[0]?.id ??
        prev.videoModel,
      heygenAvatarId:
        prev.heygenAvatarId ||
        findVespriAvatar(catalog.heygen_avatar_featured ?? catalog.heygen_avatar_options ?? [])?.id ||
        HEYGEN_VESPRI_AVATAR_ID,
      heygenVoiceId:
        prev.heygenVoiceId ||
        catalog.heygen_voice_options?.find((v) => v.label.toLowerCase().includes('female'))?.id ||
        catalog.heygen_voice_options?.[0]?.id ||
        '',
      higgsfieldVoicePreset:
        prev.higgsfieldVoicePreset ||
        catalog.higgsfield_voice_options?.[0]?.id ||
        'serene_female',
      promptLlmModel:
        prev.promptLlmModel ||
        catalog.prompt_llm_models?.find((m) => m.label.includes('(default)'))?.id ||
        catalog.prompt_llm_models?.[0]?.id ||
        '',
    }))
  }, [catalog, setValue, watch])

  // Keep sidebar ACTIVE BRAND in sync with the brand selected on this brief form.
  useEffect(() => {
    const id = (watchedBrandId || '').trim()
    if (id && id !== activeBrandId) setActiveBrandId(id)
  }, [watchedBrandId, activeBrandId, setActiveBrandId])

  const selectedPlacements = watch('placements')
  const selectedFormats = watch('formats')
  const selectedFrameworks = watch('hook_frameworks')
  const targetVariantCount = watch('target_variant_count')
  const objectiveId = watch('objective_id')
  const brandSource = watch('brand_source')
  const websiteUrlField = watch('website_url')

  useEffect(() => {
    if (mediaType !== 'image' && mediaType !== 'creative_studio') return
    if (mediaType === 'creative_studio') return
    setImageVariantSlots((prev) =>
      resizeImageVariantSlots(prev, Number(targetVariantCount) || 1)
    )
  }, [targetVariantCount, mediaType])

  const objectiveOptions = useMemo(() => {
    const source =
      catalog?.objectives?.length ? catalog.objectives : FALLBACK_OBJECTIVES
    return source.map((o) => ({ value: o.id, label: o.label }))
  }, [catalog?.objectives])

  const hookFrameworkOptions = useMemo(() => {
    const source =
      catalog?.hook_frameworks?.length ? catalog.hook_frameworks : FALLBACK_HOOK_FRAMEWORKS
    return source
  }, [catalog?.hook_frameworks])

  const carouselSlotStructureKey = useMemo(
    () =>
      imageVariantSlots
        .map(
          (s) =>
            `${s.format ?? ''}|${s.carousel_group ?? ''}|${s.carousel_index ?? ''}|${s.carousel_total ?? ''}`
        )
        .join(';'),
    [imageVariantSlots]
  )

  const variantAngleAssignments = useMemo(
    () =>
      assignAnglesToVariants(
        selectedFrameworks ?? [],
        Number(targetVariantCount) || 1,
        objectiveId,
        imageVariantSlots,
        imageProductFocus === 'product_only' ? 'product_only' : undefined
      ),
    [selectedFrameworks, targetVariantCount, objectiveId, carouselSlotStructureKey, imageVariantSlots.length, imageProductFocus]
  )

  useEffect(() => {
    if (imageProductFocus !== 'product_only') return
    if ((selectedFrameworks?.length ?? 0) > 0) {
      setValue('hook_frameworks', [])
    }
  }, [imageProductFocus, selectedFrameworks, setValue])

  const brandOptions = (brands ?? []).map((brand) => ({ value: brand.id, label: brand.name }))
  const hasBrands = brandOptions.length > 0
  const selectedBrand = (brands ?? []).find((brand) => brand.id === watch('brand_id'))
  const currentReferenceContext = {
    brand_id: (watch('brand_id') || '').trim(),
    industry: (watch('title') || '').trim(),
    niche: (watch('niche') || '').trim(),
    product_name: (watch('product_name') || '').trim(),
  }

  // A URL-fetched product is a one-use-case reference. Do not let it leak
  // into a later niche, product, industry, or brand context in this brief.
  useEffect(() => {
    setBriefReferenceImages((previous) => {
      const next = previous.filter((ref) => {
        // Legacy URL references have no context metadata, so they are unsafe
        // to carry into another use case and are removed from active refs.
        if (ref.is_product_reference && !ref.product_reference_context) return false
        if (!ref.is_product_reference || !ref.product_reference_context) return true
        const saved = ref.product_reference_context
        return (
          (saved.brand_id || '') === currentReferenceContext.brand_id &&
          (saved.industry || '') === currentReferenceContext.industry &&
          (saved.niche || '') === currentReferenceContext.niche &&
          (saved.product_name || '') === currentReferenceContext.product_name
        )
      })
      return next.length === previous.length ? previous : next
    })
  }, [
    currentReferenceContext.brand_id,
    currentReferenceContext.industry,
    currentReferenceContext.niche,
    currentReferenceContext.product_name,
  ])

  const matchingBrands = useMemo(() => {
    const query = brandSearch.trim().toLowerCase()
    if (!query) return []
    return (brands ?? []).filter((brand) => brand.name.toLowerCase().includes(query))
  }, [brandSearch, brands])

  useEffect(() => {
    if (selectedBrand) setBrandSearch(selectedBrand.name)
  }, [selectedBrand?.id, selectedBrand?.name])

  const resolvedBrandFacts: BrandFacts | null = useMemo(() => {
    if (websiteBrand?.brand_facts) return websiteBrand.brand_facts
    return brandFactsFromVoiceRules(selectedBrand?.voice_rules)
  }, [websiteBrand, selectedBrand])

  const brandSavedSocialStyle: SocialStyleProfile | null = useMemo(() => {
    return socialStyleFromBrand(selectedBrand, selectedBrandKit)
  }, [selectedBrand, selectedBrandKit])

  const brandSavedCompetitors: CompetitorSocialInsight[] = useMemo(() => {
    return competitorInsightsFromBrand(selectedBrand, selectedBrandKit)
  }, [selectedBrand, selectedBrandKit])

  const brandSavedCompetitorCandidates: CompetitorCandidate[] = useMemo(() => {
    return competitorCandidatesFromBrand(selectedBrand, selectedBrandKit)
  }, [selectedBrand, selectedBrandKit])

  const savedSocialAccountOptions = useMemo(() => {
    const base = buildSavedSocialAccountOptions(brands ?? [])
    const saved = socialStyleFromBrand(selectedBrand, selectedBrandKit)
    const brandId = (selectedBrand?.id || '').trim()
    const handle = (saved?.handle || '').replace(/^@/, '').trim()
    if (brandId && handle && saved) {
      const key = `${brandId}::${handle}`
      if (!base.some((o) => o.value === key)) {
        base.push({
          value: key,
          brandId,
          profile: saved,
          label: `${selectedBrand?.name ?? 'Brand'} — ${socialStyleAccountLabel(saved)}`,
        })
        base.sort((a, b) => a.label.localeCompare(b.label))
      }
    }
    return base
  }, [brands, selectedBrand, selectedBrandKit])

  const savedCompetitorOptions = useMemo(
    () => buildSavedCompetitorOptions(brandSavedCompetitors),
    [brandSavedCompetitors]
  )

  const competitorCandidateOptions = useMemo(() => {
    const analyzedKeys = new Set(
      brandSavedCompetitors.map(
        (i) =>
          `${(i.platform || 'social').toLowerCase()}::${(i.handle || '').replace(/^@/, '').trim()}`
      )
    )
    const filtered = brandSavedCompetitorCandidates.filter((c) => {
      const key = `${(c.platform || 'facebook').toLowerCase()}::${(c.handle || '').replace(/^@/, '').trim()}`
      return key !== '::' && !analyzedKeys.has(key)
    })
    return buildCompetitorCandidateOptions(filtered)
  }, [brandSavedCompetitorCandidates, brandSavedCompetitors])

  const allCompetitorDropdownOptions = useMemo(
    () => [
      ...competitorCandidateOptions.map((o) => ({ value: o.value, label: o.label })),
      ...savedCompetitorOptions.map((o) => ({ value: o.value, label: o.label })),
      { value: '__new__', label: '+ Analyze new competitor manually…' },
    ],
    [competitorCandidateOptions, savedCompetitorOptions]
  )

  const selectedSavedSocialAccount = useMemo(
    () => savedSocialAccountOptions.find((o) => o.value === selectedSocialAccountKey) ?? null,
    [savedSocialAccountOptions, selectedSocialAccountKey]
  )

  const selectedSavedCompetitor = useMemo(
    () => savedCompetitorOptions.find((o) => o.value === selectedCompetitorKey) ?? null,
    [savedCompetitorOptions, selectedCompetitorKey]
  )

  const selectedCompetitorCandidate = useMemo(
    () => competitorCandidateOptions.find((o) => o.value === selectedCompetitorKey) ?? null,
    [competitorCandidateOptions, selectedCompetitorKey]
  )

  const canDiscoverCompetitors = Boolean(
    (watch('brand_id') || selectedBrand?.id || '').trim() &&
      (watch('geography') || '').trim().length >= 2 &&
      (socialHandleUrl.trim() || brandSavedSocialStyle?.handle || brandSavedSocialStyle?.profile_url)
  )

  const activeSocialStyle: SocialStyleProfile | null = briefSocialStyle ?? brandSavedSocialStyle

  const briefSocialStyleColors = useMemo(
    () => resolveSocialStyleColors(activeSocialStyle),
    [activeSocialStyle]
  )

  // Load Brand Kit (canonical store for social + competitor data) when brand changes.
  useEffect(() => {
    const brandId = (watchedBrandId || selectedBrand?.id || '').trim()
    if (!brandId) {
      setSelectedBrandKit(null)
      return
    }
    let cancelled = false
    void brandsApi
      .getKit(brandId)
      .then((kit) => {
        if (!cancelled) setSelectedBrandKit(kit)
      })
      .catch(() => {
        if (!cancelled) setSelectedBrandKit(null)
      })
    return () => {
      cancelled = true
    }
  }, [watchedBrandId, selectedBrand?.id])

  // Brand switch: sync dropdown + handle from saved Brand Kit data.
  useEffect(() => {
    const saved = socialStyleFromBrand(selectedBrand, selectedBrandKit)
    const handle = (saved?.handle || '').replace(/^@/, '').trim()
    const brandId = (selectedBrand?.id || '').trim()
    if (brandId && handle) {
      const key = `${brandId}::${handle}`
      setSelectedSocialAccountKey(key)
      setSocialAccountModeNew(false)
      setSocialHandleUrl(socialStyleInputValue(saved))
    } else if (savedSocialAccountOptions.length > 0) {
      setSelectedSocialAccountKey(savedSocialAccountOptions[0].value)
      setSocialAccountModeNew(false)
      setSocialHandleUrl(socialStyleInputValue(savedSocialAccountOptions[0].profile))
    } else {
      setSelectedSocialAccountKey('')
      setSocialAccountModeNew(true)
      setSocialHandleUrl('')
    }
    setBriefSocialStyle(null)

    const competitors = competitorInsightsFromBrand(selectedBrand, selectedBrandKit)
    const candidates = competitorCandidatesFromBrand(selectedBrand, selectedBrandKit)
    if (competitors.length > 0) {
      const first = buildSavedCompetitorOptions(competitors)[0]
      setSelectedCompetitorKey(first?.value ?? '')
      setCompetitorModeNew(false)
      setUseCompetitorInsights(true)
    } else if (candidates.length > 0) {
      const first = buildCompetitorCandidateOptions(candidates)[0]
      setSelectedCompetitorKey(first?.value ?? '')
      setCompetitorModeNew(false)
      setCompetitorHandleUrl(candidateInputValue(first?.candidate))
      setUseCompetitorInsights(false)
    } else {
      setSelectedCompetitorKey('')
      setCompetitorModeNew(true)
      setUseCompetitorInsights(false)
    }
    setCompetitorHandleUrl('')
  }, [watchedBrandId, selectedBrand, selectedBrandKit, savedSocialAccountOptions.length])

  const resolvedBrandVisuals = useMemo(() => {
    const voiceRules = (selectedBrand?.voice_rules || {}) as Record<string, unknown>
    const scrapedFonts = voiceRules.scraped_fonts as
      | { heading?: string; body?: string }
      | undefined
    return {
      primary_color: selectedBrand?.primary_color ?? websiteBrand?.primary_color ?? '',
      secondary_color: selectedBrand?.secondary_color ?? websiteBrand?.secondary_color ?? '',
      font_heading:
        websiteBrand?.font_heading ??
        scrapedFonts?.heading ??
        '',
      font_body:
        websiteBrand?.font_body ??
        scrapedFonts?.body ??
        '',
    }
  }, [selectedBrand, websiteBrand])

  const handleSuggestAdAngles = async (silent = false) => {
    const campaignName = campaignLabel(watch('title') ?? '', watch('niche'))
    if (campaignName.length < 2) {
      if (!silent) toast.error('Enter an industry first.')
      return
    }
    setSuggestingAngles(true)
    try {
      const result = await generationApi.suggestAdAngles({
        campaign_name: campaignName,
        brand_name: selectedBrand?.name ?? websiteBrand?.brand_name ?? '',
        industry: (watch('title') ?? '').trim(),
        niche: (watch('niche') ?? '').trim(),
        objective_id: objectiveId ?? '',
        variant_count: Number(targetVariantCount) || 2,
      })
      setValue('hook_frameworks', result.suggested_angles)
      setAngleSuggestionReason(result.reasoning)
      if (result.icp_text?.trim()) setImageIcpText(result.icp_text.trim())
      if (!silent) {
        if (result.source === 'ai') {
          toast.success('Ad angles suggested by AI from your industry & ICP')
        } else {
          toast.success('Ad angles suggested from campaign objective (rule-based)')
        }
      }
    } catch {
      if (!silent) toast.error('Could not suggest angles — check OPENROUTER_API_KEY')
    } finally {
      setSuggestingAngles(false)
    }
  }

  const handleFetchWebsiteBrand = async () => {
    const url = (websiteUrlField ?? '').trim()
    if (url.length < 4) {
      toast.error('Enter a website URL first')
      return
    }
    setFetchingWebsiteBrand(true)
    try {
      const result = await generationApi.fetchBrandFromUrl({ url })
      setWebsiteBrand(result)

      const host = websiteHost(result.source_url || url)
      const industrySlug =
        (watch('title') || result.industry || 'general')
          .trim()
          .replace(/\s+/g, '_')
          .toLowerCase() || 'general'

      const existing = (brands ?? []).find((b) => {
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

      let savedBrand
      if (existing) {
        savedBrand = await brandsApi.update(existing.id, {
          name: result.brand_name || existing.name,
          primary_color: result.primary_color,
          secondary_color: result.secondary_color,
          logo_url: result.logo_url || existing.logo_url || undefined,
          voice_rules: voiceRules,
          ...(watch('title')?.trim() ? { industry: industrySlug } : {}),
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
        toast.success(`Updated Brand Kit: ${savedBrand.name}`)
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
        toast.success(`Saved to Brand Kit: ${savedBrand.name}`)
      }

      patchApiCache<Brand[]>('brands', (current) => {
        const prior = current ?? brands ?? []
        const idx = prior.findIndex((b) => b.id === savedBrand.id)
        if (idx >= 0) {
          const next = [...prior]
          next[idx] = { ...prior[idx], ...savedBrand }
          return next
        }
        return [...prior, savedBrand]
      })
      await refetchBrands({ background: true })

      setActiveBrandId(savedBrand.id)
      setValue('brand_id', savedBrand.id, { shouldValidate: true })
      setValue('brand_source', 'brand', { shouldValidate: true })
      setValue('website_url', result.source_url || url)
      setWebsiteBrand(null)

      // Business fill: prefer scraped niche / service location when fields are empty.
      if (!(watch('niche') || '').trim() && result.niche) {
        setValue('niche', result.niche, { shouldValidate: true })
      }
      if (!(watch('geography') || '').trim() && result.brand_facts) {
        const areas = result.brand_facts.service_areas || result.brand_facts.locations || []
        if (areas.length) {
          setValue('geography', areas.slice(0, 2).join(', '), { shouldValidate: true })
        }
      }
      if (!(watch('offer') || '').trim() && result.brand_facts?.offers?.length) {
        setValue('offer', result.brand_facts.offers.slice(0, 2).join(' · '), { shouldValidate: true })
      }

      const factsSummary = summarizeBrandFacts(result.brand_facts)
      if (factsSummary) {
        toast.success(`Brand facts ready — ${factsSummary.slice(0, 120)}`)
      }
      if (result.warning) toast(result.warning, { icon: '⚠️' })
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not fetch brand from website')
    } finally {
      setFetchingWebsiteBrand(false)
    }
  }

  const handleFetchSocialStyle = async () => {
    const brandId = (watch('brand_id') || selectedBrand?.id || '').trim()
    const handleOrUrl = socialHandleUrl.trim()
    if (!brandId) {
      toast.error('Select or fetch a brand first (website fetch saves to Brand Kit).')
      return
    }
    if (handleOrUrl.length < 2) {
      toast.error('Enter an Instagram or Facebook URL or @handle')
      return
    }
    setFetchingSocialStyle(true)
    try {
      const result = await brandsApi.fetchSocialStyle(brandId, { handle_or_url: handleOrUrl })
      patchApiCache<Brand[]>('brands', (current) => {
        const prior = current ?? brands ?? []
        const idx = prior.findIndex((b) => b.id === brandId)
        if (idx < 0) return prior
        const voiceRules = {
          ...((prior[idx].voice_rules as Record<string, unknown>) || {}),
          social_style_profile: result.social_style_profile,
          social_style_fetched_at: result.social_style_profile.fetched_at,
        }
        const next = [...prior]
        next[idx] = { ...prior[idx], voice_rules: voiceRules }
        return next
      })
      await refetchBrands({ background: true })
      try {
        const kit = await brandsApi.getKit(brandId)
        setSelectedBrandKit(kit)
      } catch {
        /* optional */
      }
      setBriefSocialStyle(result.social_style_profile)
      setSocialHandleUrl(socialStyleInputValue(result.social_style_profile))
      const savedHandle = (result.social_style_profile.handle || '').replace(/^@/, '').trim()
      if (savedHandle) {
        setSelectedSocialAccountKey(`${brandId}::${savedHandle}`)
        setSocialAccountModeNew(false)
      }
      const posts = result.social_style_profile.post_count_analyzed ?? 0
      toast.success(
        posts > 0
          ? `Social style saved — ${posts} posts analyzed for image prompts`
          : 'Social style saved to Brand Kit'
      )
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not fetch social style')
    } finally {
      setFetchingSocialStyle(false)
    }
  }

  const handleDiscoverCompetitors = async () => {
    const brandId = (watch('brand_id') || selectedBrand?.id || '').trim()
    const handleOrUrl = socialHandleUrl.trim()
    if (!brandId) {
      toast.error('Select or fetch a brand first.')
      return
    }
    if (!handleOrUrl && !brandSavedSocialStyle?.handle && !brandSavedSocialStyle?.profile_url) {
      toast.error('Fetch client social style first (Facebook or Instagram URL).')
      return
    }
    const geography = (watch('geography') ?? '').trim()
    if (geography.length < 2) {
      toast.error('Set Service Location first (e.g. Melbourne VIC) — competitors are local only.')
      return
    }
    setDiscoveringCompetitors(true)
    try {
      const result = await brandsApi.discoverCompetitors(brandId, {
        handle_or_url: handleOrUrl || undefined,
        industry: (watch('title') ?? '').trim(),
        niche: (watch('niche') ?? '').trim(),
        geography: (watch('geography') ?? '').trim(),
      })
      patchApiCache<Brand[]>('brands', (current) => {
        const prior = current ?? brands ?? []
        const idx = prior.findIndex((b) => b.id === brandId)
        if (idx < 0) return prior
        const voiceRules = {
          ...((prior[idx].voice_rules as Record<string, unknown>) || {}),
          competitor_candidates: result.competitor_candidates,
        }
        const next = [...prior]
        next[idx] = { ...prior[idx], voice_rules: voiceRules }
        return next
      })
      await refetchBrands({ background: true })
      try {
        const kit = await brandsApi.getKit(brandId)
        setSelectedBrandKit(kit)
      } catch {
        /* optional */
      }
      const first = buildCompetitorCandidateOptions(result.competitor_candidates)[0]
      if (first) {
        setSelectedCompetitorKey(first.value)
        setCompetitorModeNew(false)
        setCompetitorHandleUrl(candidateInputValue(first.candidate))
      }
      toast.success(
        result.competitor_candidates.length
          ? `Found ${result.competitor_candidates.length} competitors near ${geography} — select one, then Analyze & save`
          : 'No competitors found'
      )
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not fetch competitors')
    } finally {
      setDiscoveringCompetitors(false)
    }
  }

  const handleFetchCompetitorSocial = async () => {
    const brandId = (watch('brand_id') || selectedBrand?.id || '').trim()
    const handleOrUrl = competitorHandleUrl.trim()
    if (!brandId) {
      toast.error('Select or fetch a brand first.')
      return
    }
    if (handleOrUrl.length < 2) {
      toast.error('Enter a competitor Instagram or Facebook URL or @handle')
      return
    }
    setFetchingCompetitor(true)
    try {
      const result = await brandsApi.fetchCompetitorSocial(brandId, {
        handle_or_url: handleOrUrl,
        industry: (watch('title') ?? '').trim(),
        niche: (watch('niche') ?? '').trim(),
      })
      patchApiCache<Brand[]>('brands', (current) => {
        const prior = current ?? brands ?? []
        const idx = prior.findIndex((b) => b.id === brandId)
        if (idx < 0) return prior
        const voiceRules = {
          ...((prior[idx].voice_rules as Record<string, unknown>) || {}),
          competitor_social_insights: result.competitor_social_insights,
        }
        const next = [...prior]
        next[idx] = { ...prior[idx], voice_rules: voiceRules }
        return next
      })
      await refetchBrands({ background: true })
      try {
        const kit = await brandsApi.getKit(brandId)
        setSelectedBrandKit(kit)
      } catch {
        /* optional */
      }
      setUseCompetitorInsights(true)
      setCompetitorHandleUrl(competitorInputValue(result.competitor_insight))
      const compHandle = (result.competitor_insight.handle || '').replace(/^@/, '').trim()
      const compPlatform = (result.competitor_insight.platform || 'social').toLowerCase()
      if (compHandle) {
        setSelectedCompetitorKey(`${compPlatform}::${compHandle}`)
        setCompetitorModeNew(false)
      }
      const posts = result.competitor_insight.post_count_analyzed ?? 0
      toast.success(
        posts > 0
          ? `Competitor saved — ${posts} posts analyzed for posting logic`
          : 'Competitor analysis saved to Brand Kit'
      )
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not analyze competitor')
    } finally {
      setFetchingCompetitor(false)
    }
  }

  const handleDeleteCompetitor = async (insight: CompetitorSocialInsight) => {
    const brandId = (watch('brand_id') || selectedBrand?.id || '').trim()
    const handle = (insight.handle || '').replace(/^@/, '')
    if (!brandId || !handle) return
    try {
      const result = await brandsApi.deleteCompetitorSocial(brandId, {
        handle,
        platform: insight.platform || '',
      })
      patchApiCache<Brand[]>('brands', (current) => {
        const prior = current ?? brands ?? []
        const idx = prior.findIndex((b) => b.id === brandId)
        if (idx < 0) return prior
        const voiceRules = {
          ...((prior[idx].voice_rules as Record<string, unknown>) || {}),
          competitor_social_insights: result.competitor_social_insights,
        }
        const next = [...prior]
        next[idx] = { ...prior[idx], voice_rules: voiceRules }
        return next
      })
      await refetchBrands({ background: true })
      try {
        const kit = await brandsApi.getKit(brandId)
        setSelectedBrandKit(kit)
      } catch {
        /* optional */
      }
      if (result.competitor_social_insights.length === 0) {
        setUseCompetitorInsights(false)
        setSelectedCompetitorKey('')
        setCompetitorModeNew(true)
        setCompetitorHandleUrl('')
      } else {
        const remaining = buildSavedCompetitorOptions(result.competitor_social_insights)
        const next = remaining[0]
        if (next) {
          setSelectedCompetitorKey(next.value)
          setCompetitorModeNew(false)
          setCompetitorHandleUrl(competitorInputValue(next.insight))
        }
      }
      toast.success('Competitor removed')
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not remove competitor')
    }
  }

  const handleParseStrategy = async (file: File) => {
    const lower = file.name.toLowerCase()
    const allowed = ['.md', '.txt', '.markdown', '.doc', '.docx']
    if (!allowed.some((ext) => lower.endsWith(ext))) {
      toast.error('Upload a .md, .txt, .doc, or .docx strategy file')
      return
    }
    setParsingStrategy(true)
    setStrategyFileName(file.name)
    try {
      const result = await generationApi.parseStrategyFile(file)
      setStrategyParsed(result)

      const fromDoc = [...(result.formats || []), ...(result.variants || []).map((v) => v.format || '')]
      const imageFmts = fromDoc
        .filter((f): f is 'static' | 'carousel' => f === 'static' || f === 'carousel')
        .filter((f, i, arr) => arr.indexOf(f) === i)
      const videoFmts = fromDoc
        .filter((f): f is 'reel' | 'video' => f === 'reel' || f === 'video')
        .filter((f, i, arr) => arr.indexOf(f) === i)
      if (imageFmts.length) {
        setMediaType('image')
        setValue('formats', imageFmts, { shouldValidate: true })
      } else if (videoFmts.length) {
        setMediaType('video')
        setValue('formats', [videoFmts[0]], { shouldValidate: true })
      }

      if (result.industry) setValue('title', result.industry, { shouldValidate: true })
      if (result.niche) setValue('niche', result.niche, { shouldValidate: true })
      if (result.geography) setValue('geography', result.geography, { shouldValidate: true })
      if (result.objective_id) setValue('objective_id', result.objective_id, { shouldValidate: true })
      if (result.cta) setValue('cta', result.cta, { shouldValidate: true })
      if (result.offer) setValue('offer', result.offer, { shouldValidate: true })
      if (result.product_name) setValue('product_name', result.product_name, { shouldValidate: true })
      if (result.ad_copy_tone) setValue('ad_copy_tone', result.ad_copy_tone, { shouldValidate: true })
      if (result.audience_type) setValue('audience_type', result.audience_type, { shouldValidate: true })
      if (result.age_range) setValue('age_range', result.age_range, { shouldValidate: true })
      if (result.languages) setValue('languages', result.languages, { shouldValidate: true })
      if (result.placements?.length) setValue('placements', result.placements, { shouldValidate: true })
      if (result.hook_frameworks?.length) {
        setValue('hook_frameworks', result.hook_frameworks, { shouldValidate: true })
      }
      const count = Math.max(1, Math.min(100, result.target_variant_count || result.variants.length || 1))
      setValue('target_variant_count', count, { shouldValidate: true })
      if (result.notes) setValue('notes', result.notes.slice(0, 2000), { shouldValidate: true })
      if (result.offer) setImageCampaignOffer(result.offer)

      const fashionRetailPromo =
        result.creative_style === 'fashion_retail_promo' ||
        result.creative_style === 'fashion_retail_photo'
      const fashionPhotoOnly = result.creative_style === 'fashion_retail_photo'
      if (result.image_aspect_ratio?.trim()) {
        setImageRatio(result.image_aspect_ratio.trim())
        setImageRatioCustom('')
      } else if (fashionRetailPromo && !fashionPhotoOnly) {
        setImageRatio('1:1')
        setImageRatioCustom('')
      }

      const campaignCta = (result.cta || '').trim()
      const hasPerVariantCta = result.variants.some((v) => Boolean((v.cta || '').trim()))
      const shells = result.variants.slice(0, count).map((v) => {
        const card = Number(v.carousel_index || 0)
        const total = Number(v.carousel_total || 0)
        const retailPromo = Boolean(
          v.retail_promo || result.creative_style === 'fashion_retail_promo' || (fashionRetailPromo && !v.photo_only)
        )
        const photoOnly = Boolean(v.photo_only && !retailPromo)
        const isCloser = Boolean(total && card && card >= total) || Boolean((v.cta || '').trim())
        return {
          ...emptyImageVariantSlot(),
          ad_angle: (v.ad_angle || '').trim(),
          format: (v.format || '').trim() || undefined,
          carousel_index: card || undefined,
          carousel_total: total || undefined,
          carousel_group: (v.carousel_group || '').trim() || undefined,
          photo_only: photoOnly || undefined,
          retail_promo: retailPromo || undefined,
          aspect_ratio: (v.aspect_ratio || '').trim() || undefined,
          use_cases: v.use_cases?.length ? v.use_cases : retailPromo ? ['lifestyle', 'product_person'] : [],
          cta: photoOnly
            ? ''
            : ((v.cta || '').trim() || (hasPerVariantCta ? '' : campaignCta)),
          hook: (v.hook || '').trim(),
          message: (v.message || '').trim(),
          image_hook: photoOnly ? '' : (v.image_hook || '').trim(),
          image_headline: photoOnly ? '' : (v.image_headline || '').trim(),
          product_model: (v.product_name || '').trim() || undefined,
          product_focus: normalizeProductFocus(v.product_focus) || undefined,
          prompt: (v.prompt || '').trim(),
          reasoning: (v.reasoning || '').trim(),
        }
      })
      setImageVariantSlots(shells.length ? shells : [emptyImageVariantSlot()])

      const match = (brands ?? []).find(
        (b) => b.name.trim().toLowerCase() === (result.brand_name || '').trim().toLowerCase()
      )
      if (match) {
        setValue('brand_id', match.id, { shouldValidate: true })
      }

      const fmtLabel = imageFmts
        .map((f) => (f === 'carousel' ? 'Carousel' : 'Static'))
        .join(' + ')
      toast.success(
        shells.length >= 8 && result.variants.length >= 8
          ? `Strategy processed — ${shells.length} posts from MD (Generate AI for all to write prompts).`
          : fashionRetailPromo && !fashionPhotoOnly
          ? `Strategy processed — ${shells.length} retail promo ads (1:1/9:16, angles + on-image copy). Click Generate AI for all.`
          : fashionPhotoOnly
            ? `Strategy processed — ${shells.length} fashion static ads (photo only). Text stays in feed copy.`
            : `Strategy processed — brief filled (${fmtLabel || 'formats'}). Click Generate AI for all to write hooks.`
      )
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not read strategy file')
      setStrategyParsed(null)
    } finally {
      setParsingStrategy(false)
    }
  }

  useEffect(() => {
    if (mediaType !== 'image') return
    setImageVariantSlots((prev) =>
      prev.map((slot, i) => ({
        ...slot,
        ad_angle: variantAngleAssignments[i] || slot.ad_angle,
      }))
    )
  }, [variantAngleAssignments, mediaType])

  const wantsVideo = (selectedFormats ?? []).some(isVideoFormat)
  const wantsImageOnly =
    (selectedFormats ?? []).length > 0 &&
    (selectedFormats ?? []).every((f) => f === 'static' || f === 'carousel')
  const isHeyGen = wantsVideo && genSettings.videoModel.toLowerCase().startsWith('heygen')
  const isHiggsfieldVideo =
    wantsVideo && genSettings.videoModel.toLowerCase().startsWith('hf-')
  const isSeedanceVideo = isSeedanceVideoModel(genSettings.videoModel)
  const isPdfScriptMode = scriptBuildMode === 'pdf' && wantsVideo
  const isCustomScriptMode = scriptBuildMode === 'custom' && wantsVideo
  const isWebsiteScriptMode = scriptBuildMode === 'website' && wantsVideo
  const isAlternateScriptMode = isPdfScriptMode || isCustomScriptMode || isWebsiteScriptMode
  /** PDF/custom hide campaign detail steps; website keeps audience, script, etc. */
  const hideCampaignDetailSteps = isPdfScriptMode || isCustomScriptMode

  const imageModelSelect = useMemo(
    () =>
      buildModelSelectGroups(catalog?.image_models, [
        { value: 'nano-banana-2', label: 'Nano Banana 2' },
      ]),
    [catalog?.image_models]
  )
  const videoModelSelect = useMemo(
    () =>
      buildModelSelectGroups(catalog?.video_models, [
        { value: 'heygen-video-agent', label: 'HeyGen Video Agent (v3)' },
        { value: 'veo-3.1', label: 'Veo 3.1 (Runway)' },
      ]),
    [catalog?.video_models]
  )
  const promptLlmSelect = useMemo(
    () =>
      buildModelSelectGroups(catalog?.prompt_llm_models, [
        {
          value: 'anthropic/claude-sonnet-4.6',
          label: 'Claude Sonnet 4.6 (default)',
        },
      ]),
    [catalog?.prompt_llm_models]
  )

  const referenceImagesPayload = useMemo(
    () =>
      briefReferenceImages.map((r) => ({
        asset_id: r.asset_id,
        file_url: r.file_url,
        analysis: r.analysis ?? {},
        is_product_reference: Boolean(r.is_product_reference),
        product_reference_context: r.product_reference_context,
      })),
    [briefReferenceImages],
  )

  const submitLabel = useMemo(() => {
    if (wantsVideo && wantsImageOnly) return 'Create & Generate Video'
    if (wantsVideo) return 'Create & Generate Video'
    if (wantsImageOnly) return 'Create brief →'
    return 'Create brief →'
  }, [wantsVideo, wantsImageOnly])

  // When user picks Image → force static/carousel formats; when Video → keep what they had or default to reel
  // Creative Studio tab is a standalone panel — don't touch formats.
  useEffect(() => {
    if (mediaType === 'creative_studio') return
    if (mediaType === 'image') {
      const fmts = watch('formats') ?? []
      const imageFmts = fmts.filter((f) => !isVideoFormat(f))
      if (imageFmts.length === 0) {
        setValue('formats', ['static'], { shouldValidate: true })
      } else if (imageFmts.length !== fmts.length) {
        setValue('formats', imageFmts, { shouldValidate: true })
      }
      setScriptBuildMode('manual')
    } else {
      const fmts = watch('formats') ?? []
      if (!fmts.some(isVideoFormat)) {
        setValue('formats', ['reel'], { shouldValidate: true })
      }
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [mediaType])

  useEffect(() => {
    if (scriptBuildMode !== 'pdf') return
    const fmts = watch('formats') ?? []
    if (!fmts.some(isVideoFormat)) {
      setValue('formats', ['video'], { shouldValidate: true })
      setGenSettings((prev) => ({ ...prev, videoModel: 'heygen-video-agent' }))
    }
  }, [scriptBuildMode, setValue, watch])

  const aspectHint = useMemo(
    () => aspectHintFromFormats(selectedFormats ?? [], selectedPlacements ?? []),
    [selectedFormats, selectedPlacements]
  )

  const formatOptions = useMemo(
    () => mapCreativeFormatOptions(catalog?.creative_formats ?? []),
    [catalog?.creative_formats]
  )

  const placementOptions = useMemo(
    () => mapPlacementOptions(catalog?.placements ?? []),
    [catalog?.placements]
  )

  useEffect(() => {
    const fmts = selectedFormats ?? []
    let placements = [...(selectedPlacements ?? [])]
    if (fmts.some(isLandscapeVideoFormat) && !placements.some(isLandscapePlacement)) {
      placements = [...placements.filter((p) => !isPortraitPlacement(p)), 'landscape']
    }
    if (fmts.some(isPortraitVideoFormat) && !placements.some(isPortraitPlacement)) {
      if (!placements.includes('reels')) placements.push('reels')
    }
    if (placements.join(',') !== (selectedPlacements ?? []).join(',')) {
      setValue('placements', placements, { shouldValidate: true })
    }
  }, [selectedFormats, selectedPlacements, setValue])

  useEffect(() => {
    if (!wantsVideo || !isHeyGen) return
    const fmts = selectedFormats ?? []
    if (fmts.includes('video') && !fmts.includes('reel')) {
      setHeygenSettings((s) => ({ ...s, aspectRatio: '16:9', aspectRatioCustom: '' }))
    } else if (fmts.includes('reel')) {
      setHeygenSettings((s) => ({ ...s, aspectRatio: '9:16', aspectRatioCustom: '' }))
    }
  }, [selectedFormats, wantsVideo, isHeyGen])

  const formValues = watch()

  const avatarLabel =
    catalog?.heygen_avatar_options?.find((o) => o.id === genSettings.heygenAvatarId)?.label ?? ''
  const voiceLabel =
    catalog?.heygen_voice_options?.find((o) => o.id === genSettings.heygenVoiceId)?.label ?? ''

  const applyReferenceImageFile = (file: File | null) => {
    if (referenceImagePreview) URL.revokeObjectURL(referenceImagePreview)
    if (!file) {
      setReferenceImageFile(null)
      setReferenceImagePreview(null)
      return
    }
    if (!file.type.startsWith('image/')) {
      toast.error('Please choose an image file (PNG, JPG, or WebP).')
      return
    }
    setReferenceImageFile(file)
    setReferenceImagePreview(URL.createObjectURL(file))
  }

  const handleReferenceImagePaste = (event: React.ClipboardEvent) => {
    const item = Array.from(event.clipboardData.items).find((entry) => entry.type.startsWith('image/'))
    const file = item?.getAsFile()
    if (file) {
      event.preventDefault()
      applyReferenceImageFile(file)
    }
  }

  const onInvalid = (formErrors: FieldErrors<FormData>) => {
    const first = Object.values(formErrors).find((err) => err?.message)
    toast.error(first?.message ? String(first.message) : 'Please complete the required fields above.')
  }

  const validateManualFields = (data: FormData): string | null => {
    // Image mode: audience / tone / placement are hidden — not required.
    // Per-variant CTAs live on Image Variants (step 5); step 7 is optional.
    if (mediaType === 'image') return null
    if (!data.cta?.trim() || data.cta.trim().length < 2) {
      return 'Enter a call to action (step 7).'
    }
    if (!data.audience_type?.trim() || data.audience_type.trim().length < 2) {
      return 'Fill in Target Audience (step 3).'
    }
    if (!data.geography?.trim() || data.geography.trim().length < 2) {
      return 'Fill in Geography (step 3).'
    }
    if (!data.age_range?.trim() || data.age_range.trim().length < 2) {
      return 'Fill in Age Range (step 3).'
    }
    if (!data.languages?.trim() || data.languages.trim().length < 2) {
      return 'Fill in Languages (step 3).'
    }
    if (!data.ad_copy_tone?.trim() || data.ad_copy_tone.trim().length < 2) {
      return 'Fill in Tone of Voice (step 3).'
    }
    if (mediaType === 'video' && !data.placements?.length) {
      return 'Select at least one platform / placement (step 4).'
    }
    return null
  }

  const handleGenerateScriptNotes = async () => {
    const d = formValues
    const targetAudience = [d.audience_type, d.geography, d.age_range].filter(Boolean).join(' · ')
    setGeneratingNotes(true)
    try {
      // Use ICP-driven generation when audience + offer are available
      const useIcp = Boolean((targetAudience || d.audience_type) && (d.offer || d.product_name))
      if (useIcp) {
        const result = await generationApi.generateIcpScript({
          target_audience: targetAudience,
          offer: d.offer ?? '',
          product_name: d.product_name ?? '',
          brand_name: selectedBrand?.name ?? '',
          ad_copy_tone: d.ad_copy_tone ?? '',
          cta: d.cta ?? '',
          target_seconds: genSettings.videoDurationSeconds,
          forbidden_words: selectedBrand?.forbidden_words,
        })
        const text = result.script.full_script.trim()
        setValue('notes', text, { shouldValidate: true })
        toast.success('ICP-driven script notes saved — review in step 8')
      } else {
        const result = await generationApi.generateAvatarScript({
          purpose: 'brief_notes',
          script_prompt: d.notes || undefined,
          product_name: d.product_name ?? '',
          offer: d.offer ?? '',
          brand_name: selectedBrand?.name ?? '',
          target_audience: targetAudience,
          ad_copy_tone: d.ad_copy_tone ?? '',
          cta: d.cta ?? '',
          target_seconds: genSettings.videoDurationSeconds,
          forbidden_words: selectedBrand?.forbidden_words,
        })
        const text = result.full_script.trim()
        setValue('notes', text, { shouldValidate: true })
        toast.success('Talking points saved — generate spoken script in step 8')
      }
    } catch {
      toast.error('Could not generate — add OPENROUTER_API_KEY and restart backend')
    } finally {
      setGeneratingNotes(false)
    }
  }

  const strategySeedForSlot = (index: number, slot: ImageVariantSlot) => {
    const src = strategyParsed?.variants[index]
    const scene = (slot.prompt || src?.prompt || src?.reasoning || '').trim()
    return {
      id: src?.id || `V${index + 1}`,
      format: slot.format || src?.format || 'static',
      ad_angle: slot.ad_angle || src?.ad_angle || '',
      scene,
      prompt: scene,
      client_hook: (src?.hook || slot.hook || '').trim(),
      client_message: (src?.message || slot.message || '').trim(),
      post_type: (src?.post_type || '').trim() || undefined,
      design_notes: (src?.design_notes || '').trim() || undefined,
      product_model: (slot.product_model || src?.product_name || '').trim() || undefined,
      image_hook: (slot.image_hook || src?.image_hook || '').trim(),
      image_headline: (slot.image_headline || src?.image_headline || '').trim(),
      use_cases: slot.use_cases?.length ? slot.use_cases : src?.use_cases || [],
      carousel_index: slot.carousel_index || src?.carousel_index || undefined,
      carousel_total: slot.carousel_total || src?.carousel_total || undefined,
      carousel_group: slot.carousel_group || src?.carousel_group || undefined,
      photo_only: Boolean(slot.photo_only && !slot.retail_promo && !src?.retail_promo),
      retail_promo: Boolean(slot.retail_promo || src?.retail_promo),
      aspect_ratio: slot.aspect_ratio || src?.aspect_ratio || undefined,
      product_focus: slot.product_focus || imageProductFocus || undefined,
      cta: (slot.cta || src?.cta || '').trim(),
    }
  }

  const handleGenerateImageSlot = async (index: number) => {
    const d = formValues
    const slot = imageVariantSlots[index]
    if (!slot) return
    const campaignName = campaignLabel(d.title ?? '', d.niche)
    if (campaignName.length < 2) {
      toast.error('Enter an industry before generating image plans.')
      return
    }
    const siblingHooks = imageVariantSlots
      .map((s, i) => (i === index ? '' : s.hook.trim()))
      .filter(Boolean)
    const siblingPrompts = imageVariantSlots
      .map((s, i) => (i === index ? '' : s.prompt.trim()))
      .filter(Boolean)
    setGeneratingSlotIndex(index)
    try {
      const slotAngle = variantAngleAssignments[index]
      const catalogShot = imageProductFocus === 'product_only'
      const plan = await generationApi.previewIcpImagePlan({
        campaign_name: campaignName,
        brand_name: selectedBrand?.name ?? websiteBrand?.brand_name ?? '',
        industry:
          (d.title ?? '').trim() ||
          selectedBrand?.industry ||
          websiteBrand?.industry ||
          '',
        niche: (d.niche ?? '').trim(),
        objective_id: d.objective_id ?? '',
        cta: d.cta ?? '',
        offer: imageCampaignOffer.trim() || slot.offer.trim() || undefined,
        geography: (d.geography ?? '').trim() || undefined,
        brand_facts: resolvedBrandFacts ?? undefined,
        brand_id: (d.brand_id || selectedBrand?.id || '').trim() || undefined,
        social_style_profile: activeSocialStyle ?? undefined,
        use_competitor_insights: useCompetitorInsights,
        ...(useCompetitorInsights && brandSavedCompetitors.length > 0
          ? { competitor_social_insights: brandSavedCompetitors }
          : {}),
        image_visual_style: imageVisualStyle || undefined,
        product_focus: (slot.product_focus || imageProductFocus) || undefined,
        ...resolvedBrandVisuals,
        image_aspect_ratio: imageRatioCustom.trim() || imageRatio,
        hook_frameworks: (slot.product_focus || imageProductFocus) === 'product_only'
          ? []
          : slotAngle
            ? [slotAngle]
            : (d.hook_frameworks ?? []),
        variant_count: 1,
        existing_hooks: siblingHooks,
        existing_prompts: siblingPrompts,
        creative_format:
          slot.format === 'carousel' || slot.format === 'static'
            ? slot.format
            : (d.formats ?? []).includes('carousel') &&
                !(d.formats ?? []).includes('static')
              ? 'carousel'
              : 'static',
        // Always send per-slot seed so the backend gets the slot's prompt,
        // product_focus, ad_angle even when the brief was loaded from DB
        // (strategyParsed is only set after a fresh MD upload this session).
        strategy_variants: [strategySeedForSlot(index, slot)],
        ...(strategyParsed
          ? { strategy_notes: strategyParsed.notes || strategyParsed.reasoning || '' }
          : {}),
        ...(referenceImagesPayload.length ? { reference_images: referenceImagesPayload } : {}),
        exact_product_reference: exactProductReference,
        llm_model: genSettings.promptLlmModel || undefined,
      })
      const variant = plan.variants[0]
      if (!variant) {
        toast.error('No variant returned — try again')
        return
      }
      if (plan.icp_text?.trim()) {
        setImageIcpText(plan.icp_text.trim())
      }
      if (plan.campaign_hook) setImageCampaignHook(plan.campaign_hook)
      if (plan.campaign_headline) setImageCampaignHeadline(plan.campaign_headline)
      if (plan.campaign_cta) setValue('cta', plan.campaign_cta, { shouldValidate: true })
      const generatedAt = new Date().toISOString()
      const hook = variant.hook || slot.hook
      const message = variant.message || slot.message
      const derived = relatedOnImageLines(hook, message)
      const carouselCard = isCarouselSlot(slot, d.formats)
      const lastCarousel = isLastCarouselCard(slot, index, imageVariantSlots, d.formats)
      const photoOnly = Boolean(slot.photo_only && !slot.retail_promo)
      setImageVariantSlots((prev) =>
        prev.map((s, i) =>
          i === index
            ? {
                ...s,
                use_cases: variant.use_cases?.length ? variant.use_cases : s.use_cases,
                hook,
                message,
                image_hook: photoOnly
                  ? ''
                  : s.image_hook.trim() ||
                    (variant.image_hook && !isIncompleteOnImageLine(variant.image_hook)
                      ? variant.image_hook
                      : derived.image_hook),
                image_headline: photoOnly
                  ? ''
                  : s.image_headline.trim() ||
                    (variant.image_headline &&
                    !isIncompleteOnImageLine(variant.image_headline)
                      ? variant.image_headline
                      : derived.image_headline),
                cta: photoOnly
                  ? ''
                  : carouselCard
                    ? lastCarousel
                      ? s.cta || variant.cta || plan.campaign_cta || (d.cta ?? '')
                      : ''
                    : s.cta || variant.cta || '',
                offer: carouselCard ? '' : variant.offer || imageCampaignOffer.trim() || s.offer,
                prompt: variant.prompt || s.prompt,
                reasoning: variant.reasoning || '',
                ad_angle: slot.ad_angle || variant.ad_angle || slotAngle || '',
                product_model: s.product_model || '',
                generated_at: generatedAt,
              }
            : s
        )
      )
      toast.success(`Variant ${index + 1} AI plan ready — ICP from campaign name`)
    } catch {
      toast.error('Could not generate plan — check OPENROUTER_API_KEY and restart backend')
    } finally {
      setGeneratingSlotIndex(null)
    }
  }

  const handleGenerateAllImageSlots = async () => {
    const d = formValues
    const campaignName = campaignLabel(d.title ?? '', d.niche)
    if (campaignName.length < 2) {
      toast.error('Enter an industry before generating image plans.')
      return
    }
    const slots = imageVariantSlots
    const chunks =
      slots.length > 5 ? chunkSlotIndicesForGeneration(slots) : [slots.map((_, i) => i)]

    setGeneratingAllSlots(true)
    toast.loading(
      chunks.length > 1
        ? `Generating ${slots.length} cards in ${chunks.length} batches…`
        : `Generating ${slots.length} image plans…`,
      { id: 'gen-all-slots' }
    )
    try {
      let icpText = imageIcpText
      let campaignHook = imageCampaignHook
      let campaignHeadline = imageCampaignHeadline
      const existingHooks: string[] = []
      const existingPrompts: string[] = []
      let filled = 0
      const generatedAt = new Date().toISOString()

      for (let ci = 0; ci < chunks.length; ci++) {
        const indices = chunks[ci]
        const chunkAngle = variantAngleAssignments[indices[0]]
        const chunkSlot = slots[indices[0]]
        // Build the effective focus per slot in this chunk.
        // If every slot shares the same focus we can safely send a campaign-level
        // override; if they differ, we send undefined so the backend relies purely
        // on the per-seed product_focus values (set in strategySeedForSlot).
        const chunkFocusValues = indices.map(
          (i) => (slots[i]?.product_focus || imageProductFocus || '') as string
        )
        const allSameChunkFocus = chunkFocusValues.every((f) => f === chunkFocusValues[0])
        const chunkEffectiveFocus = allSameChunkFocus ? chunkFocusValues[0] : ''
        const catalogShot = chunkEffectiveFocus === 'product_only'
        if (chunks.length > 1) {
          toast.loading(
            `Batch ${ci + 1}/${chunks.length} — ${indices.length} card${indices.length !== 1 ? 's' : ''}…`,
            { id: 'gen-all-slots' }
          )
        }
        const plan = await generationApi.previewIcpImagePlan({
          campaign_name: campaignName,
          brand_name: selectedBrand?.name ?? websiteBrand?.brand_name ?? '',
          industry:
            (d.title ?? '').trim() ||
            selectedBrand?.industry ||
            websiteBrand?.industry ||
            '',
          niche: (d.niche ?? '').trim(),
          objective_id: d.objective_id ?? '',
          cta: d.cta ?? '',
          offer: imageCampaignOffer.trim() || undefined,
          geography: (d.geography ?? '').trim() || undefined,
          brand_facts: resolvedBrandFacts ?? undefined,
          brand_id: (d.brand_id || selectedBrand?.id || '').trim() || undefined,
          social_style_profile: activeSocialStyle ?? undefined,
        use_competitor_insights: useCompetitorInsights,
        ...(useCompetitorInsights && brandSavedCompetitors.length > 0
          ? { competitor_social_insights: brandSavedCompetitors }
          : {}),
          image_visual_style: imageVisualStyle || undefined,
          product_focus: chunkEffectiveFocus || undefined,
          ...resolvedBrandVisuals,
          image_aspect_ratio: imageRatioCustom.trim() || imageRatio,
          hook_frameworks: catalogShot
            ? []
            : chunkAngle
              ? [chunkAngle]
              : (d.hook_frameworks ?? []),
          variant_count: indices.length,
          existing_hooks: existingHooks,
          existing_prompts: existingPrompts,
          creative_format:
            (d.formats ?? []).includes('carousel') &&
            (d.formats ?? []).includes('static')
              ? 'mixed'
              : (d.formats ?? []).includes('carousel')
                ? 'carousel'
                : 'static',
          // Always send per-slot seeds — slots store prompt, product_focus,
          // ad_angle from the MD parse even when the brief is opened from DB.
          strategy_variants: indices.map((i) => strategySeedForSlot(i, slots[i])),
          ...(strategyParsed
            ? { strategy_notes: strategyParsed.notes || strategyParsed.reasoning || '' }
            : {}),
          ...(referenceImagesPayload.length ? { reference_images: referenceImagesPayload } : {}),
        exact_product_reference: exactProductReference,
          llm_model: genSettings.promptLlmModel || undefined,
        })

        if (plan.icp_text?.trim()) icpText = plan.icp_text.trim()
        if (plan.campaign_hook) campaignHook = plan.campaign_hook
        if (plan.campaign_headline) campaignHeadline = plan.campaign_headline
        if (plan.campaign_cta) setValue('cta', plan.campaign_cta, { shouldValidate: true })

        setImageVariantSlots((prev) => {
          const next = [...prev]
          indices.forEach((slotIdx, vi) => {
            const variant = plan.variants[vi]
            if (!variant) return
            const s = next[slotIdx]
            const hook = variant.hook || s.hook
            const message = variant.message || s.message
            const derived = relatedOnImageLines(hook, message)
            const carouselCard = isCarouselSlot(s, d.formats)
            const lastCarousel = isLastCarouselCard(s, slotIdx, prev, d.formats)
            const photoOnly = Boolean(s.photo_only && !s.retail_promo)
            next[slotIdx] = {
              ...s,
              use_cases: variant.use_cases?.length ? variant.use_cases : s.use_cases,
              hook,
              message,
              image_hook: photoOnly
                ? ''
                : s.image_hook.trim() ||
                  (variant.image_hook && !isIncompleteOnImageLine(variant.image_hook)
                    ? variant.image_hook
                    : derived.image_hook),
              image_headline: photoOnly
                ? ''
                : s.image_headline.trim() ||
                  (variant.image_headline &&
                  !isIncompleteOnImageLine(variant.image_headline)
                    ? variant.image_headline
                    : derived.image_headline),
              cta: photoOnly
                ? ''
                : carouselCard
                  ? lastCarousel
                    ? s.cta || variant.cta || plan.campaign_cta || (d.cta ?? '')
                    : ''
                  : s.cta || variant.cta || '',
              offer: carouselCard ? '' : variant.offer || imageCampaignOffer.trim() || s.offer,
              prompt: variant.prompt || s.prompt,
              reasoning: variant.reasoning || '',
              ad_angle: s.ad_angle || variant.ad_angle || variantAngleAssignments[slotIdx] || '',
              generated_at: generatedAt,
            }
          })
          return next
        })

        for (const v of plan.variants) {
          if (v.hook?.trim()) existingHooks.push(v.hook.trim())
          if (v.prompt?.trim()) existingPrompts.push(v.prompt.trim())
          filled++
        }
      }

      if (icpText) setImageIcpText(icpText)
      if (campaignHook) setImageCampaignHook(campaignHook)
      if (campaignHeadline) setImageCampaignHeadline(campaignHeadline)

      toast.success(
        `${filled} image variant${filled !== 1 ? 's' : ''} filled from ICP — edit hook, message, CTA, and prompt as needed`,
        { id: 'gen-all-slots' }
      )
    } catch {
      toast.error(
        'Could not generate plans — request timed out or failed. Cards generate in batches of 6; wait for the spinner to finish.',
        { id: 'gen-all-slots' }
      )
    } finally {
      setGeneratingAllSlots(false)
    }
  }

  const handleDownloadBriefExcel = () => {
    const isImageBrief = mediaType === 'image'
    const payload = buildBriefExportPayload({
      formValues,
      catalog: catalog ?? undefined,
      brandName: selectedBrand?.name ?? '',
      aspectHint,
      genSettings,
      heygenSettings: wantsVideo && isHeyGen ? heygenSettings : undefined,
      avatarLabel,
      voiceLabel,
      scriptBuildMode,
      websiteUrl,
      customPrompt,
      pdfFileName: pdfFile?.name,
      referenceImageName: referenceImageFile?.name,
      approvedScript: approvedAvatarScript,
      generatedFullScript: avatarExportSnapshot.generatedFullScript,
      // For image briefs, we generate ICP from the image plan preview (Image Variants step).
      icpText: isImageBrief ? imageIcpText : avatarExportSnapshot.icpText,
      customScriptText: customPrompt,
      strategyPreview: isImageBrief ? null : strategyPreview,
      labelForIds: (options, ids) => labelsForIds(options, ids),
    })

    const hasIcp = Boolean(
      (isImageBrief ? imageIcpText : avatarExportSnapshot.icpText)?.trim() ||
        (!isImageBrief ? strategyPreview?.icp_text?.trim() : null)
    )
    const hasScript = isImageBrief
      ? true
      : Boolean(
          avatarExportSnapshot.generatedFullScript?.trim() ||
            avatarExportSnapshot.spokenScript?.trim() ||
            approvedAvatarScript?.trim()
        )

    if (!hasIcp && !hasScript) {
      toast(
        isImageBrief
          ? 'Exporting image brief — generate image ICP + variant plans in “Image Variants” first.'
          : 'Exporting Steps 1–9 — generate ICP + script in Step 8 first for full export.',
        {
        icon: '⚠️',
        }
      )
    } else {
      toast.success('Brief exported to Excel (.xlsx)')
    }

    downloadBriefExcel(payload)
  }

  const onSubmit = async (data: FormData) => {
    if (creatingBriefRef.current) return
    if (!catalog) {
      toast.error('Still loading models — wait a moment and try again.')
      return
    }
    const wantsVidOnSubmitEarly = (data.formats ?? []).some(isVideoFormat)
    const heygenOnSubmitEarly =
      wantsVidOnSubmitEarly && genSettings.videoModel.toLowerCase().startsWith('heygen')
    const isPdfMode = scriptBuildMode === 'pdf' && wantsVidOnSubmitEarly
    const isCustomMode = scriptBuildMode === 'custom' && wantsVidOnSubmitEarly
    const isWebsiteMode = scriptBuildMode === 'website' && wantsVidOnSubmitEarly
    const isAlternateMode = isPdfMode || isCustomMode || isWebsiteMode

    if (!isAlternateMode) {
      const manualError = validateManualFields(data)
      if (manualError) {
        toast.error(manualError)
        return
      }
      if (heygenOnSubmitEarly && !approvedAvatarScript) {
        toast.error('Generate and approve your spoken script in step 8 before creating.')
        return
      }
    }

    if (isPdfMode) {
      if (!pdfFile) {
        toast.error('Choose a PDF that contains your full spoken script.')
        return
      }
      if (heygenOnSubmitEarly && (!genSettings.heygenAvatarId || !genSettings.heygenVoiceId)) {
        toast.error('Select HeyGen avatar and voice.')
        return
      }
    }

    if (isCustomMode) {
      if (!customPrompt.trim()) {
        toast.error('Paste your video prompt or script.')
        return
      }
      if (!referenceImageFile) {
        toast.error('Add a reference image (upload or paste).')
        return
      }
      if (isHeyGen && (!genSettings.heygenAvatarId || !genSettings.heygenVoiceId)) {
        toast.error('Select HeyGen avatar and voice.')
        return
      }
    }

    if (isWebsiteMode) {
      if (!websiteUrl.trim()) {
        toast.error('Paste your website page URL.')
        return
      }
      if (heygenOnSubmitEarly && !approvedAvatarScript) {
        toast.error('Generate and approve your website script in step 8 before creating.')
        return
      }
    }

    creatingBriefRef.current = true

    const fill = (s: string | undefined, minLen: number, placeholder: string) => {
      const t = (s ?? '').trim()
      return t.length >= minLen ? t : placeholder
    }

    const d: FormData = isAlternateMode
      ? {
          ...data,
          product_name: fill(data.product_name, 2, isCustomMode ? 'Custom prompt' : 'From PDF'),
          offer: fill(data.offer, 3, isCustomMode ? 'See custom prompt' : 'See PDF script'),
          audience_type: fill(data.audience_type, 2, 'General'),
          geography: fill(data.geography, 2, '—'),
          age_range: fill(data.age_range, 2, '—'),
          languages: fill(data.languages, 2, 'English'),
          ad_copy_tone: fill(data.ad_copy_tone, 2, isCustomMode ? 'Match prompt' : 'Match PDF'),
          cta: fill(data.cta, 2, 'Learn more'),
          notes: fill(
            data.notes,
            0,
            isCustomMode ? customPrompt.trim() : 'Full script from uploaded PDF.'
          ),
          placements: data.placements?.length
            ? data.placements
            : (data.formats ?? []).some(isLandscapeVideoFormat)
              ? ['landscape']
              : ['reels'],
        }
      : data

    const audience = {
      audience_type: d.audience_type,
      geography: d.geography,
      age_range: d.age_range,
      languages: d.languages,
    }
    const targetAudience = [d.audience_type, d.geography, d.age_range, d.languages].join(' · ')
    const wantsVidOnSubmit = (d.formats ?? []).some(isVideoFormat)
    const heygenOnSubmit =
      wantsVidOnSubmit && genSettings.videoModel.toLowerCase().startsWith('heygen')

    try {
      let referenceImageUrl: string | undefined
      if (isCustomScriptMode && referenceImageFile) {
        const asset = await assetsApi.upload(referenceImageFile, undefined, 'reference_image')
        referenceImageUrl = asset.file_url
      }

      let brandId = (d.brand_id || '').trim()
      // Website fetch now saves into Brand Kit immediately — only create here if somehow missing.
      if (d.brand_source === 'website' && !brandId) {
        if (!websiteBrand) {
          toast.error('Fetch brand from website first (click Fetch brand).')
          return
        }
        const created = await brandsApi.create({
          name: websiteBrand.brand_name || campaignLabel(d.title, d.niche),
          industry: (d.title || 'general').trim().replace(/\s+/g, '_').toLowerCase() || 'general',
          primary_color: websiteBrand.primary_color,
          secondary_color: websiteBrand.secondary_color,
          language: 'English',
          voice_rules: {
            website_url: websiteBrand.source_url || d.website_url || '',
            scraped_from: 'firecrawl',
            scraped_at: new Date().toISOString(),
            brand_facts: websiteBrand.brand_facts || null,
          },
        })
        brandId = created.id
        if (websiteBrand.logo_url) {
          try {
            await brandsApi.update(brandId, { logo_url: websiteBrand.logo_url })
          } catch {
            /* logo optional */
          }
        }
        clearApiCache('brands')
      }
      if (!brandId) {
        toast.error('Select a brand or fetch one from a website URL.')
        return
      }

      const briefTitle = campaignLabel(d.title ?? '', d.niche)

      const brief = await briefsApi.create({
        brand_id: brandId,
        title: briefTitle,
        objective: optionLabel(catalog.objectives, d.objective_id),
        target_audience: targetAudience,
        formats: d.formats as AdFormat[],
        ad_copy_tone: (d.ad_copy_tone ?? '').trim(),
        cta:
          (d.cta ?? '').trim() ||
          imageVariantSlots.map((s) => s.cta.trim()).find(Boolean) ||
          'Learn More',
        product_name: d.product_name ?? '',
        key_benefits: {
          target_variant_count: d.target_variant_count,
          offer: d.offer ?? '',
          placements: d.placements ?? [],
          hook_frameworks: d.hook_frameworks ?? [],
          notes: d.notes ?? '',
          audience,
          objective_id: d.objective_id,
          industry: d.title ?? '',
          niche: d.niche ?? '',
          brand_source: d.brand_source,
          ...(d.brand_source === 'website'
            ? {
                website_url: d.website_url ?? websiteBrand?.source_url ?? '',
                scraped_brand: websiteBrand ?? undefined,
              }
            : {}),
          ...(strategyParsed
            ? {
                strategy_file: strategyParsed.filename || strategyFileName,
                strategy_reasoning: strategyParsed.reasoning || '',
              }
            : {}),
          cta_text:
            (d.cta ?? '').trim() ||
            imageVariantSlots.map((s) => s.cta.trim()).find(Boolean) ||
            '',
          tone_text: (d.ad_copy_tone ?? '').trim(),
          copy_model: genSettings.copyModel,
          ...(genSettings.imageModel ? { image_model: genSettings.imageModel } : {}),
          media_type: mediaType,
          ...(mediaType === 'image'
            ? {
                image_aspect_ratio: imageRatioCustom.trim() || imageRatio,
                use_competitor_insights: useCompetitorInsights,
                ...(imageProductFocus ? { product_focus: imageProductFocus } : {}),
                ...(imageVisualStyle ? { image_visual_style: imageVisualStyle } : {}),
                ...(imageCampaignHook.trim() ? { campaign_hook: imageCampaignHook.trim() } : {}),
                ...(imageCampaignHeadline.trim()
                  ? { campaign_headline: imageCampaignHeadline.trim() }
                  : {}),
                image_variants: imageVariantSlots.map((s, i) => ({
                  use_cases: s.use_cases,
                  hook: s.hook.trim(),
                  message: s.message.trim(),
                  image_hook: s.image_hook.trim(),
                  image_headline: s.image_headline.trim(),
                  cta: s.cta.trim(),
                  offer: s.offer.trim(),
                  prompt: s.prompt.trim(),
                  reasoning: s.reasoning.trim() || undefined,
                  ad_angle: s.ad_angle || variantAngleAssignments[i] || undefined,
                  format: s.format || undefined,
                  carousel_index: s.carousel_index || undefined,
                  carousel_total: s.carousel_total || undefined,
                  carousel_group: s.carousel_group || undefined,
                  photo_only: s.photo_only || undefined,
                  retail_promo: s.retail_promo || undefined,
                  aspect_ratio: s.aspect_ratio || undefined,
                  product_focus: s.product_focus || undefined,
                  product_model: s.product_model?.trim() || undefined,
                  generated_at: s.generated_at ?? undefined,
                })),
                ...(imageIcpText?.trim() ? { image_icp_text: imageIcpText.trim() } : {}),
                ...(referenceImagesPayload.length
                  ? { reference_images: referenceImagesPayload }
                  : {}),
                exact_product_reference: exactProductReference,
                // Back-compat for older readers: first slot as shared fields
                ...(imageVariantSlots[0]?.use_cases?.length
                  ? { image_use_cases: imageVariantSlots[0].use_cases }
                  : {}),
                ...(imageVariantSlots[0]?.prompt?.trim()
                  ? { image_prompt_override: imageVariantSlots[0].prompt.trim() }
                  : {}),
              }
            : {}),
          ...(wantsVidOnSubmit
            ? {
                video_model: genSettings.videoModel,
                video_duration_seconds: genSettings.videoDurationSeconds,
                heygen_avatar_id: genSettings.heygenAvatarId,
                heygen_voice_id: genSettings.heygenVoiceId,
                higgsfield_voice_preset: genSettings.higgsfieldVoicePreset,
                heygen_settings:
                  heygenOnSubmit ? heygenSettingsForApi(heygenSettings) : undefined,
                avatar_script: isPdfScriptMode
                  ? undefined
                  : isCustomScriptMode
                    ? customPrompt.trim()
                    : approvedAvatarScript ?? undefined,
                script_source: isPdfScriptMode
                  ? 'pdf'
                  : isCustomScriptMode
                    ? 'custom'
                    : isWebsiteScriptMode
                      ? 'website'
                      : 'manual',
                ...(isCustomScriptMode
                  ? {
                      custom_prompt: customPrompt.trim(),
                      video_script_skeleton: customPrompt.trim(),
                      video_script_skeleton_version: '6',
                      reference_image_url: referenceImageUrl,
                    }
                  : {}),
                ...(isWebsiteScriptMode ? { website_url: websiteUrl.trim() } : {}),
                ...(avatarExportSnapshot.statsImageUrls.length > 0 ||
                avatarExportSnapshot.statsImageUrl
                  ? {
                      stats_image_url:
                        avatarExportSnapshot.statsImageUrls[0] ??
                        avatarExportSnapshot.statsImageUrl ??
                        undefined,
                      stats_image_urls: avatarExportSnapshot.statsImageUrls.length
                        ? avatarExportSnapshot.statsImageUrls
                        : avatarExportSnapshot.statsImageUrl
                          ? [avatarExportSnapshot.statsImageUrl]
                          : undefined,
                      performance_stats: avatarExportSnapshot.performanceStats ?? undefined,
                      performance_stats_per_image:
                        avatarExportSnapshot.performanceStatsPerImage?.length
                          ? avatarExportSnapshot.performanceStatsPerImage
                          : undefined,
                    }
                  : {}),
              }
            : {}),
        },
      })

      if (isPdfScriptMode && pdfFile) {
        await briefsApi.uploadScriptPdf(brief.id, pdfFile)
        toast.success('PDF script imported')
      }

      // Bust list cache so Briefs page shows the new draft immediately if user navigates back.
      clearBriefListCaches()

      toast.success(
        wantsVidOnSubmit
          ? 'Brief created — opening it so you can Generate video'
          : 'Brief created — opening it now…'
      )

      // Hard navigate: soft router.push can hang after create (sidebar Links also freeze).
      // Full page load resets Next App Router transition state.
      try {
        document.body.style.overflow = ''
      } catch {
        /* ignore */
      }
      const dest = `/briefs/${brief.id}?autogenerate=1`
      window.location.assign(dest)
    } catch (err: unknown) {
      creatingBriefRef.current = false
      toast.error(extractApiError(err) || 'Failed to create brief')
    }
  }

  const needsApprovedScript =
    wantsVideo && isHeyGen && !hideCampaignDetailSteps && !approvedAvatarScript

  const submitBlocked =
    (brandSource === 'brand' && !hasBrands && !(watch('brand_id') || '').trim()) ||
    (brandSource === 'website' && !websiteBrand && !(watch('brand_id') || '').trim()) ||
    !catalog ||
    (isPdfScriptMode && !pdfFile) ||
    (isCustomScriptMode && (!customPrompt.trim() || !referenceImageFile)) ||
    (isWebsiteScriptMode && !websiteUrl.trim()) ||
    needsApprovedScript

  const durationOptions = durationOptionsForVideoModel(genSettings.videoModel)

  useEffect(() => {
    if (!isSeedanceVideo) return
    if (genSettings.videoDurationSeconds > SEEDANCE_MAX_DURATION_SECONDS) {
      setGenSettings((prev) => ({
        ...prev,
        videoDurationSeconds: SEEDANCE_MAX_DURATION_SECONDS,
      }))
    }
  }, [isSeedanceVideo, genSettings.videoModel])

  return (
    <div className="min-h-full app-mesh-bg">
      <header className="sticky top-0 z-20 glass-topbar flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-charcoal tracking-tight">Create Brief</h1>
          <span className="text-[10px] font-bold uppercase tracking-wider text-accent bg-accent/10 border border-accent/25 px-2.5 py-1 rounded-full">
            {mediaType === 'image'
              ? 'Image'
              : mediaType === 'video'
                ? 'Video'
                : mediaType === 'hero_ai_image'
                  ? 'Hero AI Image'
                  : 'Creative Studio'}
          </span>
        </div>
        <Button type="submit" form="brief-form" variant="outline" size="sm" disabled={isSubmitting}>
          Save Brief
        </Button>
      </header>

      {/* Image / Video / Creative Studio tabs */}
      <div className="sticky top-[65px] z-10 border-b border-border bg-white/90 backdrop-blur-md">
        <div className="w-full max-w-[1600px] mx-auto px-6 md:px-8 flex gap-1">
          {([
            { id: 'image' as const,            label: 'Image',           hint: 'Static & carousel ads' },
            { id: 'video' as const,            label: 'Video',           hint: 'Portrait & landscape' },
            { id: 'hero_ai_image' as const,   label: 'Hero AI Image',   hint: 'Upload and burn exact copy' },
            { id: 'creative_studio' as const,  label: 'Creative Studio', hint: 'Chat playground · Seedance', badge: 'NEW' },
          ]).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setMediaType(tab.id)}
              className={`relative flex items-center gap-1.5 px-5 py-3 text-sm font-semibold transition-colors ${
                mediaType === tab.id
                  ? 'text-charcoal'
                  : 'text-mid hover:text-charcoal'
              }`}
            >
              {tab.label}
              {'badge' in tab && tab.badge && (
                <span className="px-1.5 py-0.5 text-[9px] font-bold rounded-full bg-accent/15 text-accent border border-accent/20 leading-none">
                  {tab.badge}
                </span>
              )}
              <span className="hidden sm:inline text-mid font-normal text-[11px] ml-0.5">
                · {tab.hint}
              </span>
              {mediaType === tab.id && (
                <span className="absolute left-2 right-2 bottom-0 h-0.5 rounded-full bg-accent" />
              )}
            </button>
          ))}
        </div>
      </div>

      {mediaType === 'creative_studio' && (
        <CreativeStudioTab
          brandId={(watch('brand_id') || selectedBrand?.id || '').trim() || undefined}
          brandName={selectedBrand?.name ?? websiteBrand?.brand_name}
          productName={watch('product_name') || ''}
          briefTitle={watch('title') || undefined}
        />
      )}

      {mediaType === 'hero_ai_image' && (
        <HeroAiImageTab
          brandName={selectedBrand?.name ?? websiteBrand?.brand_name}
          industry={watch('title') || selectedBrand?.industry || ''}
          niche={watch('niche') || ''}
          productName={watch('product_name') || ''}
          imageModel={genSettings.imageModel || 'openai-gpt-image-2'}
          brandId={(watch('brand_id') || '').trim()}
          brands={brands ?? []}
          onBrandChange={(brandId) => setValue('brand_id', brandId, { shouldValidate: true })}
          logoUrl={selectedBrand?.logo_url}
          logoOnLightUrl={
            typeof selectedBrandKit?.logo_variations?.on_light === 'string'
              ? selectedBrandKit.logo_variations.on_light
              : undefined
          }
          briefTitle={watch('title') || 'Hero AI Image'}
        />
      )}

      <form
        id="brief-form"
        onSubmit={handleSubmit(onSubmit, onInvalid)}
        className={`w-full max-w-[1600px] mx-auto p-6 md:p-8 space-y-4 ${mediaType === 'creative_studio' || mediaType === 'hero_ai_image' ? 'hidden' : ''}`}
      >
        <div className="space-y-4">
          {brandSource === 'brand' && !hasBrands && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              No brands yet. Create one in{' '}
              <Link href="/brand-kit" className="font-semibold text-teal hover:underline">
                Brand Kit
              </Link>
              , or switch to <strong>Website URL</strong> below to fetch brand automatically.
            </div>
          )}

          <BriefSection title="Industry & Brand" step="1">
            <div className="rounded-xl border border-dashed border-accent/50 bg-accent/5 p-4 space-y-2">
              <p className="text-xs font-bold text-navy uppercase tracking-wide">
                Upload strategy file (.md, .docx)
              </p>
              <p className="text-[11px] text-mid">
                Optional. Choose a markdown or Word file, then click <strong>Process strategy</strong> — that fills
                industry, niche, location, and angles. Variant hooks stay empty until you click{' '}
                <strong>Generate AI for all</strong>. Brand itself still comes from{' '}
                <strong>Brand Kit</strong> or <strong>Website URL</strong> below.
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <input
                  id="strategy-file-top"
                  type="file"
                  accept=".md,.txt,.markdown,.doc,.docx,text/markdown,text/plain,application/vnd.openxmlformats-officedocument.wordprocessingml.document,application/msword"
                  disabled={parsingStrategy}
                  onChange={(e) => {
                    const file = e.target.files?.[0]
                    if (!file) return
                    setStrategyFilePending(file)
                    setStrategyFileName(file.name)
                    setStrategyParsed(null)
                  }}
                  className="block min-w-0 flex-1 text-xs text-mid file:mr-3 file:rounded-full file:border file:border-accent/40 file:bg-white file:px-3.5 file:py-2 file:text-xs file:font-semibold file:text-charcoal hover:file:bg-accent/10"
                />
                <Button
                  type="button"
                  size="sm"
                  variant="primary"
                  isLoading={parsingStrategy}
                  disabled={!strategyFilePending || parsingStrategy}
                  onClick={() => {
                    if (strategyFilePending) void handleParseStrategy(strategyFilePending)
                  }}
                >
                  Process strategy
                </Button>
              </div>
              {strategyFilePending && !strategyParsed && !parsingStrategy && (
                <p className="text-xs text-mid">
                  Ready: <strong>{strategyFileName}</strong> — click Process strategy to fill the brief.
                </p>
              )}
              {parsingStrategy && (
                <p className="text-xs font-medium text-charcoal">Processing strategy… filling the brief (not variants)</p>
              )}
              {strategyParsed && !parsingStrategy && (
                <p className="text-xs font-semibold text-charcoal">
                  Brief loaded from {strategyParsed.brand_name || strategyFileName}. Empty variant
                  slots are ready — click <strong>Generate AI for all</strong> for catchy hooks.
                </p>
              )}
            </div>

            <Input
              label="Industry"
              placeholder="e.g. Mortgage Broking, Dental, Digital Marketing"
              error={errors.title?.message}
              {...register('title')}
            />
            <Input
              label="Niche"
              placeholder="e.g. First home buyers, Refinance, Investment loans"
              error={errors.niche?.message}
              {...register('niche')}
            />

            {mediaType === 'image' && (
              <div>
                <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                  Visual style <span className="font-normal normal-case text-mid">(optional)</span>
                </p>
                <p className="text-[10px] text-mid mb-2">
                  Scroll-stopping cartoon/sketch ads: problem character + competitor failures scattered,
                  hero product fresh as the answer — works for retail, trade, health, drinks, any industry.
                </p>
                <div className="flex flex-wrap gap-2">
                  {IMAGE_VISUAL_STYLE_OPTIONS.map((opt) => (
                    <button
                      key={opt.value || 'auto'}
                      type="button"
                      onClick={() => setImageVisualStyle(opt.value)}
                      className={`px-3 py-2 text-xs font-semibold rounded-full border transition-all text-left ${
                        imageVisualStyle === opt.value
                          ? 'border-accent/50 bg-accent/10 text-charcoal'
                          : 'border-border text-mid hover:border-accent/30'
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
                {IMAGE_VISUAL_STYLE_OPTIONS.find((o) => o.value === imageVisualStyle)?.hint ? (
                  <p className="mt-2 text-[10px] text-mid leading-relaxed">
                    {IMAGE_VISUAL_STYLE_OPTIONS.find((o) => o.value === imageVisualStyle)?.hint}
                  </p>
                ) : null}
              </div>
            )}

            {/* Service Location — AU state/city picker below Niche */}
            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">Service Location</p>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <Select
                  placeholder="— Pick an AU state or city —"
                  groups={AU_GEO_GROUPS}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val) setValue('geography', val, { shouldValidate: true })
                  }}
                />
                <Input
                  placeholder="Or type a suburb / region (e.g. Gold Coast QLD)"
                  error={errors.geography?.message}
                  {...register('geography')}
                />
              </div>
              <p className="mt-1 text-[10px] text-mid">
                Selecting a state or city sets the location for ad copy and image scenes. Override in the text field if needed.
              </p>
            </div>

            <p className="text-[10px] text-mid -mt-1">
              Industry = what your brand is. Niche = who/what this campaign targets.
              Objective drives the action (e.g. Conversions/Purchase → end customers, not other brokers).
            </p>

            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                Brand source
              </p>
              <div className="flex flex-wrap gap-2 mb-3">
                {(
                  [
                    { id: 'brand' as const, label: 'Brand Kit' },
                    { id: 'website' as const, label: 'Website URL' },
                  ] as const
                ).map((opt) => (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setValue('brand_source', opt.id, { shouldValidate: true })}
                    className={`px-3.5 py-2 text-xs font-semibold rounded-full border transition-all ${
                      brandSource === opt.id
                        ? 'border-accent/50 bg-accent/10 text-charcoal'
                        : 'border-border text-mid hover:border-accent/30'
                    }`}
                  >
                    {opt.label}
                  </button>
                ))}
              </div>

              {brandSource === 'brand' ? (
                <div className="relative">
                  <Input
                    label="Brand"
                    placeholder={hasBrands ? 'Type brand name to search' : 'No brands available'}
                    value={brandSearch}
                    disabled={!hasBrands}
                    error={errors.brand_id?.message}
                    onChange={(event) => {
                      const value = event.target.value
                      setBrandSearch(value)
                      if (value.trim().toLowerCase() !== (selectedBrand?.name || '').trim().toLowerCase()) {
                        setValue('brand_id', '', { shouldValidate: true })
                      }
                    }}
                  />
                  <input type="hidden" {...register('brand_id')} />
                  {brandSearch.trim() &&
                    matchingBrands.length > 0 &&
                    (!selectedBrand ||
                      selectedBrand.name.trim().toLowerCase() !==
                        brandSearch.trim().toLowerCase()) && (
                    <div className="absolute z-20 left-0 right-0 top-full mt-1 max-h-52 overflow-y-auto rounded-xl border border-border bg-white shadow-lg">
                      {matchingBrands.map((brand) => (
                        <button
                          key={brand.id}
                          type="button"
                          className="block w-full px-4 py-2.5 text-left text-sm text-charcoal hover:bg-accent/10"
                          onClick={() => {
                            setBrandSearch(brand.name)
                            setValue('brand_id', brand.id, {
                              shouldDirty: true,
                              shouldValidate: true,
                            })
                          }}
                        >
                          {brand.name}
                        </button>
                      ))}
                    </div>
                  )}
                  {brandSearch.trim() &&
                    matchingBrands.length === 0 &&
                    !selectedBrand && (
                    <p className="mt-1 text-[11px] text-mid">No matching brand found.</p>
                  )}
                </div>
              ) : (
                <div className="space-y-3">
                  <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
                    <div className="flex-1">
                      <Input
                        label="Website URL"
                        placeholder="https://yourbrand.com"
                        error={errors.website_url?.message}
                        {...register('website_url')}
                      />
                    </div>
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0 mb-0.5"
                      isLoading={fetchingWebsiteBrand}
                      onClick={() => void handleFetchWebsiteBrand()}
                    >
                      Fetch brand
                    </Button>
                  </div>
                  <p className="text-[11px] text-mid">
                    Fetches colours, logo, <strong>services, locations, reviews &amp; rates</strong> with Firecrawl,
                    then <strong>saves into Brand Kit</strong> so ads can use verified facts only (ACCC-safe).
                  </p>
                  {websiteBrand && (
                    <div className="rounded-xl border border-accent/25 bg-accent/5 p-3 flex flex-wrap items-center gap-3">
                      {websiteBrand.logo_url ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img
                          src={websiteBrand.logo_url}
                          alt={websiteBrand.brand_name}
                          className="h-10 w-10 object-contain rounded-lg bg-white border border-border"
                        />
                      ) : (
                        <div className="h-10 w-10 rounded-lg bg-white border border-border" />
                      )}
                      <div className="min-w-0 flex-1">
                        <p className="text-sm font-bold text-charcoal truncate">
                          {websiteBrand.brand_name}
                        </p>
                        <p className="text-[11px] text-mid">
                          Saved to Brand Kit — pick it under Brand Kit next time
                        </p>
                      </div>
                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-6 h-6 rounded-full border border-border"
                          style={{ background: websiteBrand.primary_color }}
                          title={websiteBrand.primary_color}
                        />
                        <span
                          className="w-6 h-6 rounded-full border border-border"
                          style={{ background: websiteBrand.secondary_color }}
                          title={websiteBrand.secondary_color}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {mediaType === 'image' && (
              <ReferenceImagesPanel
                brandId={(watch('brand_id') || selectedBrand?.id || '').trim() || undefined}
                brandName={selectedBrand?.name ?? websiteBrand?.brand_name ?? ''}
                industry={(watch('title') || selectedBrand?.industry || '').trim()}
                niche={(watch('niche') || '').trim()}
                productName={(watch('product_name') || '').trim()}
                selected={briefReferenceImages}
                onChange={setBriefReferenceImages}
                onExactProductChange={setExactProductReference}
              />
            )}

            {resolvedBrandFacts && summarizeBrandFacts(resolvedBrandFacts) && (
              <div className="rounded-xl border border-border bg-surface-elevated/80 p-3 space-y-1.5">
                <p className="text-xs font-bold text-navy uppercase tracking-wide">
                  Verified brand facts
                  {resolvedBrandFacts.confidence ? (
                    <span className="ml-2 font-medium normal-case tracking-normal text-mid">
                      · confidence {resolvedBrandFacts.confidence}
                    </span>
                  ) : null}
                </p>
                <p className="text-[11px] text-charcoal leading-relaxed">
                  {summarizeBrandFacts(resolvedBrandFacts)}
                </p>
                <p className="text-[10px] text-mid">
                  These facts feed ICP + image prompts. Missing items will not be invented in ad copy.
                </p>
              </div>
            )}

            {(watch('brand_id') || selectedBrand) && (
              <div className="rounded-xl border border-border bg-surface-elevated/80 p-3 space-y-3">
                <p className="text-xs font-bold text-navy uppercase tracking-wide">
                  Social media visual style
                </p>
                <p className="text-[10px] text-mid">
                  Fetch from Instagram or Facebook — saved to Brand Kit for this brand. AI uses the saved
                  account and style automatically on every brief.
                </p>
                {brandSavedSocialStyle && hasSocialStyleSummary(brandSavedSocialStyle) ? (
                  <div className="rounded-lg border border-accent/20 bg-accent/5 p-2.5 space-y-1.5">
                    <p className="text-[10px] font-bold uppercase tracking-wide text-navy">
                      Active for this brand
                    </p>
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <p className="text-[11px] font-semibold text-charcoal">
                        {socialStyleAccountLabel(brandSavedSocialStyle)}
                        {brandSavedSocialStyle.fetched_at ? (
                          <span className="ml-1 font-normal text-mid">
                            · {new Date(brandSavedSocialStyle.fetched_at).toLocaleDateString()}
                          </span>
                        ) : null}
                        {brandSavedSocialStyle.post_count_analyzed != null ? (
                          <span className="ml-1 font-normal text-mid">
                            · {brandSavedSocialStyle.post_count_analyzed} posts
                          </span>
                        ) : null}
                      </p>
                      {brandSavedSocialStyle.profile_url ? (
                        <a
                          href={brandSavedSocialStyle.profile_url}
                          target="_blank"
                          rel="noreferrer"
                          className="text-[10px] text-accent hover:underline shrink-0"
                        >
                          View profile
                        </a>
                      ) : null}
                    </div>
                    {summarizeSocialStyle(brandSavedSocialStyle) ? (
                      <p className="text-[11px] text-charcoal leading-relaxed line-clamp-3">
                        {summarizeSocialStyle(brandSavedSocialStyle)}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                <Select
                  label="Saved social accounts"
                  placeholder={
                    savedSocialAccountOptions.length > 0
                      ? 'Select saved account'
                      : 'No saved accounts yet'
                  }
                  value={socialAccountModeNew ? '__new__' : selectedSocialAccountKey}
                  onChange={(e) => {
                    const val = e.target.value
                    if (val === '__new__') {
                      setSocialAccountModeNew(true)
                      setSelectedSocialAccountKey('')
                      setSocialHandleUrl('')
                      return
                    }
                    setSocialAccountModeNew(false)
                    setSelectedSocialAccountKey(val)
                    const picked = savedSocialAccountOptions.find((o) => o.value === val)
                    if (picked) {
                      setSocialHandleUrl(socialStyleInputValue(picked.profile))
                    }
                  }}
                  options={[
                    ...savedSocialAccountOptions.map((o) => ({
                      value: o.value,
                      label: o.label,
                    })),
                    { value: '__new__', label: '+ Add new account…' },
                  ]}
                />
                {selectedSavedSocialAccount && !socialAccountModeNew ? (
                  <div className="rounded-lg border border-border/70 bg-white/60 p-2.5 space-y-1">
                    <p className="text-[10px] text-mid">
                      Selected · {selectedSavedSocialAccount.label}
                    </p>
                    {summarizeSocialStyle(selectedSavedSocialAccount.profile) ? (
                      <p className="text-[11px] text-charcoal leading-relaxed line-clamp-2">
                        {summarizeSocialStyle(selectedSavedSocialAccount.profile)}
                      </p>
                    ) : null}
                  </div>
                ) : null}
                <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
                  {(socialAccountModeNew || savedSocialAccountOptions.length === 0) && (
                    <div className="flex-1">
                      <Input
                        label="New Instagram / Facebook account"
                        placeholder="@yourbrand"
                        value={socialHandleUrl}
                        onChange={(e) => setSocialHandleUrl(e.target.value)}
                      />
                    </div>
                  )}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className={`shrink-0 mb-0.5 ${socialAccountModeNew || savedSocialAccountOptions.length === 0 ? '' : 'sm:ml-auto'}`}
                    isLoading={fetchingSocialStyle}
                    onClick={() => void handleFetchSocialStyle()}
                  >
                    {brandSavedSocialStyle ? 'Refresh social style' : 'Fetch social style'}
                  </Button>
                </div>
                {activeSocialStyle && hasSocialStyleSummary(activeSocialStyle) && briefSocialStyle ? (
                  <div className="rounded-lg border border-accent/20 bg-accent/5 p-2.5 space-y-2">
                    <p className="text-[11px] font-semibold text-charcoal">
                      Updated this session
                      {briefSocialStyle.fetched_at ? (
                        <span className="ml-1 font-normal text-mid">
                          · {new Date(briefSocialStyle.fetched_at).toLocaleDateString()}
                        </span>
                      ) : null}
                    </p>
                    {summarizeSocialStyle(briefSocialStyle) ? (
                      <p className="text-[11px] text-charcoal leading-relaxed">
                        {summarizeSocialStyle(briefSocialStyle)}
                      </p>
                    ) : null}
                    {(briefSocialStyleColors.cta || briefSocialStyleColors.background) && (
                      <div className="rounded-md border border-border/60 bg-white/70 p-2 space-y-1.5">
                        <p className="text-[10px] font-semibold text-navy uppercase tracking-wide">
                          Colours AI will use
                          {socialStyleAestheticLabel(activeSocialStyle) ? (
                            <span className="ml-2 normal-case tracking-normal text-accent font-bold">
                              · {socialStyleAestheticLabel(activeSocialStyle)}
                            </span>
                          ) : null}
                        </p>
                        <div className="flex flex-wrap gap-x-4 gap-y-2">
                          {briefSocialStyleColors.cta ? (
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className="w-6 h-6 shrink-0 rounded-full border border-border shadow-sm"
                                style={{ background: briefSocialStyleColors.cta }}
                                title={briefSocialStyleColors.cta}
                              />
                              <span className="text-[10px] text-charcoal">
                                CTA &amp; headline ·{' '}
                                <span className="font-mono">{briefSocialStyleColors.cta}</span>
                              </span>
                            </div>
                          ) : null}
                          {briefSocialStyleColors.background ? (
                            <div className="flex items-center gap-2 min-w-0">
                              <span
                                className="w-6 h-6 shrink-0 rounded-full border border-border shadow-sm"
                                style={{ background: briefSocialStyleColors.background }}
                                title={briefSocialStyleColors.background}
                              />
                              <span className="text-[10px] text-charcoal">
                                Background ·{' '}
                                <span className="font-mono">{briefSocialStyleColors.background}</span>
                              </span>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )}
                  </div>
                ) : null}

                <div className="border-t border-border/60 pt-3 space-y-2">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <p className="text-xs font-bold text-navy uppercase tracking-wide">
                      Competitor social analysis (optional)
                    </p>
                    <label className="flex items-center gap-2 text-[11px] text-charcoal cursor-pointer">
                      <input
                        type="checkbox"
                        className="rounded border-border"
                        checked={useCompetitorInsights}
                        disabled={brandSavedCompetitors.length === 0}
                        onChange={(e) => setUseCompetitorInsights(e.target.checked)}
                      />
                      Use saved competitor logic in image prompts
                    </label>
                  </div>
                  <p className="text-[10px] text-mid">
                    Click <strong>Fetch competitors</strong> to suggest accounts near your{' '}
                    <strong>Service Location</strong> (city + state + nearby states only — not worldwide).
                    Select one, then <strong>Analyze &amp; save</strong>.
                  </p>
                  <div className="flex flex-wrap gap-2">
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      disabled={!canDiscoverCompetitors}
                      isLoading={discoveringCompetitors}
                      onClick={() => void handleDiscoverCompetitors()}
                    >
                      Fetch competitors
                    </Button>
                    {!canDiscoverCompetitors ? (
                      <span className="text-[10px] text-mid self-center">
                        Set Service Location and fetch client social style first
                      </span>
                    ) : (
                      <span className="text-[10px] text-mid self-center">
                        Scoped to {(watch('geography') || '').trim()}
                      </span>
                    )}
                  </div>
                  <Select
                    label="Competitor accounts"
                    placeholder={
                      allCompetitorDropdownOptions.length > 1
                        ? 'Select suggested or analyzed competitor'
                        : 'Fetch competitors or add manually'
                    }
                    value={competitorModeNew ? '__new__' : selectedCompetitorKey}
                    onChange={(e) => {
                      const val = e.target.value
                      if (val === '__new__') {
                        setCompetitorModeNew(true)
                        setSelectedCompetitorKey('')
                        setCompetitorHandleUrl('')
                        return
                      }
                      setCompetitorModeNew(false)
                      setSelectedCompetitorKey(val)
                      const analyzed = savedCompetitorOptions.find((o) => o.value === val)
                      if (analyzed) {
                        setCompetitorHandleUrl(competitorInputValue(analyzed.insight))
                        return
                      }
                      const suggested = competitorCandidateOptions.find((o) => o.value === val)
                      if (suggested) {
                        setCompetitorHandleUrl(candidateInputValue(suggested.candidate))
                      }
                    }}
                    options={allCompetitorDropdownOptions}
                  />
                  {selectedCompetitorCandidate && !competitorModeNew ? (
                    <div className="rounded-lg border border-amber-200/80 bg-amber-50/80 p-2.5 space-y-1">
                      <p className="text-[11px] font-semibold text-charcoal">
                        {selectedCompetitorCandidate.candidate.name ||
                          selectedCompetitorCandidate.candidate.handle}{' '}
                        <span className="font-normal text-amber-800">· suggested, not analyzed yet</span>
                      </p>
                      {selectedCompetitorCandidate.candidate.reason ? (
                        <p className="text-[10px] text-charcoal leading-relaxed">
                          {selectedCompetitorCandidate.candidate.reason}
                        </p>
                      ) : null}
                      <p className="text-[10px] text-mid">
                        Click <strong>Analyze &amp; save</strong> to fetch their posts and save posting logic
                        to Brand Kit.
                      </p>
                    </div>
                  ) : null}
                  {selectedSavedCompetitor && !competitorModeNew ? (
                    <div className="rounded-lg border border-border/70 bg-white/60 p-2.5 space-y-1.5">
                      <div className="flex flex-wrap items-center justify-between gap-2">
                        <p className="text-[11px] font-semibold text-charcoal">
                          {competitorAccountLabel(selectedSavedCompetitor.insight)}
                          {selectedSavedCompetitor.insight.fetched_at ? (
                            <span className="ml-1 font-normal text-mid">
                              ·{' '}
                              {new Date(
                                selectedSavedCompetitor.insight.fetched_at
                              ).toLocaleDateString()}
                            </span>
                          ) : null}
                        </p>
                        <div className="flex items-center gap-2">
                          {selectedSavedCompetitor.insight.profile_url ? (
                            <a
                              href={selectedSavedCompetitor.insight.profile_url}
                              target="_blank"
                              rel="noreferrer"
                              className="text-[10px] text-accent hover:underline"
                            >
                              View
                            </a>
                          ) : null}
                          <button
                            type="button"
                            className="text-[10px] text-red-600 hover:underline"
                            onClick={() =>
                              void handleDeleteCompetitor(selectedSavedCompetitor.insight)
                            }
                          >
                            Remove
                          </button>
                        </div>
                      </div>
                      {summarizeCompetitorInsight(selectedSavedCompetitor.insight) ? (
                        <p className="text-[10px] text-charcoal leading-relaxed">
                          {summarizeCompetitorInsight(selectedSavedCompetitor.insight)}
                        </p>
                      ) : null}
                    </div>
                  ) : null}
                  <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
                    {(competitorModeNew ||
                      selectedCompetitorCandidate ||
                      (savedCompetitorOptions.length === 0 && competitorCandidateOptions.length === 0)) && (
                      <div className="flex-1">
                        <Input
                          label="Competitor Instagram / Facebook"
                          placeholder="@competitor or facebook.com/page"
                          value={competitorHandleUrl}
                          onChange={(e) => setCompetitorHandleUrl(e.target.value)}
                        />
                      </div>
                    )}
                    <Button
                      type="button"
                      variant="outline"
                      size="sm"
                      className="shrink-0 mb-0.5 sm:ml-auto"
                      isLoading={fetchingCompetitor}
                      onClick={() => void handleFetchCompetitorSocial()}
                    >
                      Analyze &amp; save
                    </Button>
                  </div>
                </div>
              </div>
            )}

            <Select
              label="Objective"
              options={objectiveOptions}
              placeholder="Select objective"
              value={objectiveId || ''}
              onChange={(e) =>
                setValue('objective_id', e.target.value, { shouldValidate: true })
              }
              error={errors.objective_id?.message}
            />
            <Input
              label="Target Variants"
              type="number"
              min={1}
              max={100}
              error={errors.target_variant_count?.message}
              {...register('target_variant_count')}
            />
          </BriefSection>

          <BriefSection title="Creative formats & models" step="2">

            {/* ── Creative format chips ── */}
            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                Creative format
              </p>
              {mediaType === 'image' && (
                <p className="text-xs text-sky-800 bg-sky-50 border border-sky-200 rounded-lg px-3 py-2 mb-3">
                  Image tab: select <strong>Static</strong>, <strong>Carousel</strong>, or both
                  if the campaign uses mixed stills and swipe cards. Switch to the{' '}
                  <strong>Video</strong> tab above for Portrait/Landscape.
                </p>
              )}
              {mediaType === 'video' && !wantsVideo && (selectedFormats ?? []).length > 0 && (
                <p className="text-xs text-teal-800 bg-teal-50 border border-teal-200 rounded-lg px-3 py-2 mb-3">
                  Select <strong>Landscape</strong> or <strong>Portrait</strong> to enable video generation (up to 4 minutes).
                </p>
              )}
              <ChipToggleGroup
                options={mediaType === 'image' ? formatOptions.filter((f) => !isVideoFormat(f.id)) : formatOptions}
                selected={selectedFormats ?? []}
                exclusive={false}
                onChange={(next) => {
                  setValue('formats', next, { shouldValidate: true })
                  // Meta carousel cards are square by default
                  if (mediaType === 'image' && next.includes('carousel')) {
                    setImageRatio('1:1')
                    setImageRatioCustom('')
                  }
                }}
                disabled={!catalog}
              />
              {mediaType === 'image' &&
                (selectedFormats ?? []).includes('static') &&
                (selectedFormats ?? []).includes('carousel') && (
                <p className="mt-2 text-[11px] text-mid">
                  Mixed campaign: Static = single stills; Carousel = swipe cards. Both stay
                  selected when the strategy file includes both types.
                </p>
              )}
              {mediaType === 'image' &&
                (selectedFormats ?? []).includes('carousel') &&
                !(selectedFormats ?? []).includes('static') && (
                <p className="mt-2 text-[11px] text-mid">
                  Carousel = one social swipe story. Card 1 problem → middle cards agitate/proof →
                  last card solution + CTA. Each variant is one card; keep 2+ variants. Angles colour
                  each beat but stay in the same story.
                </p>
              )}
              {errors.formats && <p className="mt-1 text-xs text-red-500">{errors.formats.message}</p>}
            </div>

            {/* ── Ad style / marketing approach (image mode) ── */}
            {mediaType === 'image' && imageProductFocus === 'product_only' ? (
              <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2.5">
                <p className="text-[11px] text-sky-900 leading-relaxed">
                  <strong>Product-alone catalog mode</strong> — ad angles are{' '}
                  <strong>not required</strong>. We auto-use a simple <strong>Product Hero / Catalog</strong>{' '}
                  layout (like a bike or retail catalog ad: product + model name + bold headline on brand
                  colors). Shot style controls the photo (no people).
                </p>
              </div>
            ) : mediaType === 'image' ? (
              <div>
                <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                  Ad angles <span className="font-normal normal-case text-mid">(optional)</span>
                </p>
                <AdAngleSelector
                  options={hookFrameworkOptions}
                  selected={selectedFrameworks ?? []}
                  onChange={(next) => setValue('hook_frameworks', next)}
                  onSuggest={() => void handleSuggestAdAngles(false)}
                  suggesting={suggestingAngles}
                  suggestionReason={angleSuggestionReason}
                />
              </div>
            ) : null}

            {/* ── Image ratio picker (image mode only) ── */}
            {mediaType === 'image' && (
              <div>
                <p className="text-xs font-bold text-navy uppercase tracking-wide mb-3">Image ratio</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
                  {[
                    { id: '1:1',    label: '1:1',      desc: 'Instagram · Facebook feed' },
                    { id: '4:3',    label: '4:3',      desc: 'Fashion retail · portrait feed' },
                    { id: '4:5',    label: '4:5',      desc: 'Instagram portrait feed' },
                    { id: '9:16',   label: '9:16',     desc: 'Reels · Stories · TikTok' },
                    { id: '16:9',   label: '16:9',     desc: 'Website · YouTube · Landscape' },
                    { id: '1.91:1', label: '1.91:1',   desc: 'Facebook · Google ads' },
                    { id: '2:3',    label: '2:3',      desc: 'Pinterest · Print' },
                  ].map((r) => (
                    <button
                      key={r.id}
                      type="button"
                      onClick={() => { setImageRatio(r.id); setImageRatioCustom('') }}
                      className={`relative flex flex-col gap-0.5 rounded-xl border-2 px-3 py-2.5 text-left transition-all focus:outline-none focus:ring-2 focus:ring-accent/40 ${
                        imageRatio === r.id && !imageRatioCustom
                          ? 'border-accent bg-accent/5 shadow-sm'
                          : 'border-border bg-surface hover:border-accent/40 hover:bg-accent/[0.03]'
                      }`}
                    >
                      <span className={`text-sm font-bold leading-none ${imageRatio === r.id && !imageRatioCustom ? 'text-accent' : 'text-charcoal'}`}>
                        {r.label}
                      </span>
                      <span className="text-[10px] text-mid leading-snug">{r.desc}</span>
                      {imageRatio === r.id && !imageRatioCustom && (
                        <span className="absolute top-1.5 right-1.5 w-3.5 h-3.5 rounded-full bg-accent flex items-center justify-center">
                          <svg className="w-2 h-2 text-white" fill="currentColor" viewBox="0 0 20 20">
                            <path fillRule="evenodd" d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z" clipRule="evenodd" />
                          </svg>
                        </span>
                      )}
                    </button>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <label className="text-xs font-semibold text-navy shrink-0">Custom ratio:</label>
                  <input
                    type="text"
                    placeholder="e.g. 3:4 or 1200x628"
                    value={imageRatioCustom}
                    onChange={(e) => setImageRatioCustom(e.target.value)}
                    className={`flex-1 rounded-lg border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 ${
                      imageRatioCustom ? 'border-accent bg-accent/5' : 'border-border bg-surface'
                    }`}
                  />
                  {imageRatioCustom && (
                    <button
                      type="button"
                      onClick={() => setImageRatioCustom('')}
                      className="text-xs text-mid hover:text-charcoal underline"
                    >
                      Clear
                    </button>
                  )}
                </div>
                <p className="mt-1.5 text-[10px] text-mid">
                  Selected: <strong className="text-charcoal">{imageRatioCustom.trim() || imageRatio}</strong>
                  {!imageRatioCustom && {
                    '1:1': ' — square, works everywhere',
                    '4:5': ' — portrait, best click-through on Instagram',
                    '9:16': ' — full-screen vertical',
                    '16:9': ' — landscape, website hero & YouTube',
                    '1.91:1': ' — Facebook/Google recommended',
                    '2:3': ' — Pinterest standard',
                  }[imageRatio]}
                </p>
              </div>
            )}

            {mediaType === 'video' && (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <div>
                <p className="text-xs font-bold text-navy uppercase tracking-wide mb-1">Aspect Ratio</p>
                <p className="text-sm text-mid bg-light border border-border rounded-lg px-3 py-2">{aspectHint}</p>
              </div>
              {wantsVideo && (
                <div>
                  <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">Duration</p>
                  <div className="flex flex-wrap gap-2">
                    {durationOptions.map((opt) => (
                      <ChipToggle
                        key={opt.id}
                        label={opt.label}
                        selected={String(genSettings.videoDurationSeconds) === opt.id}
                        onToggle={() =>
                          setGenSettings({ ...genSettings, videoDurationSeconds: Number(opt.id) })
                        }
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
            )}
            {isHiggsfieldVideo && mediaType === 'video' && (
              <p className="text-xs text-mid bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
                <strong>Higgsfield:</strong>{' '}
                {isSeedanceVideo ? (
                  <>
                    <strong>Seedance</strong> builds ads up to <strong>1m 30s</strong> as multiple{' '}
                    <strong>15s B-roll scenes</strong> (from your scene directions), then stitches
                    them. Add scene B-roll in the script step for best results. Voiceover/captions
                    are added after render.
                  </>
                ) : (
                  <>
                    Veo/DoP models are only <strong>5 seconds</strong> per clip. For longer ads
                    choose <strong>Kling v3.0</strong>, <strong>Marketing Studio Video</strong>, or{' '}
                    <strong>HeyGen</strong> (up to 4 minutes). Text/captions are added after
                    generation (not inside the AI video) so they stay readable.
                  </>
                )}
              </p>
            )}

            {mediaType === 'video' && (
            <div className="mt-4 pt-4 border-t border-violet-200 rounded-lg bg-violet-50/40 p-4">
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                Script source
              </p>
              {!wantsVideo && (
                <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
                  Select <strong>Landscape</strong> or <strong>Portrait</strong> above to unlock PDF
                  upload and HeyGen avatar video.
                </p>
              )}
              {wantsVideo && !isHeyGen && (
                <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-3">
                  Set <strong>Video Provider</strong> to <strong>HeyGen</strong> above to use PDF
                  script upload.
                </p>
              )}
              <p className="text-xs text-mid mb-3">
                <strong>Manual</strong> — fill campaign fields and use AI for script.{' '}
                <strong>PDF</strong> — upload a PDF; only avatar + voice are chosen here.{' '}
                <strong>Paste prompt &amp; image</strong> — supply your own script and reference image.{' '}
                <strong>Website URL</strong> — paste your webpage and AI writes the script using the best framework for your chosen duration.
              </p>
              <div className="flex flex-wrap gap-2 mb-3">
                <ChipToggle
                  label="Manual campaign & AI"
                  selected={scriptBuildMode === 'manual'}
                  disabled={!wantsVideo}
                  onToggle={() => setScriptBuildMode('manual')}
                />
                <ChipToggle
                  label="Upload PDF script"
                  selected={scriptBuildMode === 'pdf'}
                  disabled={!wantsVideo}
                  onToggle={() => {
                    setScriptBuildMode('pdf')
                    if (!isHeyGen) {
                      setGenSettings((prev) => ({ ...prev, videoModel: 'heygen-video-agent' }))
                    }
                  }}
                />
                <ChipToggle
                  label="Paste prompt & image"
                  selected={scriptBuildMode === 'custom'}
                  disabled={!wantsVideo}
                  onToggle={() => setScriptBuildMode('custom')}
                />
                <ChipToggle
                  label="Website URL → AI script"
                  selected={scriptBuildMode === 'website'}
                  disabled={!wantsVideo}
                  onToggle={() => setScriptBuildMode('website')}
                />
              </div>
              {scriptBuildMode === 'pdf' && wantsVideo && !isHeyGen && (
                <p className="text-[11px] text-mid mb-2">Switching provider to HeyGen for PDF mode…</p>
              )}
              {isPdfScriptMode && (
                <div className="rounded-lg border-2 border-violet-300 bg-white p-3 space-y-2">
                  <label className="block text-xs font-bold text-navy uppercase tracking-wide">
                    Upload script PDF
                  </label>
                  <input
                    type="file"
                    accept=".pdf,application/pdf"
                    className="text-sm w-full file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-teal file:text-white"
                    onChange={(e) => setPdfFile(e.target.files?.[0] ?? null)}
                  />
                  {pdfFile ? (
                    <p className="text-xs text-navy">
                      Selected: <strong>{pdfFile.name}</strong>
                    </p>
                  ) : (
                    <p className="text-xs text-amber-700">Choose a PDF before Create &amp; Generate.</p>
                  )}
                  <p className="text-[11px] text-mid">
                    Full script text is extracted when you save (max ~10 MB). You only pick avatar,
                    voice, and duration below — the video follows the PDF.
                  </p>
                </div>
              )}
              {isCustomScriptMode && (
                <div className="rounded-lg border-2 border-violet-300 bg-white p-3 space-y-3">
                  <div>
                    <label
                      htmlFor="custom-video-prompt"
                      className="block text-xs font-bold text-navy uppercase tracking-wide mb-1.5"
                    >
                      Video prompt / script
                    </label>
                    <TextArea
                      id="custom-video-prompt"
                      rows={5}
                      placeholder="Paste your full video script, scene directions, or creative prompt here…"
                      value={customPrompt}
                      onChange={(e) => setCustomPrompt(e.target.value)}
                    />
                  </div>
                  <div>
                    <label className="block text-xs font-bold text-navy uppercase tracking-wide mb-1.5">
                      Reference image
                    </label>
                    <div
                      tabIndex={0}
                      onPaste={handleReferenceImagePaste}
                      className="rounded-xl border-2 border-dashed border-border bg-light p-4 focus:outline-none focus:border-accent/50"
                    >
                      {referenceImagePreview ? (
                        <div className="space-y-2">
                          <img
                            src={referenceImagePreview}
                            alt="Reference preview"
                            className="max-h-40 rounded-lg object-contain mx-auto"
                          />
                          <p className="text-xs text-navy text-center">
                            <strong>{referenceImageFile?.name}</strong>
                          </p>
                          <button
                            type="button"
                            className="text-xs text-mid hover:text-charcoal underline block mx-auto"
                            onClick={() => applyReferenceImageFile(null)}
                          >
                            Remove image
                          </button>
                        </div>
                      ) : (
                        <div className="text-center space-y-2">
                          <p className="text-xs text-mid">
                            Upload or <strong>paste</strong> an image (Ctrl+V) to use as the video seed.
                          </p>
                          <input
                            type="file"
                            accept="image/png,image/jpeg,image/webp"
                            className="text-sm w-full file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-teal file:text-white"
                            onChange={(e) => applyReferenceImageFile(e.target.files?.[0] ?? null)}
                          />
                        </div>
                      )}
                    </div>
                    {!referenceImageFile && (
                      <p className="text-xs text-amber-700 mt-2">
                        Add a reference image before Create &amp; Generate.
                      </p>
                    )}
                  </div>
                  <p className="text-[11px] text-mid">
                    Your prompt drives the spoken script and scene plan. The reference image is used
                    as the seed still for video generation. Pick avatar, voice, and duration below.
                  </p>
                </div>
              )}
              {isWebsiteScriptMode && (
                <div className="rounded-lg border-2 border-violet-300 bg-white p-3 space-y-3">
                  <div>
                    <label
                      htmlFor="website-url-input"
                      className="block text-xs font-bold text-navy uppercase tracking-wide mb-1.5"
                    >
                      Website page URL
                    </label>
                    <input
                      id="website-url-input"
                      type="url"
                      className="w-full rounded-lg border border-border px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
                      placeholder="https://yourwebsite.com/service-page"
                      value={websiteUrl}
                      onChange={(e) => setWebsiteUrl(e.target.value)}
                    />
                    {!websiteUrl.trim() && (
                      <p className="text-xs text-amber-700 mt-1.5">
                        Paste your page URL — AI will read it and write the script.
                      </p>
                    )}
                  </div>
                  <div className="rounded-lg bg-violet-50 border border-violet-200 px-3 py-2 space-y-1">
                    <p className="text-[11px] font-semibold text-violet-800">Framework auto-selected by duration:</p>
                    <p className="text-[11px] text-violet-700">
                      {genSettings.videoDurationSeconds <= 20 && '⚡ Hook + CTA — punchy single-message ad'}
                      {genSettings.videoDurationSeconds > 20 && genSettings.videoDurationSeconds <= 45 && '▶ Hook → Benefit → CTA'}
                      {genSettings.videoDurationSeconds > 45 && genSettings.videoDurationSeconds <= 90 && '▶ Problem → Solution → CTA'}
                      {genSettings.videoDurationSeconds > 90 && genSettings.videoDurationSeconds <= 150 && '▶ Problem → Agitate → Solution → CTA'}
                      {genSettings.videoDurationSeconds > 150 && '▶ Story Arc — Before / Struggle / Discovery / Results / CTA'}
                    </p>
                    <p className="text-[10px] text-violet-600">Change duration above to switch framework.</p>
                  </div>
                  <p className="text-[11px] text-mid">
                    The AI fetches your page, extracts key content, and writes a fully timed script.
                    Pick avatar, voice, and duration above — the script is generated in Step 8.
                  </p>
                </div>
              )}
            </div>
            )}

          </BriefSection>

          {!hideCampaignDetailSteps && mediaType === 'video' && (
            <>
          <BriefSection title="Audience & Tone" step="3">
            <Input
              label="Target Audience"
              placeholder="e.g. Adults 28–55 interested in cosmetic dentistry"
              error={errors.audience_type?.message}
              {...register('audience_type')}
            />
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
              <Input label="Geography" placeholder="e.g. Perth WA, Sydney NSW" error={errors.geography?.message} {...register('geography')} />
              <Input label="Age Range" placeholder="28 – 55" error={errors.age_range?.message} {...register('age_range')} />
              <Input label="Languages" placeholder="English" error={errors.languages?.message} {...register('languages')} />
            </div>
            <Input
              label="Tone of Voice"
              placeholder="e.g. Friendly & Trustworthy, Professional"
              error={errors.ad_copy_tone?.message}
              {...register('ad_copy_tone')}
            />
          </BriefSection>

          <BriefSection title="Platform & Placement" step="4">
            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">Platforms / Placements</p>
              <ChipToggleGroup
                options={placementOptions}
                selected={selectedPlacements ?? []}
                onChange={(next) => setValue('placements', next, { shouldValidate: true })}
                disabled={!catalog}
              />
              {errors.placements && <p className="mt-1 text-xs text-red-500">{errors.placements.message}</p>}
            </div>
            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">Hook Frameworks (optional)</p>
              <ChipToggleGroup
                options={hookFrameworkOptions}
                selected={selectedFrameworks ?? []}
                onChange={(next) => setValue('hook_frameworks', next)}
              />
            </div>
          </BriefSection>

          </>
          )}

          {!hideCampaignDetailSteps && mediaType === 'video' && (
          <BriefSection title="Script & Content" step="5">
            <Input
              label="Hero Product (optional)"
              placeholder="e.g. General & Cosmetic Dentistry"
              error={errors.product_name?.message}
              {...register('product_name')}
            />
            <Input
              label="Offer / Key Message (optional)"
              placeholder="e.g. Free consultation for new patients"
              error={errors.offer?.message}
              {...register('offer')}
            />
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                <label
                  htmlFor="script-brief-notes"
                  className="block text-xs font-bold text-navy uppercase tracking-wide"
                >
                  {wantsVideo && isHeyGen ? 'Creative brief (optional talking points)' : 'Script / Brief Notes (optional)'}
                </label>
                <Button
                  type="button"
                  size="sm"
                  variant="primary"
                  isLoading={generatingNotes}
                  onClick={() => void handleGenerateScriptNotes()}
                >
                  Generate script using ICP
                </Button>
              </div>
              <TextArea
                id="script-brief-notes"
                rows={4}
                placeholder={
                  wantsVideo && isHeyGen
                    ? 'Writer directions: themes, tone, what to mention — not the words the avatar speaks aloud.'
                    : 'What should the ad say? Paste script ideas or talking points — or click Generate script using ICP above.'
                }
                error={errors.notes?.message}
                {...register('notes')}
              />
              <p className="mt-1 text-[11px] text-mid">
                {wantsVideo && isHeyGen ? (
                  <>
                    Optional — skip if you paste your full script in <strong>step 8</strong>. Otherwise use{' '}
                    <strong>Generate script using ICP</strong> here, then <strong>Approve</strong> in step 8.
                  </>
                ) : (
                  'Optional. Builds an ICP from audience + offer when those fields are filled.'
                )}
              </p>
            </div>
          </BriefSection>
          )}

          {mediaType === 'image' && (
            <BriefSection title="Image Variants" step="5">
              <p className="text-[11px] text-mid -mt-1">
                Static: each ad has hook, on-image lines, and a CTA. Carousel: one campaign hook/headline/CTA,
                then each card is a visual + short headline only.
              </p>
              <ImageVariantSlotsPanel
                slots={imageVariantSlots}
                onChange={setImageVariantSlots}
                generatingIndex={generatingSlotIndex}
                generatingAll={generatingAllSlots}
                onGenerateSlot={(i) => void handleGenerateImageSlot(i)}
                onGenerateAll={() => void handleGenerateAllImageSlots()}
                campaignOffer={imageCampaignOffer}
                onCampaignOfferChange={setImageCampaignOffer}
                campaignHook={imageCampaignHook}
                campaignHeadline={imageCampaignHeadline}
                campaignCta={formValues.cta ?? ''}
                onCampaignHookChange={setImageCampaignHook}
                onCampaignHeadlineChange={setImageCampaignHeadline}
                onCampaignCtaChange={(v) => setValue('cta', v, { shouldValidate: true })}
                formats={selectedFormats ?? []}
                angleOptions={hookFrameworkOptions}
                exportContext={{
                  campaignName: campaignLabel(formValues.title ?? '', formValues.niche),
                  brandName: selectedBrand?.name ?? '',
                  objectiveId: formValues.objective_id ?? '',
                  aspectRatio: imageRatioCustom.trim() || imageRatio,
                  icpText: imageIcpText ?? undefined,
                }}
                catalogProducts={resolvedBrandFacts?.products ?? []}
                productFocus={imageProductFocus}
                onProductFocusChange={setImageProductFocus}
                promptLlmModel={genSettings.promptLlmModel}
                onPromptLlmModelChange={(value) =>
                  setGenSettings((prev) => ({ ...prev, promptLlmModel: value }))
                }
                promptLlmOptions={promptLlmSelect.options}
                promptLlmGroups={promptLlmSelect.groups}
              />
            </BriefSection>
          )}

          {wantsVideo && isHeyGen && (
            <HeyGenProductionPipeline
              pdfScriptOnly={isPdfScriptMode || isCustomScriptMode}
              durationSeconds={genSettings.videoDurationSeconds}
              avatarLabel={avatarLabel}
              voiceLabel={voiceLabel}
              avatarOptions={catalog?.heygen_avatar_options ?? []}
              avatarFeatured={catalog?.heygen_avatar_featured}
              heygenCatalog={catalog ?? undefined}
              voiceOptions={catalog?.heygen_voice_options ?? []}
              avatarId={genSettings.heygenAvatarId}
              voiceId={genSettings.heygenVoiceId}
              onAvatarChange={(id) => setGenSettings({ ...genSettings, heygenAvatarId: id })}
              onVoiceChange={(id) => setGenSettings({ ...genSettings, heygenVoiceId: id })}
              onDurationChange={(seconds) =>
                setGenSettings({ ...genSettings, videoDurationSeconds: seconds })
              }
              settings={heygenSettings}
              onSettingsChange={setHeygenSettings}
              durationOptions={durationOptions}
              campaignContext={{
                productName: formValues.product_name ?? '',
                offer: formValues.offer ?? '',
                brandName: selectedBrand?.name ?? '',
                targetAudience: [
                  formValues.audience_type,
                  formValues.geography,
                  formValues.age_range,
                ]
                  .filter(Boolean)
                  .join(' · '),
                adCopyTone: formValues.ad_copy_tone ?? '',
                cta: formValues.cta ?? '',
                notes: formValues.notes ?? '',
                avatarScript: approvedAvatarScript ?? undefined,
                forbiddenWords: selectedBrand?.forbidden_words,
              }}
              scriptContext={{
                briefNotes: formValues.notes ?? '',
                productName: formValues.product_name ?? '',
                offer: formValues.offer ?? '',
                brandName: selectedBrand?.name ?? '',
                targetAudience: [
                  formValues.audience_type,
                  formValues.geography,
                  formValues.age_range,
                ]
                  .filter(Boolean)
                  .join(' · '),
                adCopyTone: formValues.ad_copy_tone ?? '',
                cta: formValues.cta ?? '',
                targetSeconds: genSettings.videoDurationSeconds,
                avatarLabel,
                voiceLabel,
                forbiddenWords: selectedBrand?.forbidden_words,
                websiteUrl: isWebsiteScriptMode ? websiteUrl : undefined,
              }}
              approvedScript={approvedAvatarScript}
              onApprovedScript={setApprovedAvatarScript}
              onExportSnapshotChange={setAvatarExportSnapshot}
              onAfterScriptApproved={() => {
                requestAnimationFrame(() => {
                  createVideoButtonRef.current?.scrollIntoView({
                    behavior: 'smooth',
                    block: 'center',
                  })
                })
              }}
              exportFileName={formValues.title}
            />
          )}

          <BriefSection title="Call to Action" step="7">
            {mediaType === 'image' ? (
              <>
                <Input
                  label="Default CTA hint (optional)"
                  placeholder="Optional — leave blank so AI picks a CTA per variant"
                  error={errors.cta?.message}
                  {...register('cta')}
                />
                <p className="mt-1 text-[11px] text-mid">
                  {(selectedFormats ?? []).includes('carousel')
                    ? 'Carousel: this CTA is the ad action and is burned onto the LAST swipe card only. Earlier cards stay visual-only.'
                    : 'For static image ads, each variant has its own CTA on image in step 5. This field is a shared hint.'}
                </p>
              </>
            ) : (
              <Input
                label="CTA Text"
                placeholder="e.g. Book Appointment, Shop Now, Learn More"
                error={errors.cta?.message}
                {...register('cta')}
              />
            )}
          </BriefSection>

          {/* ── Model Selector — bottom of form after all inputs ─────── */}
          <BriefSection title="AI Models" step="9">
            <p className="text-xs text-mid -mt-1 mb-1">
              {mediaType === 'image' ? (
                <>
                  Copy model is set here. You&apos;ll choose the <strong>image model</strong>{' '}
                  yourself on the brief page right before you generate variants.
                </>
              ) : (
                <>
                  Once you&apos;ve filled your campaign details above, click{' '}
                  <strong>Analyse &amp; suggest models</strong> to let the AI pick the best
                  image and video models — or choose manually from the dropdowns.
                </>
              )}
            </p>
            <ModelSelectorBlock
              catalog={catalog ?? undefined}
              wantsVideo={wantsVideo}
              hideImageModel={mediaType === 'image'}
              genSettings={genSettings}
              setGenSettings={setGenSettings}
              imageModelSelect={imageModelSelect}
              videoModelSelect={videoModelSelect}
              getSuggestionInputs={() => ({
                campaign_name: campaignLabel(formValues.title ?? '', formValues.niche),
                objective: formValues.objective_id
                  ? (catalog?.objectives.find(o => o.id === formValues.objective_id)?.label ?? formValues.objective_id)
                  : '',
                formats: selectedFormats ?? [],
                target_audience: [formValues.audience_type, formValues.geography, formValues.age_range]
                  .filter(Boolean).join(' · '),
                offer: formValues.offer ?? '',
                product_name: formValues.product_name ?? '',
                ad_copy_tone: formValues.ad_copy_tone ?? '',
                cta: formValues.cta ?? '',
                duration_seconds: genSettings.videoDurationSeconds,
                brand_name: selectedBrand?.name ?? '',
              })}
            />
          </BriefSection>

          {mediaType === 'video' && (
            <StrategyPreviewPanel
              canBuild={Boolean(catalog && hasBrands)}
              onPreviewChange={setStrategyPreview}
              getInputs={() => ({
                campaign_name: campaignLabel(formValues.title ?? '', formValues.niche),
                brand_name: selectedBrand?.name ?? '',
                product_name: formValues.product_name ?? '',
                offer: formValues.offer ?? '',
                target_audience: [
                  formValues.audience_type,
                  formValues.geography,
                  formValues.age_range,
                ]
                  .filter(Boolean)
                  .join(' · '),
                ad_copy_tone: formValues.ad_copy_tone ?? '',
                cta: formValues.cta ?? '',
                target_seconds: genSettings.videoDurationSeconds,
                hook_frameworks: selectedFrameworks ?? [],
                objective: formValues.objective_id
                  ? (catalog?.objectives.find((o) => o.id === formValues.objective_id)?.label ??
                    formValues.objective_id)
                  : '',
                placements: selectedPlacements ?? [],
                formats: selectedFormats ?? [],
                website_url: isWebsiteScriptMode ? websiteUrl : undefined,
              })}
            />
          )}

          <div className="flex flex-col gap-2 pt-2">
            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={handleDownloadBriefExcel}
            >
              {mediaType === 'image'
                ? 'Download brief Excel (Image + ICP + Variants)'
                : 'Download brief Excel (Steps 1–9 + script)'}
            </Button>
            {needsApprovedScript && (
              <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                Scroll to <strong>step 8</strong>, click <strong>Generate spoken script</strong>, then{' '}
                <strong>Approve</strong> before creating the video.
              </p>
            )}
            {wantsVideo && isHeyGen && approvedAvatarScript && !needsApprovedScript && (
              <p className="text-xs text-teal-900 bg-teal-50 border border-teal-300 rounded-lg px-3 py-2 font-medium">
                ✓ Script approved — click the button below to start HeyGen video generation.
              </p>
            )}
            <Button type="button" variant="outline" onClick={() => router.push('/briefs')}>
              Back
            </Button>
            <div ref={createVideoButtonRef}>
              <Button
                type="submit"
                variant="primary"
                isLoading={isSubmitting}
                disabled={submitBlocked}
                className="w-full"
                title={
                  needsApprovedScript
                    ? 'Generate and approve your spoken script in step 8 first'
                    : undefined
                }
              >
                {submitLabel}
              </Button>
            </div>
          </div>
        </div>
      </form>
    </div>
  )
}
