'use client'

import React, { useMemo } from 'react'
import HeyGenAvatarPicker from '@/components/brief/HeyGenAvatarPicker'
import Card from '@/components/ui/Card'
import Select from '@/components/ui/Select'
import { ChipToggle } from '@/components/ui/ChipToggle'
import { cn } from '@/lib/utils'
import { estimateGenerationCost, formatUsd } from '@/lib/estimateGenerationCost'
import type { GenerationCatalog } from '@/types'
import { buildModelSelectGroups } from '@/lib/modelCatalog'

export const VIDEO_DURATION_OPTIONS = [
  { id: '5', label: '5s' },
  { id: '6', label: '6s' },
  { id: '8', label: '8s' },
  { id: '10', label: '10s' },
  { id: '12', label: '12s' },
  { id: '15', label: '15s' },
  { id: '30', label: '30s' },
  { id: '60', label: '1m' },
  { id: '90', label: '1m 30s' },
  { id: '120', label: '2m' },
  { id: '180', label: '3m' },
  { id: '240', label: '4m' },
]

/** Seedance multi-scene stitch cap (matches backend SEEDANCE_MAX_TOTAL_SECONDS). */
export const SEEDANCE_MAX_DURATION_SECONDS = 90

export function isSeedanceVideoModel(videoModel: string): boolean {
  return videoModel.toLowerCase().includes('seedance')
}

export function durationOptionsForVideoModel(
  videoModel: string,
  options: typeof VIDEO_DURATION_OPTIONS = VIDEO_DURATION_OPTIONS,
) {
  if (isSeedanceVideoModel(videoModel)) {
    return options.filter((opt) => Number(opt.id) <= SEEDANCE_MAX_DURATION_SECONDS)
  }
  return options
}

export interface BriefGenerationSettings {
  copyModel: string
  imageModel: string
  videoModel: string
  videoDurationSeconds: number
  heygenAvatarId: string
  heygenVoiceId: string
  higgsfieldVoicePreset: string
}

interface BriefGenerationPanelProps {
  catalog: GenerationCatalog | undefined
  formats: string[]
  settings: BriefGenerationSettings
  onChange(settings: BriefGenerationSettings): void
  disabled?: boolean
  /** When HeyGenVideoSettingsCard is on the same page, hide duplicate avatar picker here. */
  hideHeyGenPresenter?: boolean
  /** Scroll long model pickers inside the card instead of stretching the page. */
  scrollable?: boolean
  /** Variant count for live cost estimate (defaults to 1). */
  variantCount?: number
}

