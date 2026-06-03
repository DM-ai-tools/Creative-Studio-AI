'use client'

import { useState } from 'react'
import toast from 'react-hot-toast'
import HeyGenSelectWithCustom from '@/components/brief/HeyGenSelectWithCustom'
import Button from '@/components/ui/Button'
import Select from '@/components/ui/Select'
import TextArea from '@/components/ui/TextArea'
import { generationApi } from '@/lib/api'
import { heygenSettingsForApi } from '@/lib/heygenOptions'
import {
  DEFAULT_HEYGEN_SETTINGS,
  HEYGEN_ASPECT_OPTIONS,
  HEYGEN_BROLL_OPTIONS,
  HEYGEN_CAMERA_OPTIONS,
  HEYGEN_DELIVERY_OPTIONS,
  HEYGEN_MUSIC_OPTIONS,
  HEYGEN_SCENE_OPTIONS,
  type HeyGenVideoSettings,
} from '@/lib/heygenOptions'
import HeyGenAvatarPicker from '@/components/brief/HeyGenAvatarPicker'
import type { CatalogOption, GenerationCatalog } from '@/types'

interface HeyGenVideoSettingsCardProps {
  durationSeconds: number
  avatarLabel: string
  voiceLabel: string
  avatarOptions: CatalogOption[]
  avatarFeatured?: CatalogOption[]
  heygenCatalog?: Pick<GenerationCatalog, 'heygen_avatar_options' | 'heygen_avatar_featured'> | null
  voiceOptions: CatalogOption[]
  avatarId: string
  voiceId: string
  onAvatarChange(id: string): void
  onVoiceChange(id: string): void
  onDurationChange(seconds: number): void
  settings: HeyGenVideoSettings
  onChange(settings: HeyGenVideoSettings): void
  durationOptions: { id: string; label: string }[]
  /** Campaign fields used to generate visual cues with Claude */
  campaignContext?: {
    productName: string
    offer: string
    brandName: string
    targetAudience: string
    adCopyTone: string
    cta: string
    notes: string
    avatarScript?: string
    forbiddenWords?: string[]
  }
  /** When true, only avatar / voice / duration (PDF supplies full script). */
  pdfScriptOnly?: boolean
}

export function defaultHeyGenSettings(): HeyGenVideoSettings {
  return { ...DEFAULT_HEYGEN_SETTINGS }
}

