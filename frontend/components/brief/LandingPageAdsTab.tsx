'use client'

import { useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import { extractApiError } from '@/lib/apiErrors'
import {
  landingPageAdsApi,
  type LandingPageAdJob,
  type LandingPageReference,
} from '@/lib/landingPageAdsApi'
import { assetUrl } from '@/lib/utils'

type Props = {
  brandId?: string
  brandName?: string
  imageModel?: string
}

const TERMINAL = new Set(['completed', 'partial', 'failed'])
const MONTHLY_TARGET = 150
const RUN_SIZE_OPTIONS = [1, 3, 5, 15] as const
const SIZE_OPTIONS = [
  { id: '4:5', label: '4:5 Portrait', dimensions: '1080x1350' },
  { id: '1:1', label: '1:1 Square', dimensions: '1080x1080' },
  { id: '9:16', label: '9:16 Vertical', dimensions: '1080x1920' },
  { id: '16:9', label: '16:9 Landscape', dimensions: '1200x675' },
  { id: '1.91:1', label: '1.91:1 Wide', dimensions: '1200x628' },
] as const

const SERVICE_OPTIONS = ['Brand / General', 'E-commerce', 'Lead generation', 'Local services', 'SaaS']

export default function LandingPageAdsTab({ brandId, brandName, imageModel = 'openai-gpt-image-2.6-sunburst' }: Props) {
  const [landingPageUrl, setLandingPageUrl] = useState('')
  const [service, setService] = useState('Brand / General')
  const [notes, setNotes] = useState('')
  const [existingCopy, setExistingCopy] = useState('')
  const [sizeId, setSizeId] = useState<(typeof SIZE_OPTIONS)[number]['id']>('4:5')
  const [adCount, setAdCount] = useState<(typeof RUN_SIZE_OPTIONS)[number]>(1)
  const [view, setView] = useState<'new' | 'history'>('new')
  const [history, setHistory] = useState<LandingPageAdJob[]>([])
  const [files, setFiles] = useState<File[]>([])
  const [references, setReferences] = useState<LandingPageReference[]>([])
  const [job, setJob] = useState<LandingPageAdJob | null>(null)
  const [busy, setBusy] = useState(false)
  const [revision, setRevision] = useState<Record<number, string>>({})
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const restoredLatestRef = useRef(false)

  const isRunning = Boolean(job && !TERMINAL.has(job.status))
  const acceptedFiles = useMemo(() => files.slice(0, 8), [files])
  const selectedSize = SIZE_OPTIONS.find((item) => item.id === sizeId) || SIZE_OPTIONS[0]
  const monthlyCreated = useMemo(() => {
    const now = new Date()
    return history
      .filter((item) => {
        const created = item.created_at ? new Date(item.created_at) : null
        return created && created.getFullYear() === now.getFullYear() && created.getMonth() === now.getMonth()
      })
      .reduce((sum, item) => sum + (item.assets?.length || 0), 0)
  }, [history])

  const refreshHistory = async (restoreLatest = false) => {
    try {
      const items = await landingPageAdsApi.listJobs()
      setHistory(items)
      if (restoreLatest && !restoredLatestRef.current && items[0]) {
        restoredLatestRef.current = true
        setJob(items[0])
        setLandingPageUrl(items[0].request?.landing_page_url || '')
      }
    } catch (error) {
      toast.error(extractApiError(error))
    }
  }

  useEffect(() => {
    void refreshHistory(true)
  }, [])

  const startNewSession = () => {
    restoredLatestRef.current = true
    setJob(null)
    setView('new')
    setLandingPageUrl('')
    setNotes('')
    setExistingCopy('')
    setFiles([])
    setReferences([])
    setRevision({})
  }

  const openSession = (item: LandingPageAdJob) => {
    restoredLatestRef.current = true
    setJob(item)
    setLandingPageUrl(item.request?.landing_page_url || '')
    setView('new')
  }

  useEffect(() => {
    if (!job?.id || TERMINAL.has(job.status)) return
    const poll = async () => {
      try {
        const next = await landingPageAdsApi.getJob(job.id)
        setJob(next)
        if (TERMINAL.has(next.status) && pollRef.current) {
          clearInterval(pollRef.current)
          pollRef.current = null
          void refreshHistory()
        }
      } catch (error) {
        if (pollRef.current) clearInterval(pollRef.current)
        pollRef.current = null
        toast.error(extractApiError(error))
      }
    }
    pollRef.current = setInterval(poll, 1800)
    void poll()
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
      pollRef.current = null
    }
  }, [job?.id, job?.status])

  const generate = async () => {
    if (!landingPageUrl.trim().startsWith('https://')) {
      toast.error('Enter a public HTTPS landing-page URL')
      return
    }
    setBusy(true)
    try {
      let uploaded = references
      if (acceptedFiles.length) {
        uploaded = await landingPageAdsApi.uploadReferences(acceptedFiles, brandId)
        setReferences(uploaded)
      }
      const created = await landingPageAdsApi.createJob({
        landing_page_url: landingPageUrl.trim(),
        user_prompt: [
          `Create ${adCount} static ad variation${adCount === 1 ? '' : 's'} at ${selectedSize.dimensions} (${selectedSize.label}).`,
          `Service category: ${service}.`,
          'Each creative must use a different hook and visual angle. Supporting body copy may be reused where appropriate.',
          'Use the landing page only as factual evidence. Do not invent claims, prices, statistics, testimonials or certifications.',
          notes.trim() ? `Offer, audience and proof notes: ${notes.trim()}` : '',
          existingCopy.trim() ? `Existing approved ad copy to reuse or adapt: ${existingCopy.trim()}` : '',
        ].filter(Boolean).join('\n'),
        reference_asset_ids: uploaded.map((item) => item.id),
        brand_id: brandId || undefined,
        image_model: imageModel,
      })
      setJob(created)
      toast.success('Landing page accepted. Building the evidence-grounded ad plan.')
    } catch (error) {
      toast.error(extractApiError(error))
    } finally {
      setBusy(false)
    }
  }

  const regenerate = async (slideIndex: number) => {
    const note = (revision[slideIndex] || '').trim()
    if (!job?.id || !note) {
      toast.error('Add a revision note for this slide')
      return
    }
    setBusy(true)
    try {
      await landingPageAdsApi.revise(job.id, {
        user_prompt: note,
        target_slide_indexes: [slideIndex],
      })
      setJob({ ...job, status: 'queued', phase: 'revision_queued' })
      toast.success(`Slide ${slideIndex} queued for regeneration`)
    } catch (error) {
      toast.error(extractApiError(error))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="w-full max-w-[1600px] mx-auto p-6 md:p-8 space-y-5">
      <section className="rounded-2xl border border-border bg-white shadow-sm p-5 md:p-6 space-y-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 className="text-xl font-bold text-charcoal">Bulk Ad Run</h2>
            <p className="mt-1 text-sm text-mid">
              Create 1 test ad or a bulk run: every hook uses a different angle, while approved body copy may be reused.
            </p>
          </div>
          <div className="flex flex-wrap gap-2 text-xs">
            <span className="rounded-full border border-border bg-soft/50 px-3 py-1 font-semibold text-charcoal">
              {brandName || 'Landing-page brand'}
            </span>
            <span className="rounded-full border border-accent/25 bg-accent/10 px-3 py-1 font-semibold text-accent">
              Up to 15 creatives
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-soft/30 p-4 space-y-2">
          <div className="flex items-center justify-between gap-3 text-xs">
            <span className="font-semibold text-charcoal">This month&apos;s target</span>
            <span className="text-mid">{monthlyCreated} / {MONTHLY_TARGET} images</span>
          </div>
          <div className="h-2 overflow-hidden rounded-full bg-white border border-border/60">
            <div className="h-full rounded-full bg-accent transition-all" style={{ width: `${Math.min(100, (monthlyCreated / MONTHLY_TARGET) * 100)}%` }} />
          </div>
          <p className="text-[11px] text-mid">
            Counts finished assets created by this landing-page workflow in the current month.
          </p>
        </div>

        <div className="inline-flex rounded-xl border border-border bg-soft/40 p-1">
          <button type="button" onClick={startNewSession} className={`rounded-lg px-3 py-2 text-xs font-semibold ${view === 'new' && !job ? 'bg-white text-charcoal shadow-sm' : 'text-mid'}`}>
            + New session
          </button>
          <button type="button" onClick={() => { setView('history'); void refreshHistory() }} className={`rounded-lg px-3 py-2 text-xs font-semibold ${view === 'history' ? 'bg-white text-charcoal shadow-sm' : 'text-mid'}`}>
            History ({history.length})
          </button>
        </div>

        {view === 'new' ? (
          <div className="space-y-5">
            <div className="grid gap-4 lg:grid-cols-2">
              <label className="space-y-1.5 text-sm font-semibold text-charcoal">
                Landing-page URL
                <input type="url" value={landingPageUrl} onChange={(event) => setLandingPageUrl(event.target.value)} placeholder="https://example.com/product" className="w-full rounded-xl border border-border bg-white px-3.5 py-3 text-sm font-normal outline-none focus:border-accent" />
              </label>
              <label className="space-y-1.5 text-sm font-semibold text-charcoal">
                Service
                <select value={service} onChange={(event) => setService(event.target.value)} className="w-full rounded-xl border border-border bg-white px-3.5 py-3 text-sm font-normal outline-none focus:border-accent">
                  {SERVICE_OPTIONS.map((option) => <option key={option}>{option}</option>)}
                </select>
              </label>
            </div>

            <label className="block space-y-1.5 text-sm font-semibold text-charcoal">
              Notes on the offer, audience and proof <span className="font-normal text-mid">(optional)</span>
              <textarea value={notes} onChange={(event) => setNotes(event.target.value)} rows={3} className="w-full resize-y rounded-xl border border-border bg-white px-3.5 py-3 text-sm font-normal outline-none focus:border-accent" placeholder="Who it is for, what they struggle with, results you can back up, and anything to avoid saying…" />
            </label>

            <label className="block space-y-1.5 text-sm font-semibold text-charcoal">
              Existing approved ad copy to build the bodies from <span className="font-normal text-mid">(optional)</span>
              <textarea value={existingCopy} onChange={(event) => setExistingCopy(event.target.value)} rows={3} className="w-full resize-y rounded-xl border border-border bg-white px-3.5 py-3 text-sm font-normal outline-none focus:border-accent" placeholder="Paste approved copy that already works. Hooks will vary while body copy may be reused." />
            </label>

            <div className="space-y-2">
              <p className="text-sm font-semibold text-charcoal">Run size</p>
              <div className="flex flex-wrap gap-2">
                {RUN_SIZE_OPTIONS.map((count) => (
                  <button key={count} type="button" onClick={() => setAdCount(count)} className={`rounded-full border px-3 py-2 text-xs font-semibold transition-colors ${adCount === count ? 'border-accent bg-accent/10 text-accent' : 'border-border bg-white text-mid hover:text-charcoal'}`}>
                    {count === 1 ? '1 test ad' : `${count} ads`}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-mid">Start with one test ad before spending credits on a full bulk run.</p>
            </div>

            <div className="space-y-2">
              <p className="text-sm font-semibold text-charcoal">Image size</p>
              <div className="flex flex-wrap gap-2">
                {SIZE_OPTIONS.map((option) => (
                  <button key={option.id} type="button" onClick={() => setSizeId(option.id)} className={`rounded-full border px-3 py-2 text-xs font-semibold transition-colors ${sizeId === option.id ? 'border-accent bg-accent/10 text-accent' : 'border-border bg-white text-mid hover:text-charcoal'}`}>
                    {option.label}
                  </button>
                ))}
              </div>
              <p className="text-[11px] text-mid">Selected output: {selectedSize.dimensions}</p>
            </div>

            <div className="rounded-xl border border-dashed border-border bg-soft/40 p-4">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="text-sm font-semibold text-charcoal">Optional product or visual references</p>
                  <p className="text-xs text-mid">PNG, JPG or WebP · up to 8 files · 10 MB each</p>
                </div>
                <label className="cursor-pointer rounded-lg border border-border bg-white px-3 py-2 text-sm font-semibold text-charcoal hover:border-accent">
                  Choose images
                  <input type="file" accept="image/png,image/jpeg,image/webp" multiple className="hidden" onChange={(event) => setFiles(Array.from(event.target.files || []).slice(0, 8))} />
                </label>
              </div>
              {acceptedFiles.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {acceptedFiles.map((file) => <span key={`${file.name}-${file.size}`} className="rounded-full bg-white border border-border px-2.5 py-1 text-xs text-mid">{file.name}</span>)}
                </div>
              )}
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button type="button" onClick={generate} disabled={busy || isRunning}>
                {busy || isRunning ? 'Creating ads…' : adCount === 1 ? 'Create test ad' : `Create ${adCount} ads`}
              </Button>
              <p className="text-xs text-mid">Uses {adCount} image generation{adCount === 1 ? '' : 's'} · model: <strong>{imageModel}</strong></p>
            </div>
          </div>
        ) : (
          <div className="overflow-hidden rounded-xl border border-border">
            {history.length === 0 ? (
              <p className="p-5 text-sm text-mid">No bulk runs yet.</p>
            ) : history.map((item) => (
              <button key={item.id} type="button" onClick={() => openSession(item)} className="flex w-full items-center justify-between gap-4 border-b border-border px-4 py-3 text-left last:border-b-0 hover:bg-soft/40">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-charcoal">{item.analysis?.title || item.request?.landing_page_url || 'Landing-page ad run'}</p>
                  <p className="mt-0.5 text-xs text-mid">{item.created_at ? new Date(item.created_at).toLocaleString() : 'Date unavailable'} · {item.assets?.length || 0} images</p>
                </div>
                <span className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${item.status === 'completed' ? 'bg-green-50 text-green-700' : item.status === 'failed' ? 'bg-red-50 text-red-700' : 'bg-amber-50 text-amber-700'}`}>{item.status}</span>
              </button>
            ))}
          </div>
        )}
      </section>

      {job && (
        <section className="rounded-2xl border border-border bg-white shadow-sm p-5 md:p-6 space-y-5">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <p className="text-xs font-bold uppercase tracking-wider text-accent">{job.phase?.replaceAll('_', ' ')}</p>
              <h3 className="mt-1 text-base font-bold text-charcoal">
                {job.analysis?.title || 'Landing-page ad production'}
              </h3>
              <p className="mt-1 text-xs text-mid">
                {job.request?.landing_page_url || job.analysis?.final_url || 'Landing page'}
                {job.created_at ? ` · ${new Date(job.created_at).toLocaleString()}` : ''}
                {job.brief_id ? ' · One shared brief' : ''}
              </p>
            </div>
            <div className="flex items-center gap-3 text-xs text-mid">
              {job.progress && <span>{job.progress.completed_assets}/{job.progress.total_assets} assets</span>}
              {job.download_all_url && (
                <a href={assetUrl(job.download_all_url) || undefined} download className="rounded-lg bg-charcoal px-3 py-2 font-semibold text-white">
                  Download ZIP
                </a>
              )}
            </div>
          </div>

          {isRunning && (
            <div className="h-2 overflow-hidden rounded-full bg-soft">
              <div
                className="h-full rounded-full bg-accent transition-all"
                style={{
                  width: `${Math.max(12, job.progress?.total_assets ? (job.progress.completed_assets / job.progress.total_assets) * 100 : 22)}%`,
                }}
              />
            </div>
          )}

          {job.error && <div className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">{job.error}</div>}
          {job.warnings?.map((warning) => (
            <div key={warning} className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-xs text-amber-800">{warning}</div>
          ))}

          {job.resolved_brief && (
            <div className="flex flex-wrap gap-2 text-xs text-mid">
              <span className="rounded-full border border-border px-2.5 py-1">{job.resolved_brief.format}</span>
              <span className="rounded-full border border-border px-2.5 py-1">{job.resolved_brief.ratio}</span>
              <span className="rounded-full border border-border px-2.5 py-1">{job.resolved_brief.width}×{job.resolved_brief.height}</span>
              <span className="rounded-full border border-border px-2.5 py-1">{job.resolved_brief.asset_count} images</span>
              <span className="rounded-full border border-border px-2.5 py-1">{job.resolved_brief.platform}</span>
            </div>
          )}

          {job.analysis?.evidence && job.analysis.evidence.length > 0 && (
            <details className="rounded-xl border border-border p-3">
              <summary className="cursor-pointer text-sm font-semibold text-charcoal">Evidence found on the page</summary>
              <ul className="mt-2 space-y-1 text-xs text-mid">
                {job.analysis.evidence.slice(0, 12).map((item) => <li key={item.id}>• {item.text || item.excerpt}</li>)}
              </ul>
            </details>
          )}

          {job.assets && job.assets.length > 0 && (
            <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-3">
              {job.assets.map((asset) => (
                <article key={`${asset.variant_id}-${asset.slide_index}`} className="overflow-hidden rounded-2xl border border-border bg-soft/20">
                  <a href={assetUrl(asset.preview_url) || undefined} target="_blank" rel="noreferrer" title="View full-size image">
                    <img src={assetUrl(asset.preview_url) || undefined} alt={asset.headline || `Slide ${asset.slide_index}`} className="aspect-square w-full bg-white object-contain" />
                  </a>
                  <div className="space-y-3 p-4">
                    <div>
                      <p className="text-[10px] font-bold uppercase tracking-wider text-accent">Slide {asset.slide_index} · {asset.role}</p>
                      <h4 className="mt-1 text-sm font-bold text-charcoal">{asset.headline}</h4>
                    </div>
                    <div className="flex items-center gap-4">
                      <a href={assetUrl(asset.preview_url) || undefined} target="_blank" rel="noreferrer" className="inline-flex text-xs font-semibold text-charcoal hover:underline">View image</a>
                      <a href={assetUrl(asset.download_url) || undefined} download className="inline-flex text-xs font-semibold text-accent hover:underline">Download PNG</a>
                    </div>
                    <div className="flex gap-2">
                      <input
                        value={revision[asset.slide_index] || ''}
                        onChange={(event) => setRevision((prev) => ({ ...prev, [asset.slide_index]: event.target.value }))}
                        placeholder="Revision note for this slide"
                        className="min-w-0 flex-1 rounded-lg border border-border px-2.5 py-2 text-xs outline-none focus:border-accent"
                      />
                      <button type="button" onClick={() => regenerate(asset.slide_index)} disabled={busy || isRunning} className="rounded-lg border border-border bg-white px-3 py-2 text-xs font-semibold text-charcoal disabled:opacity-50">
                        Retry
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            </div>
          )}
        </section>
      )}
    </div>
  )
}