export default function BriefGenerationPanel({
  catalog,
  formats,
  settings,
  onChange,
  disabled,
  hideHeyGenPresenter = false,
  scrollable = false,
  variantCount = 1,
}: BriefGenerationPanelProps) {
  const wantsVideo = formats.some((f) => f === 'reel' || f === 'video')
  const wantsImageOnly =
    formats.length > 0 && formats.every((f) => f === 'static' || f === 'carousel')
  const isHeyGen = settings.videoModel.toLowerCase().startsWith('heygen')
  const isSeedance = isSeedanceVideoModel(settings.videoModel)

  const costEstimate = useMemo(
    () =>
      estimateGenerationCost({
        catalog,
        mediaType: wantsVideo ? 'video' : 'image',
        imageModelId: settings.imageModel,
        videoModelId: settings.videoModel,
        variantCount,
        videoDurationSeconds: settings.videoDurationSeconds,
      }),
    [
      catalog,
      wantsVideo,
      settings.imageModel,
      settings.videoModel,
      settings.videoDurationSeconds,
      variantCount,
    ]
  )

  const copyOptions =
    catalog?.copy_models.map((m) => ({ value: m.id, label: m.label })) ?? [
      { value: 'claude', label: 'Claude copy' },
      { value: 'openai', label: 'GPT copy' },
    ]
  const imageOptions =
    catalog?.image_models.map((m) => ({
      value: m.id,
      label:
        typeof m.cost_usd === 'number'
          ? `${m.label} · $${m.cost_usd.toFixed(2)}/img`
          : m.label,
    })) ?? [{ value: 'nano-banana-2', label: 'Nano Banana 2' }]
  const imageSelectOptions = [
    { value: '', label: 'Choose image model…' },
    ...imageOptions,
  ]
  const imageSelect = buildModelSelectGroups(catalog?.image_models, imageSelectOptions)
  const videoOptions =
    catalog?.video_models.map((m) => ({
      value: m.id,
      label:
        typeof m.cost_usd === 'number'
          ? m.cost_unit === 'second'
            ? `${m.label} · $${m.cost_usd.toFixed(2)}/s`
            : `${m.label} · $${m.cost_usd.toFixed(2)}`
          : m.label,
    })) ?? [
      { value: 'heygen-video-agent', label: 'HeyGen Video Agent (v3)' },
      { value: 'veo-3.1', label: 'Veo 3.1 (Runway — no avatar)' },
    ]
  const videoSelect = buildModelSelectGroups(catalog?.video_models, videoOptions)

  const voiceOptions =
    catalog?.heygen_voice_options?.map((o) => ({ value: o.id, label: o.label })) ?? []
  const higgsfieldVoiceOptions =
    catalog?.higgsfield_voice_options?.map((o) => ({ value: o.id, label: o.label })) ?? []

  const durationOptions = durationOptionsForVideoModel(settings.videoModel)

  React.useEffect(() => {
    if (!isSeedance) return
    if (settings.videoDurationSeconds > SEEDANCE_MAX_DURATION_SECONDS) {
      onChange({ ...settings, videoDurationSeconds: SEEDANCE_MAX_DURATION_SECONDS })
    }
  }, [isSeedance, settings.videoModel])

  const panelBody = (
    <>
      <p className="text-xs text-mid mb-4 -mt-1">
        {wantsVideo
          ? 'Choose copy, image, and video provider before generating or regenerating.'
          : wantsImageOnly
            ? 'Pick the image model you want (Runway or Higgsfield), then click Generate variants.'
            : 'This brief is image-only (static/carousel). Video and HeyGen settings are hidden.'}
      </p>

      {wantsImageOnly && !settings.imageModel ? (
        <p className="text-xs text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 mb-4">
          Select an <strong>image model</strong> below before generating — nothing is auto-selected.
        </p>
      ) : null}

      {wantsVideo && !isHeyGen && settings.videoModel.startsWith('hf-') && (
        <p className="text-xs text-mid bg-light border border-border rounded-lg px-3 py-2 mb-4">
          <strong>Higgsfield</strong> — motion from your seed image (no AI text in the clip).
          Captions are burned from your ad copy / production script after render. Veo/DoP models are{' '}
          <strong>5s max</strong> and get a <strong>Runway voiceover</strong> (needs Runway API key).
          {isSeedance ? (
            <>
              {' '}
              <strong>Seedance</strong> builds longer ads (up to <strong>1m 30s</strong>) as multiple{' '}
              <strong>15s scenes</strong> from your B-roll directions, then stitches them together.
            </>
          ) : (
            <>
              {' '}
              For native speech in the clip use <strong>Kling v3.0</strong> or{' '}
              <strong>Marketing Studio Video</strong>.
            </>
          )}
        </p>
      )}
      {wantsVideo && !isHeyGen && settings.videoModel.startsWith('hf-') && higgsfieldVoiceOptions.length > 0 && (
        <div className="mb-4 p-4 rounded-2xl border border-accent/25 bg-accent/[0.05]">
          <Select
            label="Higgsfield voice (male/female)"
            hint="Used when Runway voiceover is added after Higgsfield motion render"
            options={higgsfieldVoiceOptions}
            value={settings.higgsfieldVoicePreset}
            disabled={disabled}
            onChange={(e) => onChange({ ...settings, higgsfieldVoicePreset: e.target.value })}
          />
        </div>
      )}
      {wantsVideo && !isHeyGen && !settings.videoModel.startsWith('hf-') && (
        <p className="text-xs text-mid bg-light border border-border rounded-lg px-3 py-2 mb-4">
          Runway: image → video. Needs Runway API credits.
        </p>
      )}
      {wantsVideo && isHeyGen && (
        <p className="text-xs text-mid bg-light border border-border rounded-lg px-3 py-2 mb-4">
          <strong>HeyGen Video Agent (v3)</strong> — avatar presenter, voice, dynamic backgrounds,
          and B-roll from your brief, approved script, and <strong>Scene / B-roll / Visual cues</strong>{' '}
          below. Uses your HeyGen API credits. To use Runway motion without an avatar, change{' '}
          <strong>Video provider</strong> to Veo 3.1.
        </p>
      )}

      {wantsVideo && (
        <div className="mb-4 p-4 rounded-2xl border border-accent/25 bg-accent/[0.05]">
          <p className="label-ui mb-2">
            Video length
          </p>
          <div className="flex flex-wrap gap-2">
            {durationOptions.map((opt) => (
              <ChipToggle
                key={opt.id}
                label={opt.label}
                selected={String(settings.videoDurationSeconds) === opt.id}
                disabled={disabled}
                onToggle={() => onChange({ ...settings, videoDurationSeconds: Number(opt.id) })}
              />
            ))}
          </div>
        </div>
      )}

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Select
          label="Copy model"
          options={copyOptions}
          value={settings.copyModel}
          disabled={disabled}
          onChange={(e) => onChange({ ...settings, copyModel: e.target.value })}
        />
        <Select
          label="Image model"
          options={imageSelect.options}
          groups={imageSelect.groups}
          hint="Groups: Runway, Higgsfield — required before generating images"
          value={settings.imageModel}
          disabled={disabled}
          onChange={(e) => onChange({ ...settings, imageModel: e.target.value })}
        />
        <Select
          label="Video provider"
          options={videoSelect.options}
          groups={videoSelect.groups}
          hint="Groups: HeyGen, Runway, Higgsfield"
          value={settings.videoModel}
          disabled={disabled || !wantsVideo}
          onChange={(e) => onChange({ ...settings, videoModel: e.target.value })}
        />
      </div>

      <div
        className={cn(
          'mt-4 rounded-xl border px-4 py-3 flex items-center justify-between gap-3',
          costEstimate.ready
            ? 'border-accent/25 bg-accent/[0.06]'
            : 'border-border bg-surface/80'
        )}
      >
        <div className="min-w-0">
          <p className="text-[10px] font-bold uppercase tracking-wider text-muted">
            Estimated cost
          </p>
          <p className="text-[11px] text-muted mt-0.5 truncate">
            {costEstimate.ready
              ? `${costEstimate.modelLabel} · ${variantCount} variant${variantCount === 1 ? '' : 's'}`
              : costEstimate.pendingReason}
          </p>
        </div>
        <p
          className={cn(
            'text-xl font-extrabold tabular-nums shrink-0',
            costEstimate.ready ? 'text-charcoal' : 'text-muted/50'
          )}
        >
          {formatUsd(costEstimate.costUsd)}
        </p>
      </div>

      {wantsVideo && isHeyGen && !hideHeyGenPresenter && (catalog?.heygen_avatar_options?.length ?? 0) > 0 && (
        <div className="mt-4 p-4 rounded-2xl border border-accent/25 bg-accent/[0.05] space-y-3">
          <p className="label-ui">HeyGen presenter</p>
          <HeyGenAvatarPicker
            compact
            catalog={catalog}
            avatarId={settings.heygenAvatarId}
            disabled={disabled}
            onAvatarChange={(heygenAvatarId) => onChange({ ...settings, heygenAvatarId })}
          />
          {voiceOptions.length > 0 && (
            <Select
              label="Voice (narration)"
              options={voiceOptions}
              value={settings.heygenVoiceId}
              disabled={disabled}
              onChange={(e) => onChange({ ...settings, heygenVoiceId: e.target.value })}
            />
          )}
        </div>
      )}
    </>
  )

  return (
    <Card
      title="Generation models"
      className={cn('border-accent/20', scrollable && 'flex flex-col max-h-[min(56vh,560px)]')}
      padding={!scrollable}
    >
      {scrollable ? (
        <div className="overflow-y-auto overscroll-contain min-h-0 flex-1 px-5 pb-5 pt-0 max-h-[min(48vh,480px)]">
          {panelBody}
        </div>
      ) : (
        panelBody
      )}
    </Card>
  )
}
