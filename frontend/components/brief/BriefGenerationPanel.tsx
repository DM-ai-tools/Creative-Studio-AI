'use client'

import React from 'react'
import HeyGenAvatarPicker from '@/components/brief/HeyGenAvatarPicker'
import Card from '@/components/ui/Card'
import Select from '@/components/ui/Select'
import { ChipToggle } from '@/components/ui/ChipToggle'
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
]

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
}

export default function BriefGenerationPanel({
  catalog,
  formats,
  settings,
  onChange,
  disabled,
  hideHeyGenPresenter = false,
}: BriefGenerationPanelProps) {
  const wantsVideo = formats.some((f) => f === 'reel' || f === 'video')
  const isHeyGen = settings.videoModel.toLowerCase().startsWith('heygen')

  const copyOptions =
    catalog?.copy_models.map((m) => ({ value: m.id, label: m.label })) ?? [
      { value: 'claude', label: 'Claude copy' },
      { value: 'openai', label: 'GPT copy' },
    ]
  const imageOptions =
    catalog?.image_models.map((m) => ({ value: m.id, label: m.label })) ?? [
      { value: 'nano-banana-2', label: 'Nano Banana 2' },
    ]
  const imageSelect = buildModelSelectGroups(catalog?.image_models, imageOptions)
  const videoOptions =
    catalog?.video_models.map((m) => ({ value: m.id, label: m.label })) ?? [
      { value: 'heygen-video-agent', label: 'HeyGen Video Agent (v3)' },
      { value: 'veo-3.1', label: 'Veo 3.1 (Runway — no avatar)' },
    ]
  const videoSelect = buildModelSelectGroups(catalog?.video_models, videoOptions)

  const voiceOptions =
    catalog?.heygen_voice_options?.map((o) => ({ value: o.id, label: o.label })) ?? []
  const higgsfieldVoiceOptions =
    catalog?.higgsfield_voice_options?.map((o) => ({ value: o.id, label: o.label })) ?? []

  const durationOptions = VIDEO_DURATION_OPTIONS

  return (
    <Card title="Generation models" className="border-accent/20">
      <p className="text-xs text-mid mb-4 -mt-1">
        {wantsVideo
          ? 'Choose copy, image, and video provider before generating or regenerating.'
          : 'This brief is image-only (static/carousel). Video and HeyGen settings are hidden.'}
      </p>

      {wantsVideo && !isHeyGen && settings.videoModel.startsWith('hf-') && (
        <p className="text-xs text-mid bg-light border border-border rounded-lg px-3 py-2 mb-4">
          <strong>Higgsfield</strong> — motion from your seed image (no AI text in the clip).
          Captions are burned from your ad copy / production script after render. Veo/DoP models are{' '}
          <strong>5s max</strong> and get a <strong>Runway voiceover</strong> (needs Runway API key).
          For native speech in the clip use <strong>Kling v3.0</strong> or{' '}
          <strong>Marketing Studio Video</strong> (up to 10–30s).
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
          hint="Groups: Runway, Higgsfield"
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
    </Card>
  )
}
