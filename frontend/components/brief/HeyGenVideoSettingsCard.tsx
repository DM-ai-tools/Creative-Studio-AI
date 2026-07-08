'use client'

import { useState } from 'react'
import toast from 'react-hot-toast'
import HeyGenSelectWithCustom from '@/components/brief/HeyGenSelectWithCustom'
import Button from '@/components/ui/Button'
import Select from '@/components/ui/Select'
import TextArea from '@/components/ui/TextArea'
import {
  generateSceneBrollDirections,
  generateVisualCues,
  type HeyGenCampaignContext,
} from '@/lib/heygenScriptGeneration'
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
import VoicePreviewPicker from '@/components/brief/VoicePreviewPicker'
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
  campaignContext?: HeyGenCampaignContext
  /** When true, only avatar / voice / duration (PDF supplies full script). */
  pdfScriptOnly?: boolean
  /** Which section to render in the production pipeline */
  section?: 'all' | 'avatar' | 'broll'
  /** Step badge number shown on the card */
  stepNumber?: number
  statsImageCount?: number
  performanceStats?: import('@/types').PerformanceStatsContext
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
  section = 'all',
  stepNumber = 7,
  statsImageCount = 0,
  performanceStats,
}: HeyGenVideoSettingsCardProps) {
  const patch = (partial: Partial<HeyGenVideoSettings>) => onChange({ ...settings, ...partial })
  const [generatingVisualCues, setGeneratingVisualCues] = useState(false)
  const [generatingSceneBroll, setGeneratingSceneBroll] = useState(false)
  const scriptApproved = Boolean(campaignContext?.avatarScript?.trim())
  const showAvatar = section === 'all' || section === 'avatar'
  const showBroll = section === 'all' || section === 'broll'
  const catalogForAvatars =
    heygenCatalog ??
    (avatarFeatured
      ? { heygen_avatar_options: avatarOptions, heygen_avatar_featured: avatarFeatured }
      : { heygen_avatar_options: avatarOptions })

  const handleGenerateSceneBroll = async () => {
    if (!campaignContext) {
      toast.error('Fill in campaign details above first')
      return
    }
    if (!scriptApproved) {
      toast.error('Approve your voice script first (step 1)')
      return
    }
    setGeneratingSceneBroll(true)
    try {
      const directions = await generateSceneBrollDirections({
        campaign: campaignContext,
        settings,
        durationSeconds,
        avatarLabel,
        voiceLabel,
        performanceStats,
        statsImageCount,
      })
      patch({ sceneBrollDirections: directions, brollInsert: 'directed' })
      toast.success('B-roll scene map generated from your approved script')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not generate scene map')
    } finally {
      setGeneratingSceneBroll(false)
    }
  }

  const handleGenerateVisualCues = async () => {
    if (!campaignContext) {
      toast.error('Fill in campaign details above first')
      return
    }
    if (!scriptApproved) {
      toast.error('Approve your voice script first (step 1)')
      return
    }
    setGeneratingVisualCues(true)
    try {
      const cues = await generateVisualCues({
        campaign: campaignContext,
        settings,
        durationSeconds,
        avatarLabel,
        voiceLabel,
      })
      patch({ visualCues: cues })
      toast.success('Visual cues generated from your approved script')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Could not generate visual cues')
    } finally {
      setGeneratingVisualCues(false)
    }
  }

  const title =
    section === 'broll'
      ? 'B-roll scene map'
      : section === 'avatar'
        ? 'Avatar & video settings'
        : `HeyGen Avatar Video — ${durationSeconds}s Settings`

  return (
    <div className="card-premium p-5 md:p-6 relative border-accent/20">
      <span className="absolute top-4 right-4 flex h-7 w-7 items-center justify-center rounded-xl bg-accent-gradient text-[11px] font-bold text-white shadow-glow">
        {stepNumber}
      </span>
      <div className="flex items-center gap-2 mb-2 pr-10">
        <span className="text-lg" aria-hidden>
          {section === 'broll' ? '🎬' : '🎥'}
        </span>
        <h3 className="text-sm font-bold text-charcoal tracking-tight">{title}</h3>
      </div>
      <p className="text-xs text-muted bg-accent/[0.06] border border-accent/20 rounded-xl px-3 py-2.5 mb-4">
        {section === 'broll' ? (
          <>
            <strong>Step 2 — after script approve:</strong> B-roll scenes are generated from your
            approved voice script. Timestamps match spoken lines so stats images and presenter
            stay in sync.
          </>
        ) : section === 'avatar' ? (
          <>
            <strong>Step 3:</strong> Choose presenter, voice, duration, and post-production options
            (subtitles, logo). Script and B-roll are already locked from steps 1–2.
          </>
        ) : pdfScriptOnly ? (
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

      {showAvatar && (
      <>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <div className="md:col-span-2">
          <HeyGenAvatarPicker
            catalog={catalogForAvatars}
            avatarId={avatarId}
            onAvatarChange={onAvatarChange}
          />
        </div>
        <VoicePreviewPicker
          voices={voiceOptions}
          selectedId={voiceId}
          onChange={onVoiceChange}
          sampleText={
            campaignContext
              ? `Hi, I'm your AI presenter for ${campaignContext.productName || campaignContext.brandName || 'your brand'}. ${campaignContext.cta || 'Let me show you something amazing today!'}`
              : undefined
          }
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
          label="Music"
          options={HEYGEN_MUSIC_OPTIONS}
          value={settings.music}
          customValue={settings.musicCustom}
          onValueChange={(music) => patch({ music })}
          onCustomChange={(musicCustom) => patch({ musicCustom })}
          customPlaceholder="e.g. Soft piano, uplifting"
        />
        <div className="flex flex-col justify-end gap-2 text-xs md:col-span-2">
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
      </>
      )}

      {showBroll && !pdfScriptOnly && (
      <div className="mt-3 space-y-4">
        {!scriptApproved && (
          <p className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
            Approve your voice script in <strong>step 1</strong> first — B-roll is generated from
            that script so timings stay in sync with stats images.
          </p>
        )}
        <HeyGenSelectWithCustom
          label="B-roll insert"
          options={HEYGEN_BROLL_OPTIONS}
          value={settings.brollInsert}
          customValue={settings.brollInsertCustom}
          onValueChange={(brollInsert) => patch({ brollInsert })}
          onCustomChange={(brollInsertCustom) => patch({ brollInsertCustom })}
          customPlaceholder="e.g. Only show B-roll I list in scene directions"
        />
        <div>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
            <label
              htmlFor="heygen-scene-broll"
              className="block text-xs font-bold text-navy uppercase tracking-wide"
            >
              Scene B-roll directions (required for directed mode)
            </label>
            <Button
              type="button"
              size="sm"
              variant="primary"
              isLoading={generatingSceneBroll}
              disabled={!campaignContext || !scriptApproved}
              onClick={() => void handleGenerateSceneBroll()}
            >
              ✨ Generate scene map from script
            </Button>
          </div>
          <TextArea
            id="heygen-scene-broll"
            rows={6}
            placeholder={`[00:00-00:08] HOOK — Presenter on camera, professional agency / IT office\n[00:08-00:18] PROBLEM — B-roll: frustrated CEO at executive desk, Google Ads dashboard declining\n[00:18-00:28] SOLUTION — B-roll: agency team in glass conference room, product on screen\n[00:28-00:38] PROOF — Presenter on camera in same agency office (stats added in post)\n[00:38-00:45] CTA — Presenter on camera in agency office, warm close`}
            value={settings.sceneBrollDirections}
            onChange={(e) => patch({ sceneBrollDirections: e.target.value, brollInsert: 'directed' })}
          />
          <p className="mt-1 text-[11px] text-mid">
            Tell HeyGen <strong>exactly</strong> what to show per scene — presenter or B-roll.
            Set B-roll insert to <strong>Use my scene directions</strong>. HeyGen will not pick random
            footage when this is filled.
          </p>
        </div>

        <div>
          <div className="flex flex-wrap items-center justify-between gap-2 mb-1.5">
            <label
              htmlFor="heygen-visual-cues"
              className="block text-xs font-bold text-navy uppercase tracking-wide"
            >
              On-screen text / lower-thirds (optional)
            </label>
            <Button
              type="button"
              size="sm"
              variant="primary"
              isLoading={generatingVisualCues}
              disabled={!campaignContext || !scriptApproved}
              onClick={() => void handleGenerateVisualCues()}
            >
              ✨ Generate text cues from script
            </Button>
          </div>
          <TextArea
            id="heygen-visual-cues"
            rows={3}
            placeholder="00:08 — Lower-third headline at bottom (not on face). 00:25 — CTA bar at bottom."
            value={settings.visualCues}
            onChange={(e) => patch({ visualCues: e.target.value })}
          />
          <p className="mt-1 text-[11px] text-mid">
            Headlines and captions only — use <strong>bottom third</strong>, never over the face.
          </p>
        </div>
      </div>
      )}
    </div>
  )
}