export default function HeyGenVideoSettingsCard({
  durationSeconds,
  avatarLabel,
  voiceLabel,
  avatarOptions,
  avatarFeatured,
  heygenCatalog,
  voiceOptions,
  avatarId,
  voiceId,
  onAvatarChange,
  onVoiceChange,
  onDurationChange,
  settings,
  onChange,
  durationOptions,
  campaignContext,
  pdfScriptOnly = false,
}: HeyGenVideoSettingsCardProps) {
  const patch = (partial: Partial<HeyGenVideoSettings>) => onChange({ ...settings, ...partial })
  const [generatingVisualCues, setGeneratingVisualCues] = useState(false)
  const catalogForAvatars =
    heygenCatalog ??
    (avatarFeatured
      ? { heygen_avatar_options: avatarOptions, heygen_avatar_featured: avatarFeatured }
      : { heygen_avatar_options: avatarOptions })

  const handleGenerateVisualCues = async () => {
    if (!campaignContext) {
      toast.error('Fill in campaign details above first')
      return
    }
    setGeneratingVisualCues(true)
    try {
      const apiSettings = heygenSettingsForApi(settings)
      const result = await generationApi.generateAvatarScript({
        purpose: 'visual_cues',
        script_prompt: settings.visualCues || undefined,
        product_name: campaignContext.productName,
        offer: campaignContext.offer,
        brand_name: campaignContext.brandName,
        target_audience: campaignContext.targetAudience,
        ad_copy_tone: campaignContext.adCopyTone,
        cta: campaignContext.cta,
        notes: [
          campaignContext.notes,
          campaignContext.avatarScript,
          `Scene: ${apiSettings.scene_label}`,
          `Style: ${apiSettings.delivery_style_label}`,
        ]
          .filter(Boolean)
          .join('\n'),
        target_seconds: durationSeconds,
        avatar_label: avatarLabel,
        voice_label: voiceLabel,
        forbidden_words: campaignContext.forbiddenWords,
      })
      patch({ visualCues: result.full_script.trim() })
      toast.success('Visual cues generated')
    } catch {
      toast.error('Could not generate — check OPENROUTER_API_KEY and restart backend')
    } finally {
      setGeneratingVisualCues(false)
    }
  }

  return (
    <div className="card-premium p-5 md:p-6 relative border-accent/20">
      <span className="absolute top-4 right-4 flex h-7 w-7 items-center justify-center rounded-xl bg-accent-gradient text-[11px] font-bold text-white shadow-glow">
        7
      </span>
      <div className="flex items-center gap-2 mb-2 pr-10">
        <span className="text-lg" aria-hidden>
          🎥
        </span>
        <h3 className="text-sm font-bold text-charcoal tracking-tight">
          HeyGen Avatar Video — {durationSeconds}s Settings
        </h3>
      </div>
      <p className="text-xs text-muted bg-accent/[0.06] border border-accent/20 rounded-xl px-3 py-2.5 mb-4">
        {pdfScriptOnly ? (
          <>
            <strong>PDF script mode:</strong> Spoken lines come only from your uploaded PDF. Choose
            avatar, voice, and length below.
          </>
        ) : (
          <>
            These settings apply when the brief includes a {durationSeconds}-second Avatar Video.
            B-roll cuts are generated as <strong>full-frame</strong> scenes only (no split-screen or half-chart layouts).
            With <strong>Subtitles</strong> on, the approved script is burned in at the bottom (main points highlighted).
            Pick <strong>Custom…</strong> on any dropdown to type your own value.
          </>
        )}
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="md:col-span-2">
          <HeyGenAvatarPicker
            catalog={catalogForAvatars}
            avatarId={avatarId}
            onAvatarChange={onAvatarChange}
          />
        </div>
        <Select
          label="Voice"
          options={voiceOptions.map((o) => ({ value: o.id, label: o.label }))}
          value={voiceId}
          onChange={(e) => onVoiceChange(e.target.value)}
        />
        <Select
          label="Duration"
          options={durationOptions.map((o) => ({ value: o.id, label: o.label }))}
          value={String(durationSeconds)}
          onChange={(e) => onDurationChange(Number(e.target.value))}
        />
        {!pdfScriptOnly && (
          <>
        <HeyGenSelectWithCustom
          label="Aspect ratio"
          options={HEYGEN_ASPECT_OPTIONS}
          value={settings.aspectRatio}
          customValue={settings.aspectRatioCustom}
          onValueChange={(aspectRatio) => patch({ aspectRatio })}
          onCustomChange={(aspectRatioCustom) => patch({ aspectRatioCustom })}
          customPlaceholder="e.g. 4:5 portrait for feed"
        />
        <HeyGenSelectWithCustom
          label="Scene / background"
          options={HEYGEN_SCENE_OPTIONS}
          value={settings.scene}
          customValue={settings.sceneCustom}
          onValueChange={(scene) => patch({ scene })}
          onCustomChange={(sceneCustom) => patch({ sceneCustom })}
          customPlaceholder="e.g. Dental clinic reception, bright and modern"
        />
        <HeyGenSelectWithCustom
          label="Camera framing"
          options={HEYGEN_CAMERA_OPTIONS}
          value={settings.cameraFraming}
          customValue={settings.cameraFramingCustom}
          onValueChange={(cameraFraming) => patch({ cameraFraming })}
          onCustomChange={(cameraFramingCustom) => patch({ cameraFramingCustom })}
          customPlaceholder="e.g. Over-the-shoulder product shot"
        />
        <HeyGenSelectWithCustom
          label="Delivery style"
          options={HEYGEN_DELIVERY_OPTIONS}
          value={settings.deliveryStyle}
          customValue={settings.deliveryStyleCustom}
          onValueChange={(deliveryStyle) => patch({ deliveryStyle })}
          onCustomChange={(deliveryStyleCustom) => patch({ deliveryStyleCustom })}
          customPlaceholder="e.g. Warm expert, like a friendly hygienist"
        />
        <HeyGenSelectWithCustom
          label="B-roll insert"
          options={HEYGEN_BROLL_OPTIONS}
          value={settings.brollInsert}
          customValue={settings.brollInsertCustom}
          onValueChange={(brollInsert) => patch({ brollInsert })}
          onCustomChange={(brollInsertCustom) => patch({ brollInsertCustom })}
          customPlaceholder="e.g. Smile makeover before/after at 00:12"
        />
        <HeyGenSelectWithCustom
          label="Music"
          options={HEYGEN_MUSIC_OPTIONS}
          value={settings.music}
          customValue={settings.musicCustom}
          onValueChange={(music) => patch({ music })}
          onCustomChange={(musicCustom) => patch({ musicCustom })}
          customPlaceholder="e.g. Soft piano, uplifting"
        />
        <div className="flex flex-col justify-end gap-2 text-xs">
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.captions}
              onChange={(e) => patch({ captions: e.target.checked })}
              className="rounded border-border"
            />
            <span className="font-semibold text-navy uppercase tracking-wide">Subtitles</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.burnInCaptions}
              onChange={(e) => patch({ burnInCaptions: e.target.checked })}
              className="rounded border-border"
            />
            <span className="font-semibold text-navy uppercase tracking-wide">
              Burn-in spoken lines
            </span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={settings.brandStyledOverlay}
              onChange={(e) => patch({ brandStyledOverlay: e.target.checked })}
              className="rounded border-border"
            />
            <span className="font-semibold text-navy uppercase tracking-wide">
              Brand logo on video (top-left landscape · bottom-right portrait)
            </span>
          </label>
        </div>
          </>
        )}
      </div>

      <p className="mt-3 text-[10px] text-mid">
        Presenter: <strong>{avatarLabel || '—'}</strong> · Voice: <strong>{voiceLabel || '—'}</strong>
      </p>

      {!pdfScriptOnly && (
      <div className="mt-3">
        <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
          <label
            htmlFor="heygen-visual-cues"
            className="block text-xs font-bold text-navy uppercase tracking-wide"
          >
            Visual cues / on-screen text (optional)
          </label>
          <Button
            type="button"
            size="sm"
            variant="primary"
            isLoading={generatingVisualCues}
            disabled={!campaignContext}
            onClick={() => void handleGenerateVisualCues()}
          >
            ✨ Generate with Claude Sonnet 4.6
          </Button>
        </div>
        <TextArea
          id="heygen-visual-cues"
          rows={3}
          placeholder="00:08 — Lower-third headline at bottom (not on face). 00:18 — B-roll. 00:25 — CTA bar at bottom."
          value={settings.visualCues}
          onChange={(e) => patch({ visualCues: e.target.value })}
        />
        <p className="mt-1 text-[11px] text-mid">
          Timed directions for HeyGen. During talking-head, headlines go in the{' '}
          <strong>bottom third only</strong> — never a full-width bar over the face. B-roll: natural
          skin tones (no blue/teal faces).
        </p>
      </div>
      )}
    </div>
  )
}
