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
import ModelSelectorBlock from '@/components/brief/ModelSelectorBlock'
import StrategyPreviewPanel from '@/components/brief/StrategyPreviewPanel'
import HeyGenProductionPipeline from '@/components/brief/HeyGenProductionPipeline'
import { defaultHeyGenSettings } from '@/components/brief/HeyGenVideoSettingsCard'
import { findVespriAvatar, HEYGEN_VESPRI_AVATAR_ID } from '@/lib/heygenAvatars'
import { heygenSettingsForApi, type HeyGenVideoSettings } from '@/lib/heygenOptions'
import { VIDEO_DURATION_OPTIONS, type BriefGenerationSettings } from '@/components/brief/BriefGenerationPanel'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
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
import type { AdFormat, CatalogOption, PerformanceStatsContext, StrategyPreviewResult } from '@/types'

const schema = z.object({
  brand_id: z.string().min(1, 'Select a brand'),
  title: z.string().min(3, 'Campaign name required'),
  objective_id: z.string().min(1, 'Select an objective'),
  target_variant_count: z.coerce.number().int().min(1).max(20),
  offer: z.string().optional(),
  product_name: z.string().optional(),
  cta: z.string().min(2, 'Enter a call to action'),
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

type FormData = z.infer<typeof schema>

interface BriefComposerProps {
  defaultBrandId?: string
}

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
  const { data: brands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands',
    ttlMs: API_CACHE_TTL.brands,
  })
  const { data: catalog } = useApi(() => generationApi.getCatalog(true), [], {
    cacheKey: 'generation/catalog-v4',
    ttlMs: API_CACHE_TTL.catalog,
  })

  const [genSettings, setGenSettings] = useState<BriefGenerationSettings>({
    copyModel: 'claude',
    imageModel: 'nano-banana-2',
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
  }>({
    icpText: null,
    generatedFullScript: null,
    spokenScript: null,
    statsImageUrl: null,
    statsImageUrls: [],
    performanceStats: null,
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
    if (catalog.objectives[0] && !watch('objective_id')) {
      setValue('objective_id', catalog.objectives[0].id)
    }
    setGenSettings((prev) => ({
      ...prev,
      copyModel: catalog.copy_models[0]?.id ?? prev.copyModel,
      imageModel: catalog.image_models[0]?.id ?? prev.imageModel,
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

  const brandOptions = (brands ?? []).map((brand) => ({ value: brand.id, label: brand.name }))
  const hasBrands = brandOptions.length > 0
  const selectedBrand = (brands ?? []).find((brand) => brand.id === watch('brand_id'))
  const wantsVideo = (selectedFormats ?? []).some(isVideoFormat)
  const wantsImageOnly =
    (selectedFormats ?? []).length > 0 &&
    (selectedFormats ?? []).every((f) => f === 'static' || f === 'carousel')
  const isHeyGen = wantsVideo && genSettings.videoModel.toLowerCase().startsWith('heygen')
  const isHiggsfieldVideo =
    wantsVideo && genSettings.videoModel.toLowerCase().startsWith('hf-')
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
    if (wantsVideo && wantsImageOnly) return 'Create brief →'
    if (wantsVideo) return 'Create brief →'
    if (wantsImageOnly) return 'Create brief →'
    return 'Create brief →'
  }, [wantsVideo, wantsImageOnly])

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

  const estimate = useMemo(() => {
    const count = Number(targetVariantCount) || 0
    const perVariant = catalog?.estimate.cost_per_variant_usd ?? 0
    const seconds = catalog?.estimate.seconds_per_variant ?? 0
    return {
      cost: count * perVariant,
      minutes: Math.max(1, Math.round((count * seconds) / 60)),
    }
  }, [catalog, targetVariantCount])

  const formValues = watch()

  const checklist = useMemo(() => {
    const d = formValues
    return [
      { label: 'Campaign & brand', ok: Boolean(d.title && d.brand_id) },
      { label: 'Objective selected', ok: Boolean(d.objective_id) },
      {
        label: wantsVideo ? 'Landscape or Portrait chosen' : 'Creative format chosen',
        ok: (d.formats ?? []).length > 0,
      },
      {
        label: 'Audience defined',
        ok: hideCampaignDetailSteps || Boolean(d.audience_type && d.geography),
      },
      {
        label: 'CTA & tone set',
        ok: hideCampaignDetailSteps || Boolean(d.cta && d.ad_copy_tone),
      },
      {
        label: 'HeyGen avatar (if video)',
        ok: !wantsVideo || !isHeyGen || Boolean(genSettings.heygenAvatarId),
      },
      {
        label: isPdfScriptMode
          ? 'PDF script file chosen'
          : isCustomScriptMode
            ? 'Custom prompt & image ready'
            : isWebsiteScriptMode
              ? 'Website URL & script approved'
              : 'Avatar script approved',
        ok:
          !wantsVideo ||
          (isCustomScriptMode
            ? Boolean(customPrompt.trim() && referenceImageFile)
            : isPdfScriptMode
              ? Boolean(pdfFile)
              : isWebsiteScriptMode
                ? Boolean(websiteUrl.trim() && (!isHeyGen || approvedAvatarScript))
                : !isHeyGen || Boolean(approvedAvatarScript)),
      },
    ]
  }, [
    formValues,
    wantsVideo,
    isHeyGen,
    isPdfScriptMode,
    isCustomScriptMode,
    hideCampaignDetailSteps,
    isWebsiteScriptMode,
    genSettings.heygenAvatarId,
    approvedAvatarScript,
    pdfFile,
    customPrompt,
    referenceImageFile,
    websiteUrl,
  ])

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
    if (!data.placements?.length) {
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

  const handleDownloadBriefExcel = () => {
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
      icpText: avatarExportSnapshot.icpText,
      customScriptText: customPrompt,
      strategyPreview,
      labelForIds: (options, ids) => labelsForIds(options, ids),
    })

    const hasIcp = Boolean(
      avatarExportSnapshot.icpText?.trim() || strategyPreview?.icp_text?.trim()
    )
    const hasScript = Boolean(
      avatarExportSnapshot.generatedFullScript?.trim() ||
        avatarExportSnapshot.spokenScript?.trim() ||
        approvedAvatarScript?.trim()
    )

    if (!hasIcp && !hasScript) {
      toast('Exporting Steps 1–9 — generate ICP + script in Step 8 first for full export.', {
        icon: '⚠️',
      })
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

      const brief = await briefsApi.create({
        brand_id: d.brand_id,
        title: d.title,
        objective: optionLabel(catalog.objectives, d.objective_id),
        target_audience: targetAudience,
        formats: d.formats as AdFormat[],
        ad_copy_tone: (d.ad_copy_tone ?? '').trim(),
        cta: d.cta.trim(),
        product_name: d.product_name ?? '',
        key_benefits: {
          target_variant_count: d.target_variant_count,
          offer: d.offer ?? '',
          placements: d.placements ?? [],
          hook_frameworks: d.hook_frameworks ?? [],
          notes: d.notes ?? '',
          audience,
          objective_id: d.objective_id,
          cta_text: d.cta.trim(),
          tone_text: (d.ad_copy_tone ?? '').trim(),
          copy_model: genSettings.copyModel,
          image_model: genSettings.imageModel,
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

      toast.success(
        wantsVidOnSubmit
          ? 'Brief saved — review the pipeline on the next page, then click Generate video'
          : 'Brief saved — click Generate on the brief page when ready'
      )

      router.push(`/briefs/${brief.id}`)
    } catch (err: unknown) {
      toast.error(extractApiError(err) || 'Failed to create brief')
    }
  }

  const needsApprovedScript =
    wantsVideo && isHeyGen && !hideCampaignDetailSteps && !approvedAvatarScript

  const submitBlocked =
    !hasBrands ||
    !catalog ||
    (isPdfScriptMode && !pdfFile) ||
    (isCustomScriptMode && (!customPrompt.trim() || !referenceImageFile)) ||
    (isWebsiteScriptMode && !websiteUrl.trim()) ||
    needsApprovedScript

  const durationOptions = VIDEO_DURATION_OPTIONS

  return (
    <div className="min-h-full app-mesh-bg">
      <header className="sticky top-0 z-20 glass-topbar flex items-center justify-between px-6 py-4">
        <div className="flex items-center gap-3">
          <h1 className="text-xl font-bold text-charcoal tracking-tight">Create Brief</h1>
          <span className="text-[10px] font-bold uppercase tracking-wider text-accent bg-accent/10 border border-accent/25 px-2.5 py-1 rounded-full">
            Campaign
          </span>
        </div>
        <Button type="submit" form="brief-form" variant="outline" size="sm" disabled={isSubmitting}>
          Save Brief
        </Button>
      </header>

      <form
        id="brief-form"
        onSubmit={handleSubmit(onSubmit, onInvalid)}
        className="max-w-[1440px] mx-auto p-6 md:p-8 grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-6"
      >
        <div className="space-y-4">
          {!hasBrands && (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              No brands yet. Create one in{' '}
              <Link href="/brand-kit" className="font-semibold text-teal hover:underline">
                Brand Kit
              </Link>
              .
            </div>
          )}

          <BriefSection title="Campaign & Brand" step="1">
            <Input
              label="Campaign Name"
              placeholder="e.g. Dental Clinic — New Patient Acquisition"
              error={errors.title?.message}
              {...register('title')}
            />
            <Select
              label="Brand"
              options={brandOptions}
              placeholder={hasBrands ? 'Select brand' : 'No brands'}
              disabled={!hasBrands}
              error={errors.brand_id?.message}
              {...register('brand_id')}
            />
            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">Objective</p>
              <PillRadio
                options={catalog?.objectives ?? []}
                value={objectiveId}
                onChange={(id) => setValue('objective_id', id, { shouldValidate: true })}
                disabled={!catalog}
              />
              {errors.objective_id && (
                <p className="mt-1 text-xs text-red-500">{errors.objective_id.message}</p>
              )}
            </div>
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
            <div>
              <p className="text-xs font-bold text-navy uppercase tracking-wide mb-2">
                Creative format
              </p>
              {!wantsVideo && (selectedFormats ?? []).length > 0 && (
                <p className="text-xs text-teal-800 bg-teal-50 border border-teal-200 rounded-lg px-3 py-2 mb-3">
                  <strong>Static</strong> / <strong>Carousel</strong> = image + copy only. Add{' '}
                  <strong>Landscape</strong> or <strong>Portrait</strong> for video (up to 4 minutes).
                </p>
              )}
              <ChipToggleGroup
                options={formatOptions}
                selected={selectedFormats ?? []}
                onChange={(next) => setValue('formats', next, { shouldValidate: true })}
                disabled={!catalog}
              />
              {errors.formats && <p className="mt-1 text-xs text-red-500">{errors.formats.message}</p>}
            </div>
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
            {isHiggsfieldVideo && (
              <p className="text-xs text-mid bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
                <strong>Higgsfield:</strong> Veo/DoP models are only <strong>5 seconds</strong> per
                clip. For longer ads choose <strong>Kling v3.0</strong>,{' '}
                <strong>Marketing Studio Video</strong>, or <strong>HeyGen</strong> (up to 4 minutes). Text/captions are added after generation
                (not inside the AI video) so they stay readable.
              </p>
            )}

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

          </BriefSection>

          {!hideCampaignDetailSteps && (
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
                options={catalog?.hook_frameworks ?? []}
                selected={selectedFrameworks ?? []}
                onChange={(next) => setValue('hook_frameworks', next)}
                disabled={!catalog}
              />
            </div>
          </BriefSection>

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

          </>
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
            <Input
              label="CTA Text"
              placeholder="e.g. Book Appointment, Shop Now, Learn More"
              error={errors.cta?.message}
              {...register('cta')}
            />
          </BriefSection>

          {/* ── Model Selector — bottom of form after all inputs ─────── */}
          <BriefSection title="AI Models" step="9">
            <p className="text-xs text-mid -mt-1 mb-1">
              Once you&apos;ve filled your campaign details above, click{' '}
              <strong>Analyse &amp; suggest models</strong> to let the AI pick the best
              image and video models — or choose manually from the dropdowns.
            </p>
            <ModelSelectorBlock
              catalog={catalog}
              wantsVideo={wantsVideo}
              genSettings={genSettings}
              setGenSettings={setGenSettings}
              imageModelSelect={imageModelSelect}
              videoModelSelect={videoModelSelect}
              getSuggestionInputs={() => ({
                campaign_name: formValues.title ?? '',
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
        </div>

        <aside className="space-y-4">
          <div className="rounded-2xl border border-white/10 bg-gradient-to-br from-ink to-[#25262e] p-6 text-white shadow-card">
            <p className="text-[11px] font-bold uppercase tracking-wider text-accent mb-4">Summary</p>
            <div className="space-y-2 text-xs text-subtle mb-4">
              <p>
                <span className="text-white font-semibold">Variants:</span> {targetVariantCount || 0}
              </p>
              <p>
                <span className="text-white font-semibold">Formats:</span>{' '}
                {(selectedFormats ?? []).join(', ') || '—'}
              </p>
              <p>
                <span className="text-white font-semibold">Output:</span>{' '}
                {wantsVideo
                  ? `Image + ${genSettings.videoModel}`
                  : wantsImageOnly
                    ? `Image (${genSettings.imageModel})`
                    : '—'}
              </p>
            </div>
            <div className="border-t border-white/10 pt-4 mb-4">
              <p className="text-[10px] uppercase tracking-wide text-lt font-bold">Total cost</p>
              <p className="text-3xl font-extrabold text-accent">${estimate.cost.toFixed(2)}</p>
            </div>
            <div className="border-t border-white/10 pt-4 mb-4">
              <p className="text-[10px] uppercase tracking-wide text-lt font-bold">Estimated delivery</p>
              <p className="text-lg font-bold">~ {estimate.minutes} min</p>
            </div>
            <p className="text-[10px] text-lt">Next: generate variants on the brief detail page.</p>
          </div>

          <div className="card-premium p-5">
            <p className="label-ui mb-3">Brief Checklist</p>
            <ul className="space-y-2 text-xs">
              {checklist.map((item) => (
                <li key={item.label} className={item.ok ? 'text-navy' : 'text-lt'}>
                  {item.ok ? '✓' : '○'} {item.label}
                </li>
              ))}
            </ul>
          </div>

          <StrategyPreviewPanel
            canBuild={Boolean(catalog && hasBrands)}
            onPreviewChange={setStrategyPreview}
            getInputs={() => ({
              campaign_name: formValues.title ?? '',
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

          <div className="flex flex-col gap-2">
            <Button
              type="button"
              variant="outline"
              className="w-full"
              onClick={handleDownloadBriefExcel}
            >
              Download brief Excel (Steps 1–9 + script)
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
        </aside>
      </form>
    </div>
  )
}
