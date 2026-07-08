'use client'

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useParams, useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import Card from '@/components/ui/Card'
import Modal from '@/components/ui/Modal'
import VariantGrid from '@/components/variant/VariantGrid'
import BriefGenerationPanel, {
  type BriefGenerationSettings,
  VIDEO_DURATION_OPTIONS,
} from '@/components/brief/BriefGenerationPanel'
import HeyGenProductionPipeline from '@/components/brief/HeyGenProductionPipeline'
import { defaultHeyGenSettings } from '@/components/brief/HeyGenVideoSettingsCard'
import { findVespriAvatar } from '@/lib/heygenAvatars'
import { heygenSettingsForApi, heygenSettingsFromApi, type HeyGenVideoSettings } from '@/lib/heygenOptions'
import { Spinner } from '@/components/ui/Loading'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { brandsApi, briefsApi, generationApi, variantsApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { getVariantPreviewUrls, isMotionVariantFormat } from '@/lib/variantMedia'
import { videoPreviewAspectClass, videoModalObjectFit } from '@/lib/creativeFormats'
import { getPipelineNodeStates } from '@/lib/briefPipeline'
import { cn, formatDate, timeAgo } from '@/lib/utils'
import type { Brief, BriefStatus, GenerationCatalog, PerformanceStatsContext, Variant } from '@/types'

function defaultSettingsFromBrief(
  brief: Brief,
  catalog?: Pick<
    GenerationCatalog,
    'heygen_avatar_options' | 'heygen_avatar_featured' | 'heygen_voice_options' | 'video_models'
  >
): BriefGenerationSettings {
  const kb = brief.key_benefits ?? {}
  const avatarOpts = catalog?.heygen_avatar_options ?? []
  const defaultAvatar =
    (kb.heygen_avatar_id as string) ||
    findVespriAvatar(avatarOpts as { id: string; label: string }[])?.id ||
    catalog?.heygen_avatar_featured?.[0]?.id ||
    avatarOpts.find((o) => o.label && !o.label.includes(' — '))?.id ||
    avatarOpts[0]?.id ||
    ''
  const defaultVoice =
    (kb.heygen_voice_id as string) ||
    catalog?.heygen_voice_options?.[0]?.id ||
    ''
  return {
    copyModel: (kb.copy_model as string) || 'claude',
    imageModel: (kb.image_model as string) || 'nano-banana-2',
    videoModel:
      (kb.video_model as string) ||
      catalog?.video_models?.find((m) => m.id === 'heygen-video-agent')?.id ||
      catalog?.video_models?.[0]?.id ||
      'heygen-video-agent',
    videoDurationSeconds: Number(kb.video_duration_seconds) || 8,
    heygenAvatarId: defaultAvatar,
    heygenVoiceId: defaultVoice,
    higgsfieldVoicePreset: (kb.higgsfield_voice_preset as string) || 'serene_female',
  }
}

function PipelineNode({ label, state }: { label: string; state: 'done' | 'run' | 'pend' | 'fail' }) {
  const styles = {
    done: 'bg-green-100 text-green-700 border-green-300',
    run: 'bg-[rgba(0,194,168,0.15)] text-teal border-mint pulse-mint',
    pend: 'bg-light text-lt border-border',
    fail: 'bg-red-100 text-red-700 border-red-300',
  }
  return (
    <div
      className={`px-3 py-2 rounded-lg text-xs font-semibold border text-center min-w-[100px] ${styles[state]}`}
    >
      {state === 'run' && <Spinner size="sm" className="inline mr-1 -mt-0.5" />}
      {label}
    </div>
  )
}

export default function BriefDetailPage() {
  const { id } = useParams<{ id: string }>()
  const router = useRouter()
  const [isGenerating, setIsGenerating] = useState(false)
  const [showRegenerateModal, setShowRegenerateModal] = useState(false)
  const [selectedVariant, setSelectedVariant] = useState<Variant | null>(null)
  const [genSettings, setGenSettings] = useState<BriefGenerationSettings | null>(null)
  const [heygenSettings, setHeygenSettings] = useState<HeyGenVideoSettings>(defaultHeyGenSettings())
  const [approvedAvatarScript, setApprovedAvatarScript] = useState<string | null>(null)
  const [replacePdfFile, setReplacePdfFile] = useState<File | null>(null)
  const [pdfBusy, setPdfBusy] = useState(false)
  const [statsImageUrls, setStatsImageUrls] = useState<string[]>([])
  const [ocrStatsPerImage, setOcrStatsPerImage] = useState<PerformanceStatsContext[]>([])
  const hydratedBriefIdRef = useRef<string | null>(null)
  const runningStatusSyncRef = useRef(false)
  const generateButtonRef = useRef<HTMLDivElement | null>(null)
  const focusedFromCreateRef = useRef(false)

  const { data: catalog } = useApi(() => generationApi.getCatalog(true), [], {
    cacheKey: 'generation/catalog-v4',
    ttlMs: API_CACHE_TTL.catalog,
  })
  const { data: brief, isLoading: briefLoading, refetch: refetchBrief } = useApi(
    () => briefsApi.get(id),
    [id],
    { cacheKey: `brief/${id}`, ttlMs: API_CACHE_TTL.briefs }
  )
  const { data: variants, isLoading: variantsLoading, refetch: refetchVariants } = useApi(
    () => variantsApi.list({ brief_id: id }),
    [id],
    { cacheKey: `variants/brief/${id}`, ttlMs: API_CACHE_TTL.variants }
  )

  const { data: brand } = useApi(async () => {
    if (!brief?.brand_id) return null
    return brandsApi.get(brief.brand_id)
  }, [brief?.brand_id])

  useEffect(() => {
    if (!brief || !catalog) return
    // Only hydrate form state once per brief — polling must not reset the pipeline UI.
    if (hydratedBriefIdRef.current === brief.id) return
    hydratedBriefIdRef.current = brief.id

    setGenSettings(defaultSettingsFromBrief(brief, catalog))
    const kb = brief.key_benefits ?? {}
    setHeygenSettings(heygenSettingsFromApi(kb.heygen_settings as Record<string, unknown>))
    setApprovedAvatarScript((kb.avatar_script as string) || null)
    const existing: string[] = []
    const multi = kb.stats_image_urls
    if (Array.isArray(multi)) existing.push(...(multi as string[]).filter(Boolean))
    const single = kb.stats_image_url as string | undefined
    if (single && !existing.includes(single)) existing.unshift(single)
    if (existing.length) setStatsImageUrls(existing)
    const perImg = kb.performance_stats_per_image
    if (Array.isArray(perImg) && perImg.length > 0) {
      setOcrStatsPerImage(perImg as PerformanceStatsContext[])
    }
  }, [brief, catalog])

  // From Create Brief (?autogenerate=1): open this brief and highlight Generate.
  // Do NOT auto-fire the long HeyGen request — that blocked UI/navigation and felt stuck.
  useEffect(() => {
    if (focusedFromCreateRef.current) return
    if (typeof window === 'undefined') return
    const params = new URLSearchParams(window.location.search)
    if (params.get('autogenerate') !== '1') return
    if (!brief || briefLoading || !genSettings) return

    focusedFromCreateRef.current = true
    router.replace(`/briefs/${id}`)
    document.body.style.overflow = ''

    const t = window.setTimeout(() => {
      generateButtonRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      toast.success('Brief ready — click Generate video to start', { duration: 5000 })
    }, 250)
    return () => window.clearTimeout(t)
  }, [brief, briefLoading, genSettings, router, id])

  // Poll quietly while a generation job is active — stop once variants are ready.
  useEffect(() => {
    if (brief?.status !== 'RUNNING') {
      runningStatusSyncRef.current = false
      return
    }
    const hasReadyVariant = (variants ?? []).some((v) => v.status === 'READY')
    if ((variants?.length ?? 0) > 0 && hasReadyVariant) {
      if (!runningStatusSyncRef.current) {
        runningStatusSyncRef.current = true
        void refetchBrief()
      }
      return
    }
    const tick = () => {
      if (document.visibilityState === 'hidden') return
      void refetchBrief({ background: true })
      void refetchVariants({ background: true })
    }
    tick()
    const timer = window.setInterval(tick, 20_000)
    return () => window.clearInterval(timer)
  }, [brief?.status, variants, refetchBrief, refetchVariants])

  // Safety: never leave the app in a scroll-locked state after leaving this page.
  useEffect(() => {
    return () => {
      document.body.style.overflow = ''
    }
  }, [])

  const pipelineSteps = catalog?.pipeline_steps ?? []
  const pipelineStates = useMemo(() => {
    if (!brief) return []
    return getPipelineNodeStates(
      brief.status as BriefStatus,
      pipelineSteps,
      variants ?? [],
      brief.variant_count
    )
  }, [brief, pipelineSteps, variants])

  const wantsVideoBrief = (brief?.formats ?? []).some((f) => f === 'reel' || f === 'video')
  const isHeyGen =
    wantsVideoBrief && Boolean(genSettings?.videoModel?.toLowerCase().startsWith('heygen'))
  const avatarLabel =
    catalog?.heygen_avatar_options?.find((o) => o.id === genSettings?.heygenAvatarId)?.label ?? ''
  const voiceLabel =
    catalog?.heygen_voice_options?.find((o) => o.id === genSettings?.heygenVoiceId)?.label ?? ''

  const handleResetStuckGeneration = async () => {
    if (!window.confirm('Stop waiting and reset this brief so you can click Generate again?')) return
    try {
      await briefsApi.update(id, { status: 'DRAFT' })
      toast.success('Generation reset — click Generate video when you are ready')
      hydratedBriefIdRef.current = null
      void refetchBrief()
      void refetchVariants()
    } catch (err: unknown) {
      toast.error(extractApiError(err))
    }
  }

  const runGenerate = async () => {
    if (!brief || !genSettings) return
    const wantsVideo = (brief.formats ?? []).some((f) => f === 'reel' || f === 'video')
    const kb = (brief.key_benefits ?? {}) as Record<string, unknown>
    const pdfMode = kb.script_source === 'pdf'

    setIsGenerating(true)
    try {
      if (ocrStatsPerImage.length > 0 || statsImageUrls.length > 0) {
        await briefsApi.update(id, {
          key_benefits: {
            ...kb,
            ...(statsImageUrls.length > 0
              ? { stats_image_url: statsImageUrls[0], stats_image_urls: statsImageUrls }
              : {}),
            ...(ocrStatsPerImage.length > 0
              ? { performance_stats_per_image: ocrStatsPerImage }
              : {}),
          },
        })
      }
      const result = await briefsApi.generate(id, {
        formats: brief.formats,
        ai_model: genSettings.copyModel,
        image_model: genSettings.imageModel,
        video_model: genSettings.videoModel,
        ...(wantsVideo ? { video_duration_seconds: genSettings.videoDurationSeconds } : {}),
        ...(wantsVideo && genSettings.videoModel.toLowerCase().startsWith('heygen')
          ? {
              heygen_avatar_id: genSettings.heygenAvatarId || undefined,
              heygen_voice_id: genSettings.heygenVoiceId || undefined,
              avatar_script: pdfMode ? undefined : approvedAvatarScript ?? undefined,
              heygen_settings: pdfMode ? undefined : heygenSettingsForApi(heygenSettings),
              ...(statsImageUrls.length > 0
                ? {
                    stats_image_url: statsImageUrls[0],
                    stats_image_urls: statsImageUrls,
                  }
                : {}),
            }
          : {}),
      })
      toast.success(`${result.variants_created} variants generated!`)
      setShowRegenerateModal(false)
      refetchBrief()
      refetchVariants()
    } catch (err: unknown) {
      const msg = extractApiError(err)
      const timedOut =
        (err as { code?: string })?.code === 'ECONNABORTED' ||
        /timeout/i.test(msg ?? '')
      toast.error(
        timedOut
          ? 'Request timed out — generation may still be running. This page will refresh automatically.'
          : msg
      )
      if (timedOut) {
        void refetchBrief()
        void refetchVariants()
      }
    } finally {
      setIsGenerating(false)
    }
  }

  const handleGenerateClick = () => {
    if ((variants?.length ?? 0) > 0) {
      setShowRegenerateModal(true)
      return
    }
    void runGenerate()
  }

  const handleApprove = async (variantId: string) => {
    try {
      await variantsApi.approve(variantId)
      toast.success('Variant approved')
      refetchVariants()
    } catch {
      toast.error('Failed to approve')
    }
  }

  const handleReject = async (variantId: string) => {
    try {
      await variantsApi.reject(variantId)
      toast.success('Variant rejected')
      refetchVariants()
    } catch {
      toast.error('Failed to reject')
    }
  }

  const handleDeleteVariant = async (variantId: string) => {
    if (!window.confirm('Delete this variant?')) return
    try {
      await variantsApi.delete(variantId)
      toast.success('Variant deleted')
      if (selectedVariant?.id === variantId) setSelectedVariant(null)
      refetchVariants()
    } catch {
      toast.error('Failed to delete')
    }
  }

  const handleReplaceScriptPdf = async () => {
    if (!replacePdfFile) {
      toast.error('Choose a PDF file')
      return
    }
    setPdfBusy(true)
    try {
      await briefsApi.uploadScriptPdf(id, replacePdfFile)
      toast.success('PDF script updated')
      setReplacePdfFile(null)
      refetchBrief()
    } catch (err: unknown) {
      toast.error(extractApiError(err))
    } finally {
      setPdfBusy(false)
    }
  }

  const handleClearScriptPdf = async () => {
    if (!window.confirm('Remove PDF script and switch to manual script mode?')) return
    setPdfBusy(true)
    try {
      await briefsApi.clearScriptPdf(id)
      toast.success('Switched to manual script mode')
      refetchBrief()
    } catch (err: unknown) {
      toast.error(extractApiError(err))
    } finally {
      setPdfBusy(false)
    }
  }

  if (briefLoading) {
    return (
      <div>
        <Topbar title="Brief detail" />
        <div className="p-5 space-y-3">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="skeleton h-16 rounded-xl" />
          ))}
        </div>
      </div>
    )
  }

  if (!brief) {
    return <div className="p-5 text-sm text-lt">Brief not found.</div>
  }

  if (!genSettings) {
    return (
      <div>
        <Topbar title={brief.title} />
        <div className="p-5 space-y-3">
          <div className="skeleton h-16 rounded-xl" />
        </div>
      </div>
    )
  }

  const statusBadgeVariant = (['READY', 'EXPORTED'].includes(brief.status)
    ? 'green'
    : ['FAILED'].includes(brief.status)
      ? 'red'
      : ['RUNNING'].includes(brief.status)
        ? 'mint'
        : 'amber') as 'green' | 'red' | 'mint' | 'amber'

  const hasVariants = (variants?.length ?? 0) > 0
  const generateActionLabel =
    brief.status === 'RUNNING'
      ? 'Generating…'
      : wantsVideoBrief && isHeyGen
        ? hasVariants
          ? '⚡ Regenerate video'
          : '⚡ Generate video'
        : hasVariants
          ? '⚡ Generate more'
          : '⚡ Generate variants'

  const kb = (brief.key_benefits ?? {}) as Record<string, unknown>
  const scriptFromPdf = kb.script_source === 'pdf'

  return (
    <div>
      <Topbar
        title={brief.title}
        subtitle={`Created ${timeAgo(brief.created_at)}`}
        actions={
          <div ref={generateButtonRef} className="flex gap-2">
            {hasVariants && (
              <Button
                variant="outline"
                size="sm"
                disabled={brief.status === 'RUNNING' || isGenerating}
                onClick={() => setShowRegenerateModal(true)}
              >
                Regenerate…
              </Button>
            )}
            <Button
              variant="primary"
              isLoading={isGenerating}
              onClick={handleGenerateClick}
              disabled={brief.status === 'RUNNING'}
            >
              {generateActionLabel}
            </Button>
          </div>
        }
      />

      <div className="p-5 space-y-4">
        <div className="flex items-center gap-3 flex-wrap">
          <Badge variant={statusBadgeVariant}>{brief.status}</Badge>
          <span className="text-xs text-lt">Formats: {brief.formats?.join(', ')}</span>
          <span className="text-xs text-lt">Tone: {brief.ad_copy_tone}</span>
          <span className="text-xs text-lt">CTA: {brief.cta}</span>
          <span className="text-xs text-lt">
            {brief.completed_variants}/{brief.variant_count} variants
          </span>
        </div>

        {brief.status === 'RUNNING' && (
          <div className="text-sm text-lt rounded-lg border border-mint/30 bg-mint/5 px-3 py-2 space-y-2">
            <p>
              Video generation is in progress (often 10–15 minutes for HeyGen). New variants appear
              below when ready — this page checks every 20 seconds without reloading your script edits.
            </p>
            {brief.completed_variants === 0 && (
              <Button type="button" variant="outline" size="sm" onClick={() => void handleResetStuckGeneration()}>
                Reset stuck generation
              </Button>
            )}
          </div>
        )}

        <BriefGenerationPanel
          catalog={catalog ?? undefined}
          formats={brief.formats ?? []}
          settings={genSettings}
          onChange={setGenSettings}
          disabled={brief.status === 'RUNNING' || isGenerating}
          hideHeyGenPresenter={isHeyGen}
          scrollable
        />

        {scriptFromPdf && isHeyGen && (
          <Card title="PDF script (authoritative)">
            <div className="p-4 space-y-3 text-sm">
              <p className="text-mid text-xs">
                Video uses only this text for speech. Avatar and voice are chosen below. Replace the
                PDF or clear to use manual / AI script again.
              </p>
              <p className="text-xs text-navy">
                <span className="font-bold">File:</span> {String(kb.pdf_filename ?? '—')}
              </p>
              <textarea
                readOnly
                className="w-full min-h-[120px] text-xs font-mono border border-border rounded-lg p-2 bg-light"
                value={String(kb.pdf_script_text ?? kb.avatar_script ?? '').slice(0, 8000)}
              />
              <div className="flex flex-wrap gap-2 items-center">
                <input
                  type="file"
                  accept=".pdf,application/pdf"
                  className="text-xs flex-1 min-w-[200px]"
                  onChange={(e) => setReplacePdfFile(e.target.files?.[0] ?? null)}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="primary"
                  isLoading={pdfBusy}
                  disabled={!replacePdfFile}
                  onClick={() => void handleReplaceScriptPdf()}
                >
                  Replace PDF
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={pdfBusy}
                  onClick={() => void handleClearScriptPdf()}
                >
                  Clear PDF mode
                </Button>
              </div>
            </div>
          </Card>
        )}

        {isHeyGen && genSettings && (
          <div className="rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-xs text-sky-900">
            <strong>Video production pipeline:</strong> Step 1 voice script (with stats OCR) → Step 2
            B-roll from that script → Step 3 avatar settings → approve → click{' '}
            <strong>{hasVariants ? 'Regenerate video' : 'Generate video'}</strong> at the top right
            {hasVariants ? ' → confirm in the modal → Generate with these settings' : ''}. This page
            does not use &quot;Create &amp; Generate&quot; — that is only on the new brief form.
          </div>
        )}

        {isHeyGen && genSettings && (
          <div className="space-y-4">
            <HeyGenProductionPipeline
              pdfScriptOnly={scriptFromPdf}
              durationSeconds={genSettings.videoDurationSeconds}
              avatarLabel={avatarLabel}
              voiceLabel={voiceLabel}
              avatarOptions={catalog?.heygen_avatar_options ?? []}
              avatarFeatured={catalog?.heygen_avatar_featured}
              heygenCatalog={catalog ?? undefined}
              voiceOptions={catalog?.heygen_voice_options ?? []}
              avatarId={genSettings.heygenAvatarId}
              voiceId={genSettings.heygenVoiceId}
              onAvatarChange={(heygenAvatarId) => setGenSettings({ ...genSettings, heygenAvatarId })}
              onVoiceChange={(heygenVoiceId) => setGenSettings({ ...genSettings, heygenVoiceId })}
              onDurationChange={(videoDurationSeconds) =>
                setGenSettings({ ...genSettings, videoDurationSeconds })
              }
              settings={heygenSettings}
              onSettingsChange={setHeygenSettings}
              durationOptions={VIDEO_DURATION_OPTIONS.map((opt) =>
                opt.id === '30' && isHeyGen ? { ...opt, label: '30s (recommended)' } : opt
              )}
              campaignContext={{
                productName: brief.product_name,
                offer: String(brief.key_benefits?.offer ?? ''),
                brandName: brand?.name ?? '',
                targetAudience: brief.target_audience,
                adCopyTone: brief.ad_copy_tone,
                cta: brief.cta,
                notes: String(brief.key_benefits?.notes ?? ''),
                avatarScript: approvedAvatarScript ?? undefined,
                forbiddenWords: brand?.forbidden_words,
              }}
              scriptContext={{
                briefNotes: String(brief.key_benefits?.notes ?? ''),
                productName: brief.product_name,
                offer: String(brief.key_benefits?.offer ?? ''),
                brandName: brand?.name ?? '',
                targetAudience: brief.target_audience,
                adCopyTone: brief.ad_copy_tone,
                cta: brief.cta,
                targetSeconds: genSettings.videoDurationSeconds,
                avatarLabel,
                voiceLabel,
                forbiddenWords: brand?.forbidden_words,
              }}
              approvedScript={approvedAvatarScript}
              onApprovedScript={setApprovedAvatarScript}
              preloadedStatsImageUrls={statsImageUrls}
              onExportSnapshotChange={(snap) => {
                // Only sync when data actually changes — identical snapshots used to
                // re-render the pipeline in a tight loop and freeze sidebar navigation.
                if (snap.statsImageUrls.length > 0) {
                  setStatsImageUrls((prev) => {
                    const next = snap.statsImageUrls
                    if (
                      prev.length === next.length &&
                      prev.every((u, i) => u === next[i])
                    ) {
                      return prev
                    }
                    return next
                  })
                }
                if (snap.performanceStatsPerImage?.length) {
                  setOcrStatsPerImage((prev) => {
                    const next = snap.performanceStatsPerImage
                    try {
                      if (JSON.stringify(prev) === JSON.stringify(next)) return prev
                    } catch {
                      /* fall through */
                    }
                    return next
                  })
                }
              }}
              onPersistScript={async (script) => {
                const kb = {
                  ...(brief.key_benefits ?? {}),
                  avatar_script: script,
                  ...(ocrStatsPerImage.length > 0
                    ? { performance_stats_per_image: ocrStatsPerImage }
                    : {}),
                }
                await briefsApi.update(id, { key_benefits: kb })
              }}
              exportFileName={brief.title}
            />
          </div>
        )}

        {brief.status !== 'DRAFT' && pipelineSteps.length > 0 && (
          <Card title="Generation pipeline" padding={false}>
            <div className="p-4 flex items-center gap-3 flex-wrap overflow-x-auto">
              {pipelineSteps.map((step, i) => (
                <React.Fragment key={step}>
                  <PipelineNode label={step} state={pipelineStates[i] ?? 'pend'} />
                  {i < pipelineSteps.length - 1 && (
                    <span className="text-mint font-bold text-sm">→</span>
                  )}
                </React.Fragment>
              ))}
            </div>
          </Card>
        )}

        <div>
          <h3 className="text-sm font-bold text-navy mb-3">Variants ({variants?.length ?? 0})</h3>
          <VariantGrid
            variants={(variants ?? []) as Variant[]}
            isLoading={variantsLoading}
            onApprove={handleApprove}
            onReject={handleReject}
            onDelete={handleDeleteVariant}
            onRegenerate={() => setShowRegenerateModal(true)}
            onView={setSelectedVariant}
          />
        </div>
      </div>

      <Modal
        isOpen={showRegenerateModal}
        onClose={() => !isGenerating && setShowRegenerateModal(false)}
        title="Regenerate video"
        size="lg"
        footer={
          <div className="flex gap-2 justify-end">
            <Button
              variant="outline"
              disabled={isGenerating}
              onClick={() => setShowRegenerateModal(false)}
            >
              Cancel
            </Button>
            <Button variant="primary" isLoading={isGenerating} onClick={() => void runGenerate()}>
              {wantsVideoBrief && isHeyGen
                ? 'Generate video with these settings'
                : 'Generate with these settings'}
            </Button>
          </div>
        }
      >
        <p className="text-sm text-mid mb-4">
          Choose models and settings below, then generate. This adds new variants (existing ones stay).
          Delete old variants first if you only want fresh creatives.
        </p>
        <BriefGenerationPanel
          catalog={catalog ?? undefined}
          formats={brief.formats ?? []}
          settings={genSettings}
          onChange={setGenSettings}
          disabled={isGenerating}
          scrollable
        />
      </Modal>

      {selectedVariant && (
        <Modal
          isOpen={!!selectedVariant}
          onClose={() => setSelectedVariant(null)}
          title="Variant detail"
          size="lg"
        >
          <VariantDetailBody
            variant={selectedVariant}
            onApprove={() => {
              handleApprove(selectedVariant.id)
              setSelectedVariant(null)
            }}
            onReject={() => {
              handleReject(selectedVariant.id)
              setSelectedVariant(null)
            }}
            onDelete={() => handleDeleteVariant(selectedVariant.id)}
            onRegenerate={() => {
              setSelectedVariant(null)
              setShowRegenerateModal(true)
            }}
          />
        </Modal>
      )}
    </div>
  )
}

