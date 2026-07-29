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
import AdAngleSelector from '@/components/brief/AdAngleSelector'
import ImageVariantSlotsPanel from '@/components/brief/ImageVariantSlotsPanel'
import ModelSelectorBlock from '@/components/brief/ModelSelectorBlock'
import StrategyPreviewPanel from '@/components/brief/StrategyPreviewPanel'
import HeyGenProductionPipeline from '@/components/brief/HeyGenProductionPipeline'
import {
  emptyImageVariantSlot,
  resizeImageVariantSlots,
  type ImageVariantSlot,
} from '@/lib/imageUseCases'
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
import { API_CACHE_TTL, clearApiCache, clearBriefListCaches } from '@/lib/apiCache'
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
import type { AdFormat, CatalogOption, PerformanceStatsContext, StrategyPreviewResult, WebsiteBrandFetchResult } from '@/types'

const schema = z
  .object({
    brand_id: z.string().optional(),
    title: z.string().min(2, 'Industry required'),
    niche: z.string().optional(),
    brand_source: z.enum(['brand', 'website']),
    website_url: z.string().optional(),
    objective_id: z.string().min(1, 'Select an objective'),
    target_variant_count: z.coerce.number().int().min(1).max(20),
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

function websiteHost(url: string): string {
  try {
    const raw = url.trim()
    const u = new URL(raw.startsWith('http') ? raw : `https://${raw}`)
    return u.hostname.replace(/^www\./i, '').toLowerCase()
  } catch {
    return url.trim().toLowerCase()
  }
}

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

export default function BriefComposer({ defaultBrandId }: BriefComposerProps) {
  const router = useRouter()
  const { data: brands, refetch: refetchBrands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands',
    ttlMs: API_CACHE_TTL.brands,
  })
  const { data: catalog } = useApi(() => generationApi.getCatalog(false), [], {
    cacheKey: 'generation/catalog-v7',
    ttlMs: API_CACHE_TTL.catalog,
  })

  const [mediaType, setMediaType] = useState<'image' | 'video'>('image')
  const [imageVariantSlots, setImageVariantSlots] = useState<ImageVariantSlot[]>([
    emptyImageVariantSlot(),
    emptyImageVariantSlot(),
  ])
  const [generatingSlotIndex, setGeneratingSlotIndex] = useState<number | null>(null)
  const [generatingAllSlots, setGeneratingAllSlots] = useState(false)
  const [imageIcpText, setImageIcpText] = useState<string | null>(null)
  const [imageCampaignOffer, setImageCampaignOffer] = useState('')
  const [suggestingAngles, setSuggestingAngles] = useState(false)
  const [angleSuggestionReason, setAngleSuggestionReason] = useState<string | null>(null)
  const anglesAutoSuggestedRef = useRef(false)
  const [websiteBrand, setWebsiteBrand] = useState<WebsiteBrandFetchResult | null>(null)
  const [fetchingWebsiteBrand, setFetchingWebsiteBrand] = useState(false)
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
  })
  const [heygenSettings, setHeygenSettings] = useState<HeyGenVideoSettings>(defaultHeyGenSettings())
  const [approvedAvatarScript, setApprovedAvatarScript] = useState<string | null>(null)
  const createVideoButtonRef = useRef<HTMLDivElement>(null)
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
      brand_id: defaultBrandId ?? '',
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
    }))
  }, [catalog, setValue, watch])

  useEffect(() => {
    if (defaultBrandId) setValue('brand_id', defaultBrandId)
  }, [defaultBrandId, setValue])

  const selectedPlacements = watch('placements')
  const selectedFormats = watch('formats')
  const selectedFrameworks = watch('hook_frameworks')
  const targetVariantCount = watch('target_variant_count')
  const objectiveId = watch('objective_id')
  const brandSource = watch('brand_source')
  const websiteUrlField = watch('website_url')

  useEffect(() => {
    if (mediaType !== 'image') return
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

  const variantAngleAssignments = useMemo(
    () =>
      assignAnglesToVariants(
        selectedFrameworks ?? [],
        Number(targetVariantCount) || 1,
        objectiveId
      ),
    [selectedFrameworks, targetVariantCount, objectiveId]
  )

  const brandOptions = (brands ?? []).map((brand) => ({ value: brand.id, label: brand.name }))
  const hasBrands = brandOptions.length > 0
  const selectedBrand = (brands ?? []).find((brand) => brand.id === watch('brand_id'))

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
            fonts: kit.fonts || {},
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
          })
        } catch {
          /* kit optional */
        }
        toast.success(`Saved to Brand Kit: ${savedBrand.name}`)
      }

      clearApiCache('brands')
      await refetchBrands({ background: true })
      setValue('brand_source', 'brand', { shouldValidate: true })
      setValue('brand_id', savedBrand.id, { shouldValidate: true })
      setValue('website_url', result.source_url || url)

      if (result.warning) toast(result.warning, { icon: '⚠️' })
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not fetch brand from website')
    } finally {
      setFetchingWebsiteBrand(false)
    }
  }

  useEffect(() => {
    if (mediaType !== 'image') return
    const campaignName = campaignLabel(watch('title') ?? '', watch('niche'))
    if (
      campaignName.length < 2 ||
      (selectedFrameworks?.length ?? 0) > 0 ||
      anglesAutoSuggestedRef.current
    ) {
      return
    }
    const timer = window.setTimeout(() => {
      anglesAutoSuggestedRef.current = true
      void handleSuggestAdAngles(true)
    }, 1500)
    return () => window.clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [watch('title'), watch('niche'), mediaType, selectedFrameworks?.length, objectiveId])

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

  const submitLabel = useMemo(() => {
    if (wantsVideo && wantsImageOnly) return 'Create & Generate Video'
    if (wantsVideo) return 'Create & Generate Video'
    if (wantsImageOnly) return 'Create brief →'
    return 'Create brief →'
  }, [wantsVideo, wantsImageOnly])

  // When user picks Image → force static/carousel formats; when Video → keep what they had or default to reel
  useEffect(() => {
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
      const plan = await generationApi.previewIcpImagePlan({
        campaign_name: campaignName,
        brand_name: selectedBrand?.name ?? websiteBrand?.brand_name ?? '',
        industry:
          (d.title ?? '').trim() ||
          selectedBrand?.industry ||
          websiteBrand?.industry ||
          '',
        objective_id: d.objective_id ?? '',
        cta: d.cta ?? '',
        offer: imageCampaignOffer.trim() || slot.offer.trim() || undefined,
        image_aspect_ratio: imageRatioCustom.trim() || imageRatio,
        hook_frameworks: slotAngle ? [slotAngle] : (d.hook_frameworks ?? []),
        variant_count: 1,
        existing_hooks: siblingHooks,
        existing_prompts: siblingPrompts,
      })
      const variant = plan.variants[0]
      if (!variant) {
        toast.error('No variant returned — try again')
        return
      }
      if (plan.icp_text?.trim()) {
        setImageIcpText(plan.icp_text.trim())
      }
      const generatedAt = new Date().toISOString()
      setImageVariantSlots((prev) =>
        prev.map((s, i) =>
          i === index
            ? {
                ...s,
                use_cases: variant.use_cases?.length ? variant.use_cases : s.use_cases,
                hook: variant.hook || s.hook,
                message: variant.message || s.message,
                cta: variant.cta || s.cta,
                offer: variant.offer || imageCampaignOffer.trim() || s.offer,
                prompt: variant.prompt || s.prompt,
                reasoning: variant.reasoning || '',
                ad_angle: variant.ad_angle || slotAngle || '',
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
    setGeneratingAllSlots(true)
    try {
      const plan = await generationApi.previewIcpImagePlan({
        campaign_name: campaignName,
        brand_name: selectedBrand?.name ?? websiteBrand?.brand_name ?? '',
        industry:
          (d.title ?? '').trim() ||
          selectedBrand?.industry ||
          websiteBrand?.industry ||
          '',
        objective_id: d.objective_id ?? '',
        cta: d.cta ?? '',
        offer: imageCampaignOffer.trim() || undefined,
        image_aspect_ratio: imageRatioCustom.trim() || imageRatio,
        hook_frameworks: d.hook_frameworks ?? [],
        variant_count: imageVariantSlots.length,
      })
      if (plan.icp_text?.trim()) {
        setImageIcpText(plan.icp_text.trim())
      }
      const generatedAt = new Date().toISOString()
      setImageVariantSlots((prev) =>
        prev.map((s, i) => {
          const variant = plan.variants[i]
          if (!variant) return s
          return {
            ...s,
            use_cases: variant.use_cases?.length ? variant.use_cases : s.use_cases,
            hook: variant.hook || s.hook,
            message: variant.message || s.message,
            cta: variant.cta || s.cta,
            offer: variant.offer || imageCampaignOffer.trim() || s.offer,
            prompt: variant.prompt || s.prompt,
            reasoning: variant.reasoning || '',
            ad_angle: variant.ad_angle || variantAngleAssignments[i] || '',
            generated_at: generatedAt,
          }
        })
      )
      toast.success(
        `${plan.variants.length} image variant${plan.variants.length !== 1 ? 's' : ''} filled from ICP — edit hook, message, CTA, and prompt as needed`
      )
    } catch {
      toast.error('Could not generate plans — check OPENROUTER_API_KEY and restart backend')
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
    const isAlternateMode = isPdfMode || isCustomMode

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
          cta_text:
            (d.cta ?? '').trim() ||
            imageVariantSlots.map((s) => s.cta.trim()).find(Boolean) ||
            '',
          tone_text: (d.ad_copy_tone ?? '').trim(),
          copy_model: genSettings.copyModel,
          ...(mediaType !== 'image' && genSettings.imageModel
            ? { image_model: genSettings.imageModel }
            : {}),
          media_type: mediaType,
          ...(mediaType === 'image'
            ? {
                image_aspect_ratio: imageRatioCustom.trim() || imageRatio,
                image_variants: imageVariantSlots.map((s, i) => ({
                  use_cases: s.use_cases,
                  hook: s.hook.trim(),
                  message: s.message.trim(),
                  cta: s.cta.trim(),
                  offer: s.offer.trim(),
                  prompt: s.prompt.trim(),
                  reasoning: s.reasoning.trim() || undefined,
                  ad_angle: s.ad_angle || variantAngleAssignments[i] || undefined,
                  generated_at: s.generated_at ?? undefined,
                })),
                ...(imageIcpText?.trim() ? { image_icp_text: imageIcpText.trim() } : {}),
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

      // Land on the new brief (Generate video is on that page). No list search / refresh needed.
      router.push(`/briefs/${brief.id}?autogenerate=1`)
    } catch (err: unknown) {
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
            {mediaType === 'image' ? 'Image' : 'Video'}
          </span>
        </div>
        <Button type="submit" form="brief-form" variant="outline" size="sm" disabled={isSubmitting}>
          Save Brief
        </Button>
      </header>

      {/* Image / Video tabs */}
      <div className="sticky top-[65px] z-10 border-b border-border bg-white/90 backdrop-blur-md">
        <div className="w-full max-w-[1600px] mx-auto px-6 md:px-8 flex gap-1">
          {([
            { id: 'image' as const, label: 'Image', hint: 'Static & carousel ads' },
            { id: 'video' as const, label: 'Video', hint: 'Portrait & landscape' },
          ]).map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setMediaType(tab.id)}
              className={`relative px-5 py-3 text-sm font-semibold transition-colors ${
                mediaType === tab.id
                  ? 'text-charcoal'
                  : 'text-mid hover:text-charcoal'
              }`}
            >
              {tab.label}
              <span className="hidden sm:inline text-mid font-normal text-[11px] ml-1.5">
                · {tab.hint}
              </span>
              {mediaType === tab.id && (
                <span className="absolute left-2 right-2 bottom-0 h-0.5 rounded-full bg-accent" />
              )}
            </button>
          ))}
        </div>
      </div>

      <form
        id="brief-form"
        onSubmit={handleSubmit(onSubmit, onInvalid)}
        className="w-full max-w-[1600px] mx-auto p-6 md:p-8 space-y-4"
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
            <Input
              label="Industry"
              placeholder="e.g. Dental, Legal Services, Digital Marketing"
              error={errors.title?.message}
              {...register('title')}
            />
            <Input
              label="Niche"
              placeholder="e.g. New patient acquisition, Meta ads for SMBs"
              error={errors.niche?.message}
              {...register('niche')}
            />

            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                Brand source
              </p>
              <div className="flex gap-2 mb-3">
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
                <Select
                  label="Brand"
                  options={brandOptions}
                  placeholder={hasBrands ? 'Select brand' : 'No brands'}
                  disabled={!hasBrands}
                  error={errors.brand_id?.message}
                  {...register('brand_id')}
                />
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
                    Fetches colours &amp; logo with Firecrawl, then <strong>saves into Brand Kit</strong> so
                    you can reuse it next time without fetching again. Industry and niche stay yours to type
                    above.
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
              max={20}
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
                  Image tab: <strong>Static</strong> and <strong>Carousel</strong>. Switch to the{' '}
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
                onChange={(next) => setValue('formats', next, { shouldValidate: true })}
                disabled={!catalog}
              />
              {errors.formats && <p className="mt-1 text-xs text-red-500">{errors.formats.message}</p>}
            </div>

            {/* ── Ad style / marketing approach (image mode) ── */}
            {mediaType === 'image' && (
              <div>
                <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                  Ad angles
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
            )}

            {/* ── Image ratio picker (image mode only) ── */}
            {mediaType === 'image' && (
              <div>
                <p className="text-xs font-bold text-navy uppercase tracking-wide mb-3">Image ratio</p>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 mb-3">
                  {[
                    { id: '1:1',    label: '1:1',      desc: 'Instagram · Facebook feed' },
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
              <Input label="Geography" placeholder="United States" error={errors.geography?.message} {...register('geography')} />
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
                ICP-driven plans from your campaign name — unique use case, hook, headline, CTA, and prompt per variant.
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
                angleOptions={hookFrameworkOptions}
                exportContext={{
                  campaignName: campaignLabel(formValues.title ?? '', formValues.niche),
                  brandName: selectedBrand?.name ?? '',
                  objectiveId: formValues.objective_id ?? '',
                  aspectRatio: imageRatioCustom.trim() || imageRatio,
                  icpText: imageIcpText ?? undefined,
                }}
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
                  For image ads, each variant has its own <strong>CTA on image</strong> in step 5.
                  Generate AI for all fills those CTAs. This field is only a shared hint.
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
