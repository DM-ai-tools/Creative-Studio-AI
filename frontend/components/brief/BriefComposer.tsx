'use client'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import React, { useEffect, useMemo, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import Select from '@/components/ui/Select'
import TextArea from '@/components/ui/TextArea'
import { ChipToggle, ChipToggleGroup } from '@/components/ui/ChipToggle'
import BriefSection from '@/components/brief/BriefSection'
import AvatarScriptPanel from '@/components/brief/AvatarScriptPanel'
import HeyGenVideoSettingsCard, { defaultHeyGenSettings } from '@/components/brief/HeyGenVideoSettingsCard'
import { findVespriAvatar, HEYGEN_VESPRI_AVATAR_ID } from '@/lib/heygenAvatars'
import { heygenSettingsForApi, type HeyGenVideoSettings } from '@/lib/heygenOptions'
import { VIDEO_DURATION_OPTIONS, type BriefGenerationSettings } from '@/components/brief/BriefGenerationPanel'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { brandsApi, briefsApi, generationApi } from '@/lib/api'
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
import type { AdFormat, CatalogOption } from '@/types'

const schema = z.object({
  brand_id: z.string().min(1, 'Select a brand'),
  title: z.string().min(3, 'Campaign name required'),
  objective_id: z.string().min(1, 'Select an objective'),
  target_variant_count: z.coerce.number().int().min(1).max(20),
  offer: z.string().min(3, 'Offer or key message required'),
  product_name: z.string().min(2, 'Product name required'),
  cta: z.string().min(2, 'Enter a call to action'),
  audience_type: z.string().min(2, 'Audience type required'),
  geography: z.string().min(2, 'Geography required'),
  age_range: z.string().min(2, 'Age range required'),
  languages: z.string().min(2, 'Languages required'),
  placements: z.array(z.string()).min(1, 'Select at least one placement'),
  formats: z.array(z.string()).min(1, 'Select at least one format'),
  hook_frameworks: z.array(z.string()),
  notes: z.string().max(2000).optional(),
  ad_copy_tone: z.string().min(2, 'Enter a tone for the copy'),
})

type FormData = z.infer<typeof schema>

interface BriefComposerProps {
  defaultBrandId?: string
}

function optionLabel(options: CatalogOption[], id: string): string {
  return options.find((option) => option.id === id)?.label ?? id
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
  const { data: catalog } = useApi(() => generationApi.getCatalog(), [], {
    cacheKey: 'generation/catalog-v2',
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
  const [generatingNotes, setGeneratingNotes] = useState(false)
  const [scriptBuildMode, setScriptBuildMode] = useState<'manual' | 'pdf'>('manual')
  const [pdfFile, setPdfFile] = useState<File | null>(null)

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
  const isPdfModeHeyGen = scriptBuildMode === 'pdf' && wantsVideo && isHeyGen

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
    if (wantsVideo && wantsImageOnly) return 'Create & Generate →'
    if (wantsVideo) return 'Create & Generate Video →'
    if (wantsImageOnly) return 'Create & Generate Image →'
    return 'Create & Generate →'
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
      { label: 'Audience defined', ok: isPdfModeHeyGen || Boolean(d.audience_type && d.geography) },
      { label: 'CTA & tone set', ok: isPdfModeHeyGen || Boolean(d.cta && d.ad_copy_tone) },
      {
        label: 'HeyGen avatar (if video)',
        ok: !wantsVideo || !isHeyGen || Boolean(genSettings.heygenAvatarId),
      },
      {
        label: isPdfModeHeyGen ? 'PDF script file chosen' : 'Avatar script approved',
        ok:
          !wantsVideo ||
          !isHeyGen ||
          (isPdfModeHeyGen ? Boolean(pdfFile) : Boolean(approvedAvatarScript)),
      },
    ]
  }, [
    formValues,
    wantsVideo,
    isHeyGen,
    isPdfModeHeyGen,
    genSettings.heygenAvatarId,
    approvedAvatarScript,
    pdfFile,
  ])

  const avatarLabel =
    catalog?.heygen_avatar_options?.find((o) => o.id === genSettings.heygenAvatarId)?.label ?? ''
  const voiceLabel =
    catalog?.heygen_voice_options?.find((o) => o.id === genSettings.heygenVoiceId)?.label ?? ''

  const handleGenerateScriptNotes = async () => {
    const d = formValues
    setGeneratingNotes(true)
    try {
      const result = await generationApi.generateAvatarScript({
        purpose: 'brief_notes',
        script_prompt: d.notes || undefined,
        product_name: d.product_name ?? '',
        offer: d.offer ?? '',
        brand_name: selectedBrand?.name ?? '',
        target_audience: [d.audience_type, d.geography, d.age_range].filter(Boolean).join(' · '),
        ad_copy_tone: d.ad_copy_tone ?? '',
        cta: d.cta ?? '',
        target_seconds: genSettings.videoDurationSeconds,
        forbidden_words: selectedBrand?.forbidden_words,
      })
      const text = result.full_script.trim()
      setValue('notes', text, { shouldValidate: true })
      toast.success('Talking points saved — generate spoken script in step 8')
    } catch {
      toast.error('Could not generate — add OPENROUTER_API_KEY and restart backend')
    } finally {
      setGeneratingNotes(false)
    }
  }

  const onSubmit = async (data: FormData) => {
    if (!catalog) return

    if (isPdfModeHeyGen) {
      if (!pdfFile) {
        toast.error('Choose a PDF that contains your full spoken script.')
        return
      }
      if (!genSettings.heygenAvatarId || !genSettings.heygenVoiceId) {
        toast.error('Select HeyGen avatar and voice.')
        return
      }
    }

    const fill = (s: string | undefined, minLen: number, placeholder: string) => {
      const t = (s ?? '').trim()
      return t.length >= minLen ? t : placeholder
    }

    const d: FormData = isPdfModeHeyGen
      ? {
          ...data,
          product_name: fill(data.product_name, 2, 'From PDF'),
          offer: fill(data.offer, 3, 'See PDF script'),
          audience_type: fill(data.audience_type, 2, 'General'),
          geography: fill(data.geography, 2, '—'),
          age_range: fill(data.age_range, 2, '—'),
          languages: fill(data.languages, 2, 'English'),
          ad_copy_tone: fill(data.ad_copy_tone, 2, 'Match PDF'),
          cta: fill(data.cta, 2, 'Learn more'),
          notes: fill(data.notes, 0, 'Full script from uploaded PDF.'),
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
      const brief = await briefsApi.create({
        brand_id: d.brand_id,
        title: d.title,
        objective: optionLabel(catalog.objectives, d.objective_id),
        target_audience: targetAudience,
        formats: d.formats as AdFormat[],
        ad_copy_tone: d.ad_copy_tone.trim(),
        cta: d.cta.trim(),
        product_name: d.product_name,
        key_benefits: {
          target_variant_count: d.target_variant_count,
          offer: d.offer,
          placements: d.placements,
          hook_frameworks: d.hook_frameworks,
          notes: d.notes ?? '',
          audience,
          objective_id: d.objective_id,
          cta_text: d.cta.trim(),
          tone_text: d.ad_copy_tone.trim(),
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
                  heygenOnSubmit && !isPdfModeHeyGen
                    ? heygenSettingsForApi(heygenSettings)
                    : undefined,
                avatar_script: isPdfModeHeyGen ? undefined : approvedAvatarScript ?? undefined,
                script_source: isPdfModeHeyGen ? 'pdf' : 'manual',
              }
            : {}),
        },
      })

      if (isPdfModeHeyGen && pdfFile) {
        await briefsApi.uploadScriptPdf(brief.id, pdfFile)
        toast.success('PDF script imported')
      }

      toast.success('Brief created — generating variants…')

      try {
        await briefsApi.generate(brief.id, {
          formats: d.formats as AdFormat[],
          count_per_format: 1,
          ai_model: genSettings.copyModel,
          image_model: genSettings.imageModel,
          video_model: genSettings.videoModel,
          higgsfield_voice_preset: genSettings.higgsfieldVoicePreset || undefined,
          ...(wantsVidOnSubmit ? { video_duration_seconds: genSettings.videoDurationSeconds } : {}),
          ...(wantsVidOnSubmit && heygenOnSubmit
            ? {
                heygen_avatar_id: genSettings.heygenAvatarId || undefined,
                heygen_voice_id: genSettings.heygenVoiceId || undefined,
                avatar_script: isPdfModeHeyGen ? undefined : approvedAvatarScript ?? undefined,
                heygen_settings:
                  isPdfModeHeyGen ? undefined : heygenSettingsForApi(heygenSettings),
              }
            : {}),
        })
        toast.success('Variants generated')
      } catch (genErr: unknown) {
        toast.error(
          extractApiError(genErr) || 'Brief saved but generation failed — open the brief and try again'
        )
      }

      router.push(`/briefs/${brief.id}`)
    } catch {
      toast.error('Failed to create brief')
    }
  }

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
        onSubmit={handleSubmit(onSubmit)}
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
                  <strong>Landscape</strong> or <strong>Portrait</strong> for video (up to 30s).
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
            <div
              className={`grid grid-cols-1 gap-3 pt-2 border-t border-border ${
                wantsVideo ? 'md:grid-cols-3' : 'md:grid-cols-2'
              }`}
            >
              <Select
                label="Copy model"
                options={
                  catalog?.copy_models.map((m) => ({ value: m.id, label: m.label })) ?? []
                }
                value={genSettings.copyModel}
                onChange={(e) => setGenSettings({ ...genSettings, copyModel: e.target.value })}
              />
              <Select
                label="Image model"
                hint="Open list — groups: Runway, Higgsfield"
                options={imageModelSelect.options}
                groups={imageModelSelect.groups}
                value={genSettings.imageModel}
                onChange={(e) => setGenSettings({ ...genSettings, imageModel: e.target.value })}
              />
              {wantsVideo && (
                <Select
                  label="Video provider"
                  hint="Open list — groups: HeyGen, Runway, Higgsfield"
                  options={videoModelSelect.options}
                  groups={videoModelSelect.groups}
                  value={genSettings.videoModel}
                  onChange={(e) =>
                    setGenSettings({ ...genSettings, videoModel: e.target.value })
                  }
                />
              )}
            </div>
            {isHiggsfieldVideo && (
              <p className="text-xs text-mid bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mt-2">
                <strong>Higgsfield:</strong> Veo/DoP models are only <strong>5 seconds</strong> per
                clip. For 10–30s ads choose <strong>Kling v3.0</strong> or{' '}
                <strong>Marketing Studio Video</strong>. Text/captions are added after generation
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
                <strong>PDF</strong> — upload a PDF; only avatar + voice are chosen here.
              </p>
              <div className="flex flex-wrap gap-2 mb-3">
                <ChipToggle
                  label="Manual campaign & AI"
                  selected={scriptBuildMode === 'manual'}
                  disabled={!wantsVideo}
                  onToggle={() => {
                    setScriptBuildMode('manual')
                    setPdfFile(null)
                  }}
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
              </div>
              {scriptBuildMode === 'pdf' && wantsVideo && !isHeyGen && (
                <p className="text-[11px] text-mid mb-2">Switching provider to HeyGen for PDF mode…</p>
              )}
              {isPdfModeHeyGen && (
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
            </div>
          </BriefSection>

          {!isPdfModeHeyGen && (
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
            <Input label="Hero Product" placeholder="e.g. General & Cosmetic Dentistry" error={errors.product_name?.message} {...register('product_name')} />
            <Input label="Offer / Key Message" placeholder="e.g. Free consultation for new patients" error={errors.offer?.message} {...register('offer')} />
            <div>
              <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
                <label
                  htmlFor="script-brief-notes"
                  className="block text-xs font-bold text-navy uppercase tracking-wide"
                >
                  {wantsVideo && isHeyGen ? 'Creative brief (talking points)' : 'Script / Brief Notes'}
                </label>
                <Button
                  type="button"
                  size="sm"
                  variant="primary"
                  isLoading={generatingNotes}
                  onClick={() => void handleGenerateScriptNotes()}
                >
                  {wantsVideo && isHeyGen ? 'Generate talking points' : '✨ Generate with AI'}
                </Button>
              </div>
              <TextArea
                id="script-brief-notes"
                rows={4}
                placeholder={
                  wantsVideo && isHeyGen
                    ? 'Writer directions: themes, tone, what to mention — not the words the avatar speaks aloud.'
                    : 'What should the ad say? Paste script ideas or talking points — or click Generate with AI above.'
                }
                error={errors.notes?.message}
                {...register('notes')}
              />
              <p className="mt-1 text-[11px] text-mid">
                {wantsVideo && isHeyGen ? (
                  <>
                    Ideas for the ad only — saved on the brief, not sent to HeyGen as voiceover. In{' '}
                    <strong>step 8</strong> below, click <strong>Generate spoken script</strong>, then{' '}
                    <strong>Approve</strong>.
                  </>
                ) : (
                  'Uses Claude Sonnet 4.6 from your campaign fields above (product, offer, audience, tone).'
                )}
              </p>
            </div>
          </BriefSection>

          </>
          )}

          {wantsVideo && isHeyGen && (
            <>
              <HeyGenVideoSettingsCard
                pdfScriptOnly={isPdfModeHeyGen}
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
                onChange={setHeygenSettings}
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
              />
              {!isPdfModeHeyGen && (
              <AvatarScriptPanel
                context={{
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
                }}
                approvedScript={approvedAvatarScript}
                onApprovedScript={setApprovedAvatarScript}
              />
              )}
            </>
          )}

          <BriefSection title="Call to Action" step="7">
            <Input
              label="CTA Text"
              placeholder="e.g. Book Appointment, Shop Now, Learn More"
              error={errors.cta?.message}
              {...register('cta')}
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

          <div className="flex flex-col gap-2">
            <Button type="button" variant="outline" onClick={() => router.push('/briefs')}>
              Back
            </Button>
            <Button type="submit" variant="primary" isLoading={isSubmitting} disabled={!hasBrands || !catalog || (isPdfModeHeyGen && !pdfFile)}>
              {submitLabel}
            </Button>
          </div>
        </aside>
      </form>
    </div>
  )
}
