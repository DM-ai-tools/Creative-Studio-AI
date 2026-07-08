'use client'

import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import AvatarScriptPanel, { type AvatarScriptContext } from '@/components/brief/AvatarScriptPanel'
import Button from '@/components/ui/Button'
import HeyGenVideoSettingsCard from '@/components/brief/HeyGenVideoSettingsCard'
import MasterScriptPreview from '@/components/brief/MasterScriptPreview'
import VideoProductionStepper, {
  productionStepFromState,
  type ProductionStepId,
} from '@/components/brief/VideoProductionStepper'
import { generateSceneBrollDirections } from '@/lib/heygenScriptGeneration'
import type { HeyGenVideoSettings } from '@/lib/heygenOptions'
import type { HeyGenCampaignContext } from '@/lib/heygenScriptGeneration'
import type { CatalogOption, GenerationCatalog, PerformanceStatsContext } from '@/types'

const EMPTY_STATS: PerformanceStatsContext[] = []

type ExportSnapshot = {
  icpText: string | null
  generatedFullScript: string | null
  spokenScript: string | null
  statsImageUrl: string | null
  statsImageUrls: string[]
  performanceStats: PerformanceStatsContext | null
  performanceStatsPerImage: PerformanceStatsContext[]
}

export default function HeyGenProductionPipeline({
  pdfScriptOnly = false,
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
  onSettingsChange,
  durationOptions,
  campaignContext,
  scriptContext,
  approvedScript,
  onApprovedScript,
  onExportSnapshotChange,
  preloadedStatsImageUrls,
  onPersistScript,
  onAfterScriptApproved,
  exportFileName,
}: {
  pdfScriptOnly?: boolean
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
  onSettingsChange(settings: HeyGenVideoSettings): void
  durationOptions: { id: string; label: string }[]
  campaignContext: HeyGenCampaignContext
  scriptContext: AvatarScriptContext
  approvedScript: string | null
  onApprovedScript(script: string | null): void
  onExportSnapshotChange?: (snap: ExportSnapshot) => void
  preloadedStatsImageUrls?: string[]
  /** Save approved script to brief (detail page) */
  onPersistScript?: (script: string) => Promise<void>
  onAfterScriptApproved?: (script: string) => void
  /** Brief/campaign name for master script Excel export filename. */
  exportFileName?: string
}) {
  const brollRef = useRef<HTMLDivElement>(null)
  const [exportSnap, setExportSnap] = useState<ExportSnapshot | null>(null)
  const [autoBrollBusy, setAutoBrollBusy] = useState(false)
  const [masterWarnings, setMasterWarnings] = useState<string[]>([])
  const [approveState, setApproveState] = useState<{
    canApprove: boolean
    approve: () => void
    edit: () => void
  } | null>(null)
  const scriptPanelRef = useRef<HTMLDivElement>(null)
  const onExportSnapshotChangeRef = useRef(onExportSnapshotChange)
  useEffect(() => {
    onExportSnapshotChangeRef.current = onExportSnapshotChange
  }, [onExportSnapshotChange])

  const handleExportSnapshot = useCallback((snap: ExportSnapshot) => {
    setExportSnap((prev) => {
      try {
        if (prev && JSON.stringify(prev) === JSON.stringify(snap)) return prev
      } catch {
        /* ignore */
      }
      return snap
    })
    onExportSnapshotChangeRef.current?.(snap)
  }, [])

  const handleApproveStateChange = useCallback(
    (state: { canApprove: boolean; approve: () => void; edit: () => void }) => {
      setApproveState(state)
    },
    []
  )

  const handleMasterWarnings = useCallback((warnings: string[]) => {
    setMasterWarnings((prev) => {
      if (prev.length === warnings.length && prev.every((w, i) => w === warnings[i])) {
        return prev
      }
      return warnings
    })
  }, [])

  const scriptApproved = Boolean(approvedScript?.trim())
  const brollReady = Boolean(settings.sceneBrollDirections?.trim())
  const scriptForPreview = approvedScript || exportSnap?.generatedFullScript || null
  const avatarReady = Boolean(avatarId && voiceId)

  const activeStep: ProductionStepId = productionStepFromState({
    scriptApproved,
    brollReady,
    avatarReady,
  })

  const statsImageCount = exportSnap?.statsImageUrls?.length ?? preloadedStatsImageUrls?.length ?? 0
  const performanceStats = exportSnap?.performanceStats ?? undefined

  const campaignWithScript = useMemo(
    (): HeyGenCampaignContext => ({
      ...campaignContext,
      avatarScript: approvedScript ?? undefined,
    }),
    [campaignContext, approvedScript]
  )

  const runAutoBroll = useCallback(
    async (script: string) => {
      if (pdfScriptOnly || settings.sceneBrollDirections?.trim()) return
      setAutoBrollBusy(true)
      try {
        const directions = await generateSceneBrollDirections({
          campaign: { ...campaignContext, avatarScript: script },
          settings,
          durationSeconds,
          avatarLabel,
          voiceLabel,
          performanceStats: exportSnap?.performanceStats ?? undefined,
          statsImageCount,
        })
        onSettingsChange({
          ...settings,
          sceneBrollDirections: directions,
          brollInsert: 'directed',
        })
        toast.success('Step 2: B-roll scene map generated from your script')
        requestAnimationFrame(() => {
          brollRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        })
      } catch (err) {
        toast.error(
          err instanceof Error ? err.message : 'Could not auto-generate B-roll — use step 2 manually'
        )
      } finally {
        setAutoBrollBusy(false)
      }
    },
    [
      pdfScriptOnly,
      settings,
      campaignContext,
      durationSeconds,
      avatarLabel,
      voiceLabel,
      exportSnap,
      statsImageCount,
      onSettingsChange,
    ]
  )

  const handleScriptApproved = useCallback(
    async (script: string) => {
      if (onPersistScript) {
        try {
          await onPersistScript(script)
        } catch {
          toast.error('Could not save script to brief')
        }
      }
      if (!pdfScriptOnly) {
        await runAutoBroll(script)
      }
      onAfterScriptApproved?.(script)
    },
    [onPersistScript, pdfScriptOnly, runAutoBroll, onAfterScriptApproved]
  )

  const handleMasterScriptEdit = useCallback(
    (newScript: string) => {
      const clean = newScript.trim()
      if (!clean) return
      onApprovedScript(clean)
      void handleScriptApproved(clean)
      toast.success('Master script updated — B-roll will refresh if needed')
    },
    [onApprovedScript, handleScriptApproved]
  )

  return (
    <div className="space-y-4">
      {!pdfScriptOnly && (
        <VideoProductionStepper
          activeStep={activeStep}
          scriptApproved={scriptApproved}
          brollReady={brollReady}
          avatarReady={avatarReady}
        />
      )}

      {!pdfScriptOnly && (
        <div className="relative" ref={scriptPanelRef}>
          <span className="absolute top-4 right-4 z-10 flex h-7 w-7 items-center justify-center rounded-xl bg-accent-gradient text-[11px] font-bold text-white shadow-glow">
            1
          </span>
          <AvatarScriptPanel
            context={scriptContext}
            approvedScript={approvedScript}
            onApprovedScript={onApprovedScript}
            preloadedStatsImageUrls={preloadedStatsImageUrls}
            showApproveButton={false}
            onApproveStateChange={handleApproveStateChange}
            onExportSnapshotChange={handleExportSnapshot}
            onScriptApproved={(script) => {
              void handleScriptApproved(script)
            }}
          />
        </div>
      )}

      {!pdfScriptOnly && scriptForPreview && (
        <MasterScriptPreview
          avatarScript={scriptForPreview}
          sceneBrollDirections={settings.sceneBrollDirections}
          targetSeconds={durationSeconds}
          performanceStatsPerImage={
            exportSnap?.performanceStatsPerImage?.length
              ? exportSnap.performanceStatsPerImage
              : EMPTY_STATS
          }
          scriptApproved={scriptApproved}
          brollReady={brollReady}
          onWarningsChange={handleMasterWarnings}
          onScriptChange={handleMasterScriptEdit}
          exportFileName={exportFileName}
        />
      )}

      {!pdfScriptOnly && scriptForPreview && approveState && (
        <div className="flex flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-indigo-200 bg-white px-4 py-3">
          <div className="flex items-center gap-2">
            {scriptApproved ? (
              <span className="text-xs font-semibold text-emerald-700">
                ✓ Approved — B-roll generated below. Use “✎ Edit master script” above to change it.
              </span>
            ) : (
              <span className="text-xs text-slate-500">
                Reviewed the master script above? Edit it inline or Approve — B-roll is generated
                right after you approve.
              </span>
            )}
          </div>
          {!scriptApproved && (
            <Button
              type="button"
              variant="primary"
              size="sm"
              disabled={!approveState.canApprove}
              onClick={() => approveState.approve()}
            >
              Approve &amp; generate B-roll →
            </Button>
          )}
        </div>
      )}

      {!pdfScriptOnly && (
        <div ref={brollRef}>
          <HeyGenVideoSettingsCard
            section="broll"
            stepNumber={2}
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
            campaignContext={campaignWithScript}
            statsImageCount={statsImageCount}
            performanceStats={performanceStats}
          />
          {autoBrollBusy && (
            <p className="text-xs text-sky-700 mt-2">Generating B-roll from approved script…</p>
          )}
        </div>
      )}

      <HeyGenVideoSettingsCard
        section={pdfScriptOnly ? 'all' : 'avatar'}
        stepNumber={pdfScriptOnly ? 7 : 3}
        pdfScriptOnly={pdfScriptOnly}
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
        campaignContext={campaignWithScript}
      />

      {!pdfScriptOnly && scriptApproved && brollReady && masterWarnings.length > 0 && (
        <div className="rounded-xl border-2 border-amber-400 bg-amber-50 px-4 py-3 text-sm text-amber-950">
          <p className="font-bold">Fix stat / voice alignment before Generate</p>
          <p className="text-xs mt-1">
            Amber rows in the master script mean the avatar will not say what is on the stat image.
            Regenerate the voice script after Re-extract stats, or edit proof lines to cite the exact
            OCR figures.
          </p>
        </div>
      )}

      {!pdfScriptOnly && scriptApproved && brollReady && avatarReady && masterWarnings.length === 0 && (
        <div className="rounded-xl border-2 border-teal-400 bg-teal-50 px-4 py-3 text-sm text-teal-900">
          <p className="font-bold">✓ Step 4 — Ready to generate</p>
          <p className="text-xs mt-1 text-teal-800">
            Voice script, B-roll scenes, and avatar settings are aligned. Click{' '}
            <strong>Create &amp; Generate Video</strong> (new brief) or{' '}
            <strong>Generate video</strong> (brief page) to render.
          </p>
        </div>
      )}
    </div>
  )
}