function VariantDetailBody({
  variant,
  onApprove,
  onReject,
  onDelete,
  onRegenerate,
}: {
  variant: Variant
  onApprove(): void
  onReject(): void
  onDelete(): void
  onRegenerate(): void
}) {
  const {
    imageUrl: imageSrc,
    videoUrl: videoSrc,
    imageFailed,
    imageError,
    videoFailed,
    videoError,
    missingMotionMedia,
    subtitlesMissing,
    subtitleWarning,
    logoMissing,
    logoWarning,
  } = getVariantPreviewUrls(variant)

  return (
    <div className="p-6 space-y-3">
      {videoSrc ? (
        <div
          className={cn(
            'mx-auto w-full rounded-lg border border-border bg-black overflow-hidden',
            variant.format === 'video' ? 'max-w-3xl' : 'max-w-[360px]',
            videoPreviewAspectClass(variant.format)
          )}
        >
          <video
            src={videoSrc}
            className={cn(
              'h-full w-full bg-black',
              videoModalObjectFit(variant.format) === 'contain' ? 'object-contain' : 'object-cover'
            )}
            controls
            playsInline
          />
        </div>
      ) : null}
      {videoSrc && (subtitlesMissing || logoMissing) ? (
        <div className="space-y-2">
          {subtitlesMissing ? (
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              {subtitleWarning ||
                'Subtitles missing — regenerate to apply captions from your speakable script/copy.'}
            </p>
          ) : null}
          {logoMissing ? (
            <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
              {logoWarning ||
                'Clicktrends logo missing — confirm Brand Kit logo is uploaded, restart backend, generate again.'}
            </p>
          ) : null}
        </div>
      ) : null}
      {!videoSrc && imageSrc ? (
        <img
          src={imageSrc}
          alt={variant.headline || variant.hook}
          className="w-full rounded-lg border border-border max-h-[420px] object-contain bg-light"
        />
      ) : videoFailed || missingMotionMedia ? (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          Video not generated. {videoError || 'Use Regenerate variants with Runway credits.'}
        </p>
      ) : imageFailed && !isMotionVariantFormat(variant.format) ? (
        <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          Image not generated. {imageError}
        </p>
      ) : null}

      <div className="flex items-center gap-2 flex-wrap">
        <Badge variant="gray" className="capitalize">
          {variant.format}
        </Badge>
        <Badge variant={variant.compliance_status === 'PASSED' ? 'green' : 'amber'}>
          {variant.compliance_status}
        </Badge>
        <span className="text-xs text-lt">{formatDate(variant.created_at)}</span>
      </div>

      <div>
        <p className="text-[10px] font-bold text-lt uppercase tracking-wide mb-1">Hook</p>
        <p className="text-sm font-semibold text-navy">{variant.hook}</p>
      </div>
      <div>
        <p className="text-[10px] font-bold text-lt uppercase tracking-wide mb-1">Headline</p>
        <p className="text-sm text-navy">{variant.headline}</p>
      </div>
      <div>
        <p className="text-[10px] font-bold text-lt uppercase tracking-wide mb-1">Body copy</p>
        <p className="text-sm text-mid leading-relaxed whitespace-pre-line">{variant.body_copy}</p>
      </div>

      <div className="flex flex-wrap gap-2 pt-2">
        <button
          type="button"
          onClick={onApprove}
          className="flex-1 min-w-[90px] bg-mint text-navy text-sm font-bold py-2 rounded-lg hover:bg-[#00A892]"
        >
          Approve
        </button>
        <button
          type="button"
          onClick={onReject}
          className="flex-1 min-w-[90px] bg-red-100 text-red-700 text-sm font-bold py-2 rounded-lg hover:bg-red-200"
        >
          Reject
        </button>
        <button
          type="button"
          onClick={onRegenerate}
          className="flex-1 min-w-[90px] border border-mint text-navy text-sm font-bold py-2 rounded-lg hover:bg-[rgba(0,194,168,0.08)]"
        >
          Regenerate with new settings…
        </button>
        <button
          type="button"
          onClick={onDelete}
          className="flex-1 min-w-[90px] border border-border text-navy text-sm font-bold py-2 rounded-lg hover:bg-light"
        >
          Delete
        </button>
      </div>
    </div>
  )
}
