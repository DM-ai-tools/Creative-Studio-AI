'use client'

import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import TextArea from '@/components/ui/TextArea'
import {
  hasTimedScriptLines,
  inferTargetSecondsFromSourceScript,
  isPlaceholderScriptResult,
  looksLikeCreativeBrief,
  resolveTargetSecondsForConversion,
  spokenTextFromTimedScript,
} from '@/lib/avatarScript'
import { generationApi, assetsApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { mergePerformanceStats } from '@/lib/performanceStats'
import type {
  AvatarScriptResult,
  IcpScriptResult,
  PerformanceStatsContext,
  WebsiteScriptResult,
} from '@/types'

export interface AvatarScriptContext {
  /** Step 5 creative brief — context for AI only, not copied into the prompt box. */
  briefNotes: string
  productName: string
  offer: string
  brandName: string
  targetAudience: string
  adCopyTone: string
  cta: string
  targetSeconds: number
  avatarLabel: string
  voiceLabel: string
  forbiddenWords?: string[]
  /** When set, "Website URL" mode is active — generate script from this page */
  websiteUrl?: string
}

interface AvatarScriptPanelProps {
  context: AvatarScriptContext
  approvedScript: string | null
  onApprovedScript: (script: string | null) => void
  /** Called after approve — parent can scroll to submit, etc. */
  onScriptApproved?: (script: string) => void
  /** Sync ICP + full timed script + stats image to parent for brief submit / export */
  onExportSnapshotChange?: (snapshot: {
    icpText: string | null
    generatedFullScript: string | null
    spokenScript: string | null
    statsImageUrl: string | null
    statsImageUrls: string[]
    performanceStats: PerformanceStatsContext | null
    performanceStatsPerImage: PerformanceStatsContext[]
  }) => void
  /** Pre-load stats image URLs already saved on the brief (seeded on mount) */
  preloadedStatsImageUrls?: string[]
  /** Hide the in-panel Approve button (parent renders it after the master script). */
  showApproveButton?: boolean
  /** Expose approve availability + handlers so the parent can place the buttons. */
  onApproveStateChange?: (state: {
    canApprove: boolean
    approve: () => void
    edit: () => void
  }) => void
}

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

function scriptTextFromResult(result: AvatarScriptResult | null): string {
  if (!result) return ''
  const full = (result.full_script || '').trim()
  if (full) return full
  return result.lines.map((line) => `[${line.start} - ${line.end}] ${line.text}`).join('\n')
}

function IcpPreviewPanel({ icpText, onClose }: { icpText: string; onClose: () => void }) {
  return (
    <div className="rounded-xl border-2 border-violet-300 bg-violet-50 p-4 mt-3">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-bold text-violet-700 uppercase tracking-wide">
          ICP Profile Generated
        </span>
        <button
          type="button"
          onClick={onClose}
          className="text-xs text-violet-500 hover:text-violet-700 underline"
        >
          Hide ICP
        </button>
      </div>
      <pre className="text-xs text-violet-900 whitespace-pre-wrap leading-relaxed font-sans">
        {icpText}
      </pre>
    </div>
  )
}

function StatsPreviewPanel({
  stats,
  filename,
  onClear,
}: {
  stats: PerformanceStatsContext
  filename?: string
  onClear: () => void
}) {
  const rows = [
    stats.industry && { label: 'Industry', value: stats.industry },
    stats.campaign_type && { label: 'Campaign', value: stats.campaign_type },
    stats.headline_stat && { label: 'Headline', value: stats.headline_stat },
    stats.roas && { label: 'ROAS', value: stats.roas },
    stats.roi && { label: 'ROI', value: stats.roi },
    stats.conversions && { label: 'Conversions', value: stats.conversions },
    stats.clicks && { label: 'Clicks', value: stats.clicks },
    stats.purchases_sales && { label: 'Sales', value: stats.purchases_sales },
    stats.cost && { label: 'Cost', value: stats.cost },
    stats.cost_per_conversion && { label: 'Cost / conv.', value: stats.cost_per_conversion },
    stats.timeline && { label: 'Timeline', value: stats.timeline },
  ].filter(Boolean) as { label: string; value: string }[]

  return (
    <div className="rounded-xl border-2 border-emerald-300 bg-emerald-50/80 p-3 mt-3">
      <div className="flex items-center justify-between gap-2 mb-2">
        <span className="text-xs font-bold text-emerald-800 uppercase tracking-wide">
          Stats from image {filename ? `· ${filename}` : ''}
        </span>
        <button
          type="button"
          onClick={onClear}
          className="text-xs text-emerald-700 hover:text-emerald-900 underline"
        >
          Remove
        </button>
      </div>
      {rows.length > 0 ? (
        <dl className="grid grid-cols-2 gap-x-3 gap-y-1 text-[11px]">
          {rows.map((row) => (
            <div key={row.label} className="contents">
              <dt className="text-emerald-700 font-semibold">{row.label}</dt>
              <dd className="text-emerald-950">{row.value}</dd>
            </div>
          ))}
        </dl>
      ) : (
        <p className="text-[11px] text-emerald-900 whitespace-pre-wrap">{stats.summary_for_script}</p>
      )}
      {stats.script_proof_lines.length > 0 && (
        <ul className="mt-2 space-y-1 text-[11px] text-emerald-900 list-disc list-inside">
          {stats.script_proof_lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
      <p className="text-[10px] text-emerald-700 mt-2">
        These figures will be used when you generate the script
        {filename?.includes('dashboard') ? ' (merged from all uploaded images)' : ''}.
      </p>
    </div>
  )
}

export default function AvatarScriptPanel({
  context,
  approvedScript,
  onApprovedScript,
  onScriptApproved,
  onExportSnapshotChange,
  preloadedStatsImageUrls,
  showApproveButton = true,
  onApproveStateChange,
}: AvatarScriptPanelProps) {
  const [scriptPrompt, setScriptPrompt] = useState('')
  const [sourceScript, setSourceScript] = useState('')
  const [convertLoading, setConvertLoading] = useState(false)
  const previewRef = useRef<HTMLDivElement>(null)
  const [preview, setPreview] = useState<AvatarScriptResult | null>(null)
  const [icpResult, setIcpResult] = useState<IcpScriptResult | null>(null)
  const [websiteResult, setWebsiteResult] = useState<WebsiteScriptResult | null>(null)
  const [showIcp, setShowIcp] = useState(false)
  const [showWebsiteInfo, setShowWebsiteInfo] = useState(false)
  const [manualEdit, setManualEdit] = useState(false)
  const [editedScript, setEditedScript] = useState('')
  const [loading, setLoading] = useState(false)
  const [icpLoading, setIcpLoading] = useState(false)
  const [websiteLoading, setWebsiteLoading] = useState(false)
  const [statsItems, setStatsItems] = useState<StatsImageItem[]>(() =>
    (preloadedStatsImageUrls ?? [])
      .filter(Boolean)
      .map((url) => ({
        id: newStatsItemId(),
        previewUrl: url,
        imageUrl: url,
      }))
  )
  const [statsLoading, setStatsLoading] = useState(false)
  const hasBriefNotes = Boolean(context.briefNotes?.trim())
  const isWebsiteMode = Boolean(context.websiteUrl?.trim())

  const statsImageUrls = useMemo(
    () => statsItems.map((item) => item.imageUrl).filter(Boolean) as string[],
    [statsItems]
  )
  const mergedPerformanceStats = useMemo(
    () => mergePerformanceStats(statsItems.map((item) => item.stats).filter(Boolean) as PerformanceStatsContext[]),
    [statsItems]
  )
  const performanceStatsPayload = mergedPerformanceStats ?? undefined
  const performanceStatsPerImage = useMemo(
    () =>
      statsItems
        .map((item) => item.stats)
        .filter(Boolean) as PerformanceStatsContext[],
    [statsItems]
  )

  const pushExportSnapshot = useCallback(
    (overrides?: {
      icpText?: string | null
      generatedFullScript?: string | null
      spokenScript?: string | null
      statsImageUrls?: string[]
      performanceStats?: PerformanceStatsContext | null
      performanceStatsPerImage?: PerformanceStatsContext[]
    }) => {
      if (!onExportSnapshotChange) return
      const full =
        overrides?.generatedFullScript ??
        ((manualEdit ? editedScript : scriptTextFromResult(preview)) || '')
      const urls = overrides?.statsImageUrls ?? statsImageUrls
      onExportSnapshotChange({
        icpText: overrides?.icpText ?? icpResult?.icp_text ?? null,
        generatedFullScript: full.trim() || null,
        spokenScript: overrides?.spokenScript ?? approvedScript,
        statsImageUrl: urls[0] ?? null,
        statsImageUrls: urls,
        performanceStats: overrides?.performanceStats ?? mergedPerformanceStats,
        performanceStatsPerImage:
          overrides?.performanceStatsPerImage ?? performanceStatsPerImage,
      })
    },
    [
      onExportSnapshotChange,
      manualEdit,
      editedScript,
      preview,
      icpResult,
      approvedScript,
      statsImageUrls,
      mergedPerformanceStats,
      performanceStatsPerImage,
    ]
  )

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
      // Only revoke blob: URLs — preloaded items use https URLs
      if (item?.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(item.previewUrl)
      return prev.filter((i) => i.id !== id)
    })
  }

  const clearAllStatsItems = () => {
    statsItems.forEach((item) => {
      if (item.previewUrl?.startsWith('blob:')) URL.revokeObjectURL(item.previewUrl)
    })
    setStatsItems([])
  }

  const runExtractStats = async () => {
    const pending = statsItems.filter((item) => !item.stats && item.file)
    if (pending.length === 0) {
      if (statsItems.length === 0) {
        toast.error('Choose one or more dashboard screenshots first')
      } else {
        toast.success('All images already extracted')
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
          console.error('extractStatsFromImage error:', item.file?.name, err)
          toast.error(
            extractApiError(err, `Could not read stats from ${item.file?.name ?? 'image'}`)
          )
        }
      }
      setStatsItems(updated)
      const merged = mergePerformanceStats(
        updated.map((i) => i.stats).filter(Boolean) as PerformanceStatsContext[]
      )
      const urls = updated.map((i) => i.imageUrl).filter(Boolean) as string[]
      pushExportSnapshot({ performanceStats: merged, statsImageUrls: urls })
      if (ok > 0) {
        toast.success(
          ok === 1
            ? 'Stats extracted — image will appear in video during proof beat'
            : `${ok} dashboard images extracted — all will appear in the video proof section`
        )
      }
    } finally {
      setStatsLoading(false)
    }
  }

  const applyScriptResult = (result: AvatarScriptResult, forceShow = false) => {
    const text = scriptTextFromResult(result)
    if (!text) {
      toast.error('Script came back empty — try again or edit manually')
      return false
    }
    if (!forceShow && looksLikeCreativeBrief(text)) {
      toast.error('AI returned brief directions — showing anyway, edit as needed')
    }
    setPreview(result)
    setEditedScript(text)
    return true
  }

  const runConvertSourceScript = async () => {
    if (!sourceScript.trim()) {
      toast.error('Paste your full script first')
      return
    }
    const targetSeconds = resolveTargetSecondsForConversion(
      sourceScript,
      context.targetSeconds
    )
    setConvertLoading(true)
    setManualEdit(false)
    toast.loading('Converting to voice script…', { id: 'convert-script' })
    try {
      const result = await generationApi.generateAvatarScript({
        purpose: 'avatar_script',
        source_script: sourceScript.trim(),
        script_prompt: scriptPrompt.trim() || undefined,
        product_name: context.productName,
        offer: context.offer,
        brand_name: context.brandName,
        target_audience: context.targetAudience,
        ad_copy_tone: context.adCopyTone,
        cta: context.cta,
        notes: context.briefNotes || undefined,
        target_seconds: targetSeconds,
        avatar_label: context.avatarLabel,
        voice_label: context.voiceLabel,
        forbidden_words: context.forbiddenWords,
        performance_stats: performanceStatsPayload,
        performance_stats_per_image: performanceStatsPerImage,
        stats_image_count: statsItems.filter((s) => s.imageUrl).length,
      })
      if (isPlaceholderScriptResult(result)) {
        toast.error(
          'AI returned a short placeholder — OpenRouter credits may be low. Add credits at openrouter.ai/settings/credits and try again.',
          { id: 'convert-script', duration: 10000 }
        )
        return
      }
      const ok = applyScriptResult(result, true)
      if (ok) {
        toast.success(
          targetSeconds !== context.targetSeconds
            ? `Voice script ready (${targetSeconds}s from your script) — scroll down to Approve`
            : 'Voice script ready — review below and Approve',
          { id: 'convert-script' }
        )
        requestAnimationFrame(() => {
          previewRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
        })
      } else {
        toast.error('Conversion returned empty — try again or edit manually', {
          id: 'convert-script',
        })
      }
    } catch (err) {
      console.error('convertSourceScript error:', err)
      toast.error(extractApiError(err, 'Could not convert script — is the backend running?'), {
        id: 'convert-script',
      })
    } finally {
      setConvertLoading(false)
    }
  }

  const runGenerate = async (variation: 'default' | 'different_hook' = 'default') => {
    setLoading(true)
    setManualEdit(false)
    try {
      const result = await generationApi.generateAvatarScript({
        purpose: 'avatar_script',
        script_prompt: scriptPrompt.trim() || undefined,
        source_script: sourceScript.trim() || undefined,
        product_name: context.productName,
        offer: context.offer,
        brand_name: context.brandName,
        target_audience: context.targetAudience,
        ad_copy_tone: context.adCopyTone,
        cta: context.cta,
        notes: context.briefNotes || undefined,
        target_seconds: context.targetSeconds,
        avatar_label: context.avatarLabel,
        voice_label: context.voiceLabel,
        forbidden_words: context.forbiddenWords,
        variation,
        performance_stats: performanceStatsPayload,
        performance_stats_per_image: performanceStatsPerImage,
        stats_image_count: statsItems.filter((s) => s.imageUrl).length,
      })
      applyScriptResult(result, true)
      toast.success('Spoken script generated — review and Approve')
    } catch (err) {
      console.error('generateAvatarScript error:', err)
      toast.error('Could not generate script — see console for details')
    } finally {
      setLoading(false)
    }
  }

  const runIcpGenerate = async (variation: 'default' | 'different_hook' = 'default') => {
    if (!context.targetAudience && !context.offer) {
      toast.error('Fill in Target Audience and Offer / Key Message first (Step 3 & 5).')
      return
    }
    setIcpLoading(true)
    setManualEdit(false)
    try {
      const result = await generationApi.generateIcpScript({
        target_audience: context.targetAudience,
        offer: context.offer,
        product_name: context.productName,
        brand_name: context.brandName,
        ad_copy_tone: context.adCopyTone,
        cta: context.cta,
        target_seconds: context.targetSeconds,
        avatar_label: context.avatarLabel,
        voice_label: context.voiceLabel,
        forbidden_words: context.forbiddenWords,
        variation,
        performance_stats: performanceStatsPayload,
        performance_stats_per_image: performanceStatsPerImage,
        stats_image_count: statsItems.filter((s) => s.imageUrl).length,
        source_script: sourceScript.trim() || undefined,
      })
      setIcpResult(result)
      setShowIcp(true)
      applyScriptResult(result.script, true)
      toast.success('ICP built + script generated — review and Approve')
    } catch (err) {
      console.error('generateIcpScript error:', err)
      toast.error('Could not generate ICP script — see console for details')
    } finally {
      setIcpLoading(false)
    }
  }

  const runWebsiteGenerate = async (variation: 'default' | 'different_hook' = 'default') => {
    if (!context.websiteUrl?.trim()) {
      toast.error('Enter a website URL in Step 2 first.')
      return
    }
    setWebsiteLoading(true)
    setManualEdit(false)
    try {
      const result = await generationApi.generateWebsiteScript({
        url: context.websiteUrl,
        target_seconds: context.targetSeconds,
        brand_name: context.brandName,
        product_name: context.productName,
        offer: context.offer,
        ad_copy_tone: context.adCopyTone,
        cta: context.cta,
        target_audience: context.targetAudience,
        avatar_label: context.avatarLabel,
        voice_label: context.voiceLabel,
        forbidden_words: context.forbiddenWords,
        variation,
        performance_stats: performanceStatsPayload,
        performance_stats_per_image: performanceStatsPerImage,
        stats_image_count: statsItems.filter((s) => s.imageUrl).length,
      })
      setWebsiteResult(result)
      setShowWebsiteInfo(true)
      applyScriptResult(result.script, true)
      toast.success(`Script written using "${result.framework_name}" framework`)
    } catch (err) {
      console.error('generateWebsiteScript error:', err)
      toast.error('Could not fetch the website or generate script — check the URL and try again')
    } finally {
      setWebsiteLoading(false)
    }
  }

  const generatedScript = scriptTextFromResult(preview).trim()
  const readableScript = (manualEdit ? editedScript : generatedScript || approvedScript || '').trim()
  const showPreview = Boolean(preview || approvedScript || manualEdit)

  const startManualEdit = () => {
    setEditedScript(generatedScript || approvedScript || editedScript || '')
    setManualEdit(true)
  }

  const scriptForApprove = (manualEdit ? editedScript : generatedScript || approvedScript || '').trim()

  const canApprove = Boolean(
    scriptForApprove &&
      !looksLikeCreativeBrief(scriptForApprove) &&
      (preview || manualEdit || hasTimedScriptLines(scriptForApprove))
  )

  const isAnyLoading = loading || icpLoading || websiteLoading || statsLoading || convertLoading

  const handleApprove = useCallback(() => {
    if (!canApprove) {
      toast.error(
        'Generate a spoken script first (brief notes alone are not sent to HeyGen)'
      )
      return
    }
    const fullForExport = manualEdit
      ? editedScript
      : scriptTextFromResult(preview) || scriptForApprove
    const plainForHeyGen = hasTimedScriptLines(fullForExport)
      ? spokenTextFromTimedScript(fullForExport) || fullForExport
      : fullForExport
    // Store full timed script on brief — keeps proof-beat timing for stats images
    onApprovedScript(fullForExport.trim())
    pushExportSnapshot({
      generatedFullScript: fullForExport.trim(),
      spokenScript: plainForHeyGen.trim(),
      icpText: icpResult?.icp_text ?? null,
    })
    toast.success(
      'Script approved — now click Create & Generate Video in the sidebar (right) →',
      { duration: 8000 }
    )
    onScriptApproved?.(fullForExport.trim())
  }, [
    canApprove,
    manualEdit,
    editedScript,
    preview,
    scriptForApprove,
    onApprovedScript,
    pushExportSnapshot,
    icpResult,
    onScriptApproved,
  ])

  // Expose approve availability + a stable handler so the parent can render the
  // Approve button AFTER the master-script timeline preview.
  const approveRef = useRef(handleApprove)
  approveRef.current = handleApprove
  const stableApprove = useCallback(() => approveRef.current(), [])
  const editRef = useRef(startManualEdit)
  editRef.current = startManualEdit
  const stableEdit = useCallback(() => editRef.current(), [])
  useEffect(() => {
    onApproveStateChange?.({ canApprove, approve: stableApprove, edit: stableEdit })
  }, [canApprove, stableApprove, stableEdit, onApproveStateChange])

  return (
    <div className="rounded-xl border-2 border-sky-200 bg-white p-4 shadow-sm relative">
      <span className="absolute top-3 right-3 flex h-6 w-6 items-center justify-center rounded-full bg-teal text-[11px] font-bold text-white">
        8
      </span>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-2 pr-8">
        <h3 className="text-sm font-bold text-sky-700">
          Avatar Script — spoken lines for HeyGen
        </h3>
        <div className="flex flex-wrap gap-2">
          {isWebsiteMode ? (
            <Button
              type="button"
              size="sm"
              variant="primary"
              isLoading={websiteLoading}
              disabled={isAnyLoading}
              onClick={() => void runWebsiteGenerate('default')}
              title="Fetches your website and generates a framework-based script"
            >
              Generate from website
            </Button>
          ) : (
            <Button
              type="button"
              size="sm"
              variant="primary"
              isLoading={icpLoading}
              disabled={isAnyLoading}
              onClick={() => void runIcpGenerate('default')}
              title="Builds an ICP profile from your Target Audience + Offer, then writes the script"
            >
              Generate script using ICP
            </Button>
          )}
          <Button
            type="button"
            size="sm"
            variant="outline"
            isLoading={loading}
            disabled={isAnyLoading}
            onClick={() => void runGenerate('default')}
          >
            Generate spoken script
          </Button>
        </div>
      </div>

      <p className="text-[11px] text-mid mb-2 rounded-lg bg-sky-50 border border-sky-200/80 px-3 py-2 text-sky-900">
        Scripts are written in <strong>Australian English</strong> — natural Aussie accent, spelling, and
        phrasing (not American). Regenerate after changing audience or offer.
      </p>

      <p className="text-[11px] text-mid mb-2 rounded-lg bg-violet-50 border border-violet-200/80 px-3 py-2 text-violet-900">
        <strong>Generate script using ICP</strong> builds a buyer profile from your{' '}
        <strong>Target Audience</strong> and <strong>Offer</strong> fields, then writes dialogue
        that speaks directly to that avatar's pain and desire.
      </p>

      <p className="text-[11px] text-mid mb-3 rounded-lg bg-amber-50 border border-amber-200/80 px-3 py-2 text-amber-950">
        <strong>Step 5 above</strong> only saves creative brief notes (ideas for writers). They are{' '}
        <strong>not</strong> what the avatar says. Use this section to generate real dialogue, then{' '}
        <strong>Approve &amp; send to HeyGen</strong>.
      </p>

      <div className="mb-4 rounded-xl border-2 border-indigo-300 bg-indigo-50/50 p-3 space-y-3">
        <div>
          <p className="text-xs font-bold text-indigo-800 uppercase tracking-wide mb-1">
            Paste full script → voice script
          </p>
          <p className="text-[11px] text-indigo-900 mb-2">
            Paste your written script (Hook, Problem, Proof, Guarantee, CTA). Section headers and{' '}
            <code className="text-[10px] bg-white/80 px-1 rounded">[INSERT … STAT IMAGE]</code> lines
            are stripped — upload stats images below for video visuals.
          </p>
        </div>
        <TextArea
          rows={10}
          value={sourceScript}
          onChange={(e) => setSourceScript(e.target.value)}
          placeholder={`Variation 1 - Main Script\nHook\nIf your ecommerce brand is doing over $100,000 a month...\nProblem\nMost ecommerce brands are not stuck because...\nProof\nAt ClickTrends, we helped one client...\n[INSERT ClickTrends_ecommerce STAT IMAGE]\nCTA\nBook your consultation today.`}
          className="font-mono text-xs"
        />
        <div className="flex flex-wrap gap-2 items-center">
          <Button
            type="button"
            size="sm"
            variant="primary"
            isLoading={convertLoading}
            disabled={!sourceScript.trim() || convertLoading}
            onClick={() => void runConvertSourceScript()}
          >
            Convert to voice script
          </Button>
          {sourceScript.trim() ? (
            <button
              type="button"
              className="text-xs text-indigo-600 underline hover:text-indigo-800"
              onClick={() => setSourceScript('')}
            >
              Clear pasted script
            </button>
          ) : null}
        </div>
        {convertLoading ? (
          <p className="text-[11px] text-indigo-800 bg-indigo-100/80 rounded-lg px-3 py-2">
            Converting your script to timed voice lines… this can take 15–30 seconds for long
            scripts.
          </p>
        ) : null}
        {inferTargetSecondsFromSourceScript(sourceScript, context.targetSeconds) !==
        context.targetSeconds ? (
          <p className="text-[10px] text-indigo-700">
            Script mentions{' '}
            <strong>
              {inferTargetSecondsFromSourceScript(sourceScript, context.targetSeconds)}s
            </strong>
            ; converting for{' '}
            <strong>
              {resolveTargetSecondsForConversion(sourceScript, context.targetSeconds)}s
            </strong>{' '}
            (your video length setting).
          </p>
        ) : null}
      </div>

      {showPreview && (
        <div
          ref={previewRef}
          className="rounded-lg bg-slate-900 p-4 border border-slate-700 mt-2 mb-4 scroll-mt-24"
        >
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3 border-b border-slate-600 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wide text-teal">
              {manualEdit ? 'Editing spoken script' : 'Spoken script preview'} ·{' '}
              {preview?.model_label ?? 'Claude Sonnet 4.6'}
            </span>
            {preview && !manualEdit && (
              <span className="text-[10px] text-slate-400">
                {preview.word_count} words · ~ {Math.round(preview.estimated_seconds)} seconds @{' '}
                {preview.words_per_second} wps
              </span>
            )}
          </div>

          {manualEdit ? (
            <textarea
              value={editedScript}
              onChange={(e) => setEditedScript(e.target.value)}
              rows={10}
              spellCheck
              className="w-full min-h-[200px] px-3 py-2 rounded-lg border border-slate-600 bg-slate-800 text-white text-sm font-mono leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-teal/50 placeholder:text-slate-500"
              placeholder="Paste or type what the avatar says, with [00:00 - 00:05] timestamps optional…"
            />
          ) : (
            <div className="text-sm leading-relaxed text-slate-100 font-mono whitespace-pre-wrap max-h-80 overflow-y-auto">
              {(preview?.lines ?? []).length > 1 ? (
                preview!.lines.map((line) => (
                  <p key={`${line.start}-${line.end}`} className="mb-2">
                    <span className="text-amber-300 font-semibold">
                      [{line.start} - {line.end}]
                    </span>{' '}
                    <span className="text-slate-100">{line.text}</span>
                  </p>
                ))
              ) : (
                <p className="text-slate-100">{readableScript}</p>
              )}
            </div>
          )}

          {!manualEdit && preview?.validations && preview.validations.length > 0 && (
            <ul className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-slate-600">
              {preview.validations.map((v) => (
                <li
                  key={v.id}
                  className={`text-[10px] font-semibold px-2 py-1 rounded-full ${
                    v.status === 'ok'
                      ? 'bg-emerald-900/60 text-emerald-200'
                      : 'bg-amber-900/60 text-amber-100'
                  }`}
                >
                  {v.status === 'ok' ? '✓' : '⚠'} {v.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      <div className="mb-4 rounded-xl border-2 border-dashed border-emerald-300 bg-emerald-50/40 p-3 space-y-3">
        <div>
          <p className="text-xs font-bold text-emerald-800 uppercase tracking-wide mb-1">
            Performance stats images (optional)
          </p>
          <p className="text-[11px] text-emerald-900 mb-2">
            Upload dashboard screenshots, then click <strong>Re-extract stats</strong> before
            generating your voice script. Numbers from OCR are woven into the proof beat; B-roll and
            stats image timing follow the same approved script.
          </p>
          {statsItems.some((item) => !item.stats) && statsItems.length > 0 && (
            <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-2 py-1.5 mb-2">
              Images marked <strong>PENDING</strong> — click <strong>Re-extract stats</strong> so
              the voice script cites your real ROAS/conversion numbers (not generic text).
            </p>
          )}
        </div>

        {statsItems.length > 0 ? (
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
            {statsItems.map((item) => (
              <div
                key={item.id}
                className="relative rounded-lg border border-emerald-200 bg-white p-1.5"
              >
                <img
                  src={item.previewUrl}
                  alt={item.file?.name ?? 'Stats image'}
                  className="w-full h-24 object-contain rounded"
                />
                <p className="text-[10px] text-emerald-900 truncate mt-1 px-0.5" title={item.file?.name ?? item.imageUrl ?? ''}>
                  {item.file?.name ?? 'Saved image'}
                </p>
                {item.stats ? (
                  <span className="absolute top-1.5 left-1.5 text-[9px] font-bold uppercase bg-emerald-600 text-white px-1.5 py-0.5 rounded">
                    Ready
                  </span>
                ) : (
                  <span className="absolute top-1.5 left-1.5 text-[9px] font-bold uppercase bg-amber-500 text-white px-1.5 py-0.5 rounded">
                    Pending
                  </span>
                )}
                <button
                  type="button"
                  onClick={() => removeStatsItem(item.id)}
                  className="absolute top-1 right-1 h-5 w-5 rounded-full bg-white/90 text-emerald-800 text-xs font-bold border border-emerald-200 hover:bg-red-50 hover:text-red-700"
                  title="Remove image"
                >
                  ×
                </button>
              </div>
            ))}
          </div>
        ) : null}

        <div className="flex flex-wrap gap-2 items-center">
          <input
            type="file"
            accept="image/png,image/jpeg,image/webp"
            multiple
            className="text-xs w-full file:mr-2 file:py-1.5 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-semibold file:bg-emerald-600 file:text-white"
            onChange={(e) => {
              addStatsFiles(e.target.files)
              e.target.value = ''
            }}
          />
          <Button
            type="button"
            size="sm"
            variant="outline"
            isLoading={statsLoading}
            disabled={statsItems.length === 0 || statsLoading}
            onClick={() => void runExtractStats()}
          >
            {statsItems.some((i) => !i.stats)
              ? 'Extract stats from images'
              : 'Re-extract stats'}
          </Button>
          {statsItems.length > 0 ? (
            <button
              type="button"
              className="text-xs text-emerald-700 underline hover:text-emerald-900"
              onClick={clearAllStatsItems}
            >
              Clear all ({statsItems.length})
            </button>
          ) : null}
        </div>

        {mergedPerformanceStats && (
          <StatsPreviewPanel
            stats={mergedPerformanceStats}
            filename={
              statsItems.length > 1
                ? `${statsItems.length} dashboards`
                : statsItems[0]?.file?.name
            }
            onClear={clearAllStatsItems}
          />
        )}
      </div>

      {hasBriefNotes && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <p className="text-[11px] text-mid flex-1 min-w-[200px]">
            Brief notes from step 5 are used as context when you generate — they will not
            auto-fill this box.
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={isAnyLoading}
            onClick={() => void runGenerate('default')}
          >
            Write script from brief notes
          </Button>
        </div>
      )}

      <TextArea
        label="Optional prompt (tone or angle — not the final script)"
        rows={3}
        value={scriptPrompt}
        onChange={(e) => setScriptPrompt(e.target.value)}
        placeholder="e.g. Friendly expert tone, mention free audit, end with Book a call."
      />

      {/* ICP preview panel */}
      {icpResult && showIcp && (
        <IcpPreviewPanel icpText={icpResult.icp_text} onClose={() => setShowIcp(false)} />
      )}
      {icpResult && !showIcp && (
        <button
          type="button"
          className="text-xs text-violet-600 hover:text-violet-800 underline mt-2 block"
          onClick={() => setShowIcp(true)}
        >
          View ICP profile used for this script
        </button>
      )}

      {/* Website script info banner */}
      {websiteResult && (
        <div className="mt-2 rounded-xl border border-emerald-200 bg-emerald-50/70 px-3 py-2">
          <div className="flex items-center justify-between gap-2">
            <div>
              <p className="text-[10px] font-bold text-emerald-700 uppercase tracking-wide">
                Website script · {websiteResult.framework_name}
              </p>
              <p className="text-[11px] text-emerald-800 mt-0.5 truncate max-w-[340px]">
                {websiteResult.page_title || websiteResult.url}
              </p>
            </div>
            <button
              type="button"
              className="text-[11px] text-emerald-600 underline hover:text-emerald-800 shrink-0"
              onClick={() => setShowWebsiteInfo((v) => !v)}
            >
              {showWebsiteInfo ? 'Hide' : 'Details'}
            </button>
          </div>
          {showWebsiteInfo && websiteResult.page_description && (
            <p className="text-[11px] text-emerald-800 mt-1.5 border-t border-emerald-200 pt-1.5">
              {websiteResult.page_description}
            </p>
          )}
        </div>
      )}

      {!showPreview && (
        <p className="text-[11px] text-mid mt-3">
          Click <strong>Generate script using ICP</strong> (recommended) or{' '}
          <strong>Generate spoken script</strong>, then <strong>Approve</strong>. HeyGen uses this
          exact dialogue — B-roll and text cuts are synced to what the avatar says in each beat.
        </p>
      )}

      <div className="flex flex-wrap gap-2 mt-4">
        {manualEdit ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setManualEdit(false)
              if (preview) {
                setPreview({ ...preview, full_script: editedScript })
              }
              toast.success('Edits saved to preview')
            }}
          >
            Done editing
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!readableScript}
            onClick={startManualEdit}
          >
            Edit manually
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isAnyLoading}
          onClick={() =>
            isWebsiteMode
              ? void runWebsiteGenerate('default')
              : icpResult
                ? void runIcpGenerate('default')
                : void runGenerate('default')
          }
        >
          {isWebsiteMode ? 'Regenerate from website' : icpResult ? 'Regenerate with ICP' : 'Regenerate'}
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={isAnyLoading}
          onClick={() =>
            isWebsiteMode
              ? void runWebsiteGenerate('different_hook')
              : icpResult
                ? void runIcpGenerate('different_hook')
                : void runGenerate('different_hook')
          }
        >
          Try different hook
        </Button>
        {showApproveButton && (
          <Button
            type="button"
            variant="primary"
            size="sm"
            className="ml-auto"
            disabled={!canApprove}
            onClick={handleApprove}
          >
            Approve &amp; send to HeyGen →
          </Button>
        )}
      </div>

      {!showApproveButton && !approvedScript && (
        <p className="mt-3 text-xs text-slate-500">
          Review the <strong>Master Script</strong> timeline below, then click{' '}
          <strong>Approve &amp; send to HeyGen</strong> under it.
        </p>
      )}

      {approvedScript && (
        <div className="mt-3 rounded-xl border-2 border-teal-400 bg-teal-50 px-4 py-3 space-y-1">
          <p className="text-sm font-bold text-teal-900">
            ✓ Script approved ({approvedScript.split(/\s+/).filter(Boolean).length} words)
          </p>
          <p className="text-xs text-teal-800">
            This dialogue will be sent to HeyGen. <strong>Approve does not start the video</strong>{' '}
            — scroll to the <strong>right sidebar</strong> and click{' '}
            <strong>Create &amp; Generate Video</strong> to render your ad (takes several minutes).
          </p>
        </div>
      )}
    </div>
  )
}
