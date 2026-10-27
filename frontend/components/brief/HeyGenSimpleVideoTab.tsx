'use client'

import { useCallback, useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import HeyGenVideoSettingsCard from '@/components/brief/HeyGenVideoSettingsCard'
import Button from '@/components/ui/Button'
import TextArea from '@/components/ui/TextArea'
import { assetsApi, generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { mergePerformanceStats } from '@/lib/performanceStats'
import type { HeyGenVideoSettings } from '@/lib/heygenOptions'
import type { CatalogOption, GenerationCatalog, PerformanceStatsContext } from '@/types'

type StatsImageItem = {
  id: string
  file?: File
  previewUrl: string
  imageUrl?: string
  stats?: PerformanceStatsContext
}

function newStatsItemId(): string {
  return `stats-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export type HeyGenVideoExportSnapshot = {
  icpText: string | null
  generatedFullScript: string | null
  spokenScript: string | null
  statsImageUrl: string | null
  statsImageUrls: string[]
  performanceStats: PerformanceStatsContext | null
  performanceStatsPerImage: PerformanceStatsContext[]
}

export interface HeyGenSimpleVideoTabProps {
  script: string
  onScriptChange: (value: string) => void
  durationSeconds: number
  onDurationChange: (seconds: number) => void
  durationOptions: { id: string; label: string }[]
  avatarId: string
  voiceId: string
  avatarLabel: string
  voiceLabel: string
  onAvatarChange: (id: string) => void
  onVoiceChange: (id: string) => void
  settings: HeyGenVideoSettings
  onSettingsChange: (settings: HeyGenVideoSettings) => void
  avatarOptions: CatalogOption[]
  avatarFeatured?: CatalogOption[]
  heygenCatalog?: Pick<GenerationCatalog, 'heygen_avatar_options' | 'heygen_avatar_featured'> | null
  voiceOptions: CatalogOption[]
  brandName?: string
  productName?: string
  niche?: string
  onExportSnapshotChange?: (snap: HeyGenVideoExportSnapshot) => void
  /** PDF alternate path */
  scriptMode?: 'custom' | 'pdf'
  onScriptModeChange?: (mode: 'custom' | 'pdf') => void
  pdfFile?: File | null
  onPdfFileChange?: (file: File | null) => void
}

const SCRIPT_PLACEHOLDER = `[00:00-00:05] PRESENTER — SPEAK: "Your opening line…"
[00:05-00:12] B-ROLL — SAME AVATAR walks through the office and reviews the analytics dashboard
[00:12-00:20] PRESENTER — SPEAK: "Your proof line citing the result…" Use [INSERT STAT IMAGE 1]
[00:20-00:27] B-ROLL — SAME AVATAR demonstrates the product on a laptop
[00:27-00:30] PRESENTER — SPEAK: "Book a free call today"`

export default function HeyGenSimpleVideoTab({
  script,
  onScriptChange,
  durationSeconds,
  onDurationChange,
  durationOptions,
  avatarId,
  voiceId,
  avatarLabel,
  voiceLabel,
  onAvatarChange,
  onVoiceChange,
  settings,
  onSettingsChange,
  avatarOptions,
  avatarFeatured,
  heygenCatalog,
  voiceOptions,
  brandName,
  productName,
  niche,
  onExportSnapshotChange,
  scriptMode = 'custom',
  onScriptModeChange,
  pdfFile,
  onPdfFileChange,
}: HeyGenSimpleVideoTabProps) {
  const [statsItems, setStatsItems] = useState<StatsImageItem[]>([])
  const [statsLoading, setStatsLoading] = useState(false)
  const [promptLoading, setPromptLoading] = useState(false)
  const [nicheOptions, setNicheOptions] = useState<{ id: string; label: string }[]>([])
  const [selectedNiche, setSelectedNiche] = useState('')

  useEffect(() => {
    generationApi
      .creativeStudioNiches()
      .then(setNicheOptions)
      .catch(() => {
        /* optional helper */
      })
  }, [])

  const statsImageUrls = useMemo(
    () => statsItems.map((item) => item.imageUrl).filter(Boolean) as string[],
    [statsItems]
  )
  const mergedPerformanceStats = useMemo(
    () =>
      mergePerformanceStats(
        statsItems.map((item) => item.stats).filter(Boolean) as PerformanceStatsContext[]
      ),
    [statsItems]
  )
  const performanceStatsPerImage = useMemo(
    () =>
      statsItems.map((item) => item.stats).filter(Boolean) as PerformanceStatsContext[],
    [statsItems]
  )

  const pushExportSnapshot = useCallback(() => {
    onExportSnapshotChange?.({
      icpText: null,
      generatedFullScript: script.trim() || null,
      spokenScript: script.trim() || null,
      statsImageUrl: statsImageUrls[0] ?? null,
      statsImageUrls,
      performanceStats: mergedPerformanceStats,
      performanceStatsPerImage,
    })
  }, [
    onExportSnapshotChange,
    script,
    statsImageUrls,
    mergedPerformanceStats,
    performanceStatsPerImage,
  ])

  useEffect(() => {
    pushExportSnapshot()
  }, [pushExportSnapshot])

  const addStatsFiles = (files: FileList | File[] | null) => {
    if (!files || files.length === 0) return
    const incoming = Array.from(files).filter((f) => f.type.startsWith('image/'))
    if (incoming.length === 0) {
      toast.error('Choose PNG, JPEG, or WebP images')
      return
    }
    setStatsItems((prev) => [
      ...prev,
      ...incoming.map((file) => ({
        id: newStatsItemId(),
        file,
        previewUrl: URL.createObjectURL(file),
      })),
    ])
  }

  const removeStatsItem = (id: string) => {
    setStatsItems((prev) => {
      const item = prev.find((i) => i.id === id)
      if (item?.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(item.previewUrl)
      return prev.filter((i) => i.id !== id)
    })
  }

  const runExtractStats = async () => {
    const pending = statsItems.filter((item) => !item.stats && item.file)
    if (pending.length === 0) {
      if (statsItems.length === 0) {
        toast.error('Upload dashboard screenshots first')
      } else {
        toast.success('All images already processed')
      }
      return
    }
    setStatsLoading(true)
    try {
      const updated = [...statsItems]
      let ok = 0
      for (const item of pending) {
        if (!item.file) continue
        const idx = updated.findIndex((i) => i.id === item.id)
        if (idx < 0) continue
        try {
          const [result, asset] = await Promise.all([
            generationApi.extractStatsFromImage(item.file),
            assetsApi.upload(item.file, undefined, 'stats_dashboard'),
          ])
          updated[idx] = {
            ...updated[idx],
            stats: result.stats,
            imageUrl: asset.file_url,
          }
          ok += 1
        } catch (err) {
          toast.error(
            extractApiError(err, `Could not read stats from ${item.file?.name ?? 'image'}`)
          )
        }
      }
      setStatsItems(updated)
      if (ok > 0) {
        toast.success(
          ok === 1 ? 'Stats image ready for video' : `${ok} stats images ready for video`
        )
      }
    } finally {
      setStatsLoading(false)
    }
  }

  const handleGeneratePrompt = async () => {
    const nicheId = selectedNiche || niche?.trim()
    if (!nicheId) {
      toast.error('Pick a niche or fill in Niche above')
      return
    }
    setPromptLoading(true)
    try {
      const result = await generationApi.creativeStudioPrompt({
        niche: nicheId,
        media_mode: 'video',
        duration_seconds: durationSeconds,
        brand_name: brandName,
        product_name: productName,
      })
      onScriptChange(result.prompt)
      toast.success('Timed script draft generated — edit timestamps and lines')
    } catch (err) {
      toast.error(extractApiError(err, 'Could not generate script'))
    } finally {
      setPromptLoading(false)
    }
  }

  const isPdfMode = scriptMode === 'pdf'

  return (
    <div className="space-y-4">
      <div className="rounded-xl border-2 border-sky-200 bg-sky-50/80 px-4 py-3 text-sm text-sky-950">
        <p className="font-bold">Create the complete video from one prompt</p>
        <p className="text-xs mt-1 text-sky-800">
          Paste one timed prompt below in your own format. The app recognises presenter dialogue
          and visual scenes from common labels, then routes each scene to the correct HeyGen
          workflow automatically. Choose the avatar and voice only once.
        </p>
      </div>

      {onScriptModeChange && (
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={() => onScriptModeChange('custom')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-full border ${
              !isPdfMode
                ? 'border-accent bg-accent/10 text-charcoal'
                : 'border-border text-mid hover:border-accent/30'
            }`}
          >
            Paste timed script
          </button>
          <button
            type="button"
            onClick={() => onScriptModeChange('pdf')}
            className={`px-3 py-1.5 text-xs font-semibold rounded-full border ${
              isPdfMode
                ? 'border-accent bg-accent/10 text-charcoal'
                : 'border-border text-mid hover:border-accent/30'
            }`}
          >
            Upload PDF script
          </button>
        </div>
      )}

      {isPdfMode && onPdfFileChange ? (
        <div className="card-premium p-5 border-accent/20 space-y-3">
          <label className="block text-xs font-bold text-navy uppercase tracking-wide">
            Script PDF
          </label>
          <input
            type="file"
            accept=".pdf,application/pdf"
            className="text-sm w-full file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-teal file:text-white"
            onChange={(e) => onPdfFileChange(e.target.files?.[0] ?? null)}
          />
          {pdfFile ? (
            <p className="text-xs text-navy">
              Selected: <strong>{pdfFile.name}</strong>
            </p>
          ) : (
            <p className="text-xs text-amber-700">Choose a PDF before generating.</p>
          )}
          <p className="text-[11px] text-mid">
            Speech comes from the PDF. Avatar and voice are chosen below.
          </p>
        </div>
      ) : (
        <>
          <div className="card-premium p-5 border-accent/20 space-y-3">
            <div className="flex flex-wrap items-end gap-3">
              <div className="flex-1 min-w-[180px]">
                <label className="block text-xs font-bold text-navy uppercase tracking-wide mb-1.5">
                  Niche helper <span className="font-normal normal-case text-mid">(optional)</span>
                </label>
                <select
                  className="w-full rounded-lg border border-border px-3 py-2 text-sm bg-surface"
                  value={selectedNiche}
                  onChange={(e) => setSelectedNiche(e.target.value)}
                >
                  <option value="">Use niche from form above…</option>
                  {nicheOptions.map((n) => (
                    <option key={n.id} value={n.id}>
                      {n.label}
                    </option>
                  ))}
                </select>
              </div>
              <Button
                type="button"
                size="sm"
                variant="primary"
                isLoading={promptLoading}
                onClick={() => void handleGeneratePrompt()}
              >
                ✨ Draft script with AI
              </Button>
            </div>

            <div>
              <label
                htmlFor="heygen-timed-script"
                className="block text-xs font-bold text-navy uppercase tracking-wide mb-1.5"
              >
                One video prompt — script and scenes
              </label>
              <TextArea
                id="heygen-timed-script"
                rows={12}
                placeholder={SCRIPT_PLACEHOLDER}
                value={script}
                onChange={(e) => onScriptChange(e.target.value)}
              />
              <p className="mt-1.5 text-[11px] text-mid">
                Give every scene an exact start and end time in any common style, such as
                <strong> [00:00-00:05]</strong>, <strong>0–5 seconds</strong>, or
                <strong> Scene 1 | 0:00–0:05</strong>. Label speaking sections as Presenter,
                Avatar speaks, or Talking head; label visual sections as B-roll, Cutaway, or
                Cinematic scene. Add
                <strong> [INSERT STAT IMAGE 1]</strong> where a supplied dashboard should appear.
              </p>
            </div>
          </div>

          <div className="card-premium p-5 border-accent/20 space-y-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <label className="block text-xs font-bold text-navy uppercase tracking-wide">
                Stat / dashboard images
              </label>
              <Button
                type="button"
                size="sm"
                variant="primary"
                isLoading={statsLoading}
                disabled={statsItems.length === 0}
                onClick={() => void runExtractStats()}
              >
                Process images for video
              </Button>
            </div>
            <div
              tabIndex={0}
              onPaste={(e) => {
                const item = Array.from(e.clipboardData.items).find((entry) =>
                  entry.type.startsWith('image/')
                )
                const file = item?.getAsFile()
                if (file) {
                  e.preventDefault()
                  addStatsFiles([file])
                }
              }}
              className="rounded-xl border-2 border-dashed border-border bg-light p-4"
            >
              <input
                type="file"
                accept="image/png,image/jpeg,image/webp"
                multiple
                className="text-sm w-full file:mr-3 file:py-2 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-teal file:text-white"
                onChange={(e) => {
                  addStatsFiles(e.target.files)
                  e.target.value = ''
                }}
              />
              <p className="text-[11px] text-mid mt-2">
                Upload or paste screenshots. Reference them in the script as{' '}
                <strong>[INSERT STAT IMAGE 1]</strong>, <strong>[INSERT STAT IMAGE 2]</strong>, etc.
                Click <strong>Process images</strong> before generating.
              </p>
            </div>
            {statsItems.length > 0 && (
              <div className="flex flex-wrap gap-3">
                {statsItems.map((item, index) => (
                  <div key={item.id} className="relative group">
                    <img
                      src={item.previewUrl}
                      alt={`Stat ${index + 1}`}
                      className="h-24 w-auto rounded-lg border border-border object-contain bg-white"
                    />
                    <span className="absolute top-1 left-1 text-[10px] font-bold bg-black/60 text-white px-1.5 py-0.5 rounded">
                      #{index + 1}
                    </span>
                    <button
                      type="button"
                      className="absolute -top-2 -right-2 h-5 w-5 rounded-full bg-red-500 text-white text-xs opacity-0 group-hover:opacity-100"
                      onClick={() => removeStatsItem(item.id)}
                      aria-label="Remove"
                    >
                      ×
                    </button>
                    {item.imageUrl && (
                      <span className="block text-[10px] text-emerald-700 mt-0.5">Ready</span>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </>
      )}

      <HeyGenVideoSettingsCard
        section="all"
        stepNumber={2}
        simplifiedMode
        durationSeconds={durationSeconds}
        avatarLabel={avatarLabel}
        voiceLabel={voiceLabel}
        avatarOptions={avatarOptions}
        avatarFeatured={avatarFeatured}
        heygenCatalog={heygenCatalog}
        voiceOptions={voiceOptions}
        avatarId={avatarId}
        voiceId={voiceId}
        onAvatarChange={onAvatarChange}
        onVoiceChange={onVoiceChange}
        onDurationChange={onDurationChange}
        settings={settings}
        onChange={onSettingsChange}
        durationOptions={durationOptions}
        campaignContext={{
          productName: productName ?? '',
          brandName: brandName ?? '',
          offer: '',
          targetAudience: '',
          adCopyTone: '',
          cta: '',
          notes: '',
          avatarScript: script.trim() || undefined,
        }}
      />
    </div>
  )
}
