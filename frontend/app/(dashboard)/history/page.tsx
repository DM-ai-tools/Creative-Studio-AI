'use client'

import React, { useMemo, useState } from 'react'
import Link from 'next/link'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import Modal from '@/components/ui/Modal'
import { ChipToggle } from '@/components/ui/ChipToggle'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { brandsApi, briefsApi, variantsApi } from '@/lib/api'
import {
  downloadHistoryExcel,
  buildHistoryDetailFields,
  type HistoryMediaTab,
  type HistoryRow,
} from '@/lib/exportHistoryExcel'
import { getVariantPreviewUrls, isMotionVariantFormat } from '@/lib/variantMedia'
import { cn, formatDate, timeAgo } from '@/lib/utils'
import type { Brief, Variant } from '@/types'

type PeriodId = 'all' | 'today' | '7d' | '30d' | 'custom'

function startOfDay(d: Date) {
  const x = new Date(d)
  x.setHours(0, 0, 0, 0)
  return x
}

function endOfDay(d: Date) {
  const x = new Date(d)
  x.setHours(23, 59, 59, 999)
  return x
}

function periodRange(
  period: PeriodId,
  customFrom: string,
  customTo: string
): { from: Date | null; to: Date | null; label: string } {
  const now = new Date()
  if (period === 'today') {
    return { from: startOfDay(now), to: endOfDay(now), label: 'Today' }
  }
  if (period === '7d') {
    const from = startOfDay(now)
    from.setDate(from.getDate() - 6)
    return { from, to: endOfDay(now), label: 'Last 7 days' }
  }
  if (period === '30d') {
    const from = startOfDay(now)
    from.setDate(from.getDate() - 29)
    return { from, to: endOfDay(now), label: 'Last 30 days' }
  }
  if (period === 'custom') {
    const from = customFrom ? startOfDay(new Date(customFrom)) : null
    const to = customTo ? endOfDay(new Date(customTo)) : null
    return {
      from,
      to,
      label:
        customFrom || customTo
          ? `${customFrom || '…'} → ${customTo || '…'}`
          : 'Custom range',
    }
  }
  return { from: null, to: null, label: 'All time' }
}

function inPeriod(iso: string, from: Date | null, to: Date | null) {
  const t = new Date(iso).getTime()
  if (Number.isNaN(t)) return false
  if (from && t < from.getTime()) return false
  if (to && t > to.getTime()) return false
  return true
}

export default function HistoryPage() {
  const [tab, setTab] = useState<HistoryMediaTab>('image')
  const [period, setPeriod] = useState<PeriodId>('all')
  const [customFrom, setCustomFrom] = useState('')
  const [customTo, setCustomTo] = useState('')
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set())
  const [detail, setDetail] = useState<HistoryRow | null>(null)
  const [exporting, setExporting] = useState(false)

  const { data: variants, isLoading, error, refetch } = useApi(
    () => variantsApi.list({ limit: 300 }),
    [],
    { cacheKey: 'history/variants', ttlMs: API_CACHE_TTL.variants }
  )
  const { data: briefs } = useApi(() => briefsApi.list({ limit: 200 }), [], {
    cacheKey: 'briefs',
    ttlMs: API_CACHE_TTL.briefs,
  })
  const { data: brands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands',
    ttlMs: API_CACHE_TTL.brands,
  })

  const briefById = useMemo(() => {
    const map = new Map<string, Brief>()
    for (const b of briefs ?? []) map.set(b.id, b)
    return map
  }, [briefs])

  const brandById = useMemo(() => {
    const map = new Map<string, string>()
    for (const b of brands ?? []) map.set(b.id, b.name)
    return map
  }, [brands])

  const { from, to, label: periodLabel } = useMemo(
    () => periodRange(period, customFrom, customTo),
    [period, customFrom, customTo]
  )

  const rows: HistoryRow[] = useMemo(() => {
    const list = (variants ?? [])
      .filter((v) => {
        const motion = isMotionVariantFormat(v.format)
        if (tab === 'image' && motion) return false
        if (tab === 'video' && !motion) return false
        return inPeriod(v.created_at, from, to)
      })
      .sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      )
      .map((variant) => ({
        variant,
        brief: briefById.get(variant.brief_id) ?? null,
        brandName: brandById.get(variant.brand_id),
      }))
    return list
  }, [variants, tab, from, to, briefById, brandById])

  const allVisibleSelected =
    rows.length > 0 && rows.every((r) => selectedIds.has(r.variant.id))

  const toggleOne = (id: string) => {
    setSelectedIds((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const toggleAllVisible = () => {
    if (allVisibleSelected) {
      setSelectedIds((prev) => {
        const next = new Set(prev)
        rows.forEach((r) => next.delete(r.variant.id))
        return next
      })
      return
    }
    setSelectedIds((prev) => {
      const next = new Set(prev)
      rows.forEach((r) => next.add(r.variant.id))
      return next
    })
  }

  const selectedRows = useMemo(
    () => rows.filter((r) => selectedIds.has(r.variant.id)),
    [rows, selectedIds]
  )

  const hydrateForExport = async (source: HistoryRow[]): Promise<HistoryRow[]> => {
    // Fetch full variant payloads so Excel includes complete prompts.
    const hydrated = await Promise.all(
      source.map(async (row) => {
        try {
          const full = await variantsApi.get(row.variant.id)
          return { ...row, variant: full }
        } catch {
          return row
        }
      })
    )
    return hydrated
  }

  const handleDownload = async (mode: 'selected' | 'all-visible') => {
    const source = mode === 'selected' ? selectedRows : rows
    if (!source.length) {
      toast.error(
        mode === 'selected'
          ? 'Select at least one item to download.'
          : 'No history items in this period.'
      )
      return
    }
    setExporting(true)
    try {
      const hydrated = await hydrateForExport(source)
      downloadHistoryExcel(hydrated, { tab, periodLabel })
      toast.success(
        `Downloaded ${hydrated.length} ${tab} item${hydrated.length === 1 ? '' : 's'} (.xlsx)`
      )
    } catch {
      toast.error('Excel download failed')
    } finally {
      setExporting(false)
    }
  }

  return (
    <div>
      <Topbar
        title="History"
        subtitle={`${rows.length} ${tab} item${rows.length !== 1 ? 's' : ''} · ${periodLabel}`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={() => void refetch()}>
              Refresh
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={exporting || selectedRows.length === 0}
              isLoading={exporting}
              onClick={() => void handleDownload('selected')}
            >
              Download selected ({selectedRows.length})
            </Button>
            <Button
              variant="primary"
              size="sm"
              disabled={exporting || rows.length === 0}
              isLoading={exporting}
              onClick={() => void handleDownload('all-visible')}
            >
              Download all in view
            </Button>
          </>
        }
      />

      <div className="px-5 py-3 bg-white border-b border-border space-y-3">
        <div className="flex flex-wrap gap-2 items-center">
          <ChipToggle
            label="Image history"
            selected={tab === 'image'}
            onToggle={() => {
              setTab('image')
              setSelectedIds(new Set())
            }}
          />
          <ChipToggle
            label="Video history"
            selected={tab === 'video'}
            onToggle={() => {
              setTab('video')
              setSelectedIds(new Set())
            }}
          />
          <span className="w-px h-6 bg-border mx-1" />
          {(
            [
              ['all', 'All time'],
              ['today', 'Today'],
              ['7d', 'Last 7 days'],
              ['30d', 'Last 30 days'],
              ['custom', 'Custom'],
            ] as Array<[PeriodId, string]>
          ).map(([id, label]) => (
            <ChipToggle
              key={id}
              label={label}
              selected={period === id}
              onToggle={() => setPeriod(id)}
            />
          ))}
        </div>

        {period === 'custom' && (
          <div className="flex flex-wrap items-end gap-3">
            <label className="text-xs font-semibold text-navy">
              From
              <input
                type="date"
                value={customFrom}
                onChange={(e) => setCustomFrom(e.target.value)}
                className="mt-1 block rounded-lg border border-border px-3 py-2 text-sm"
              />
            </label>
            <label className="text-xs font-semibold text-navy">
              To
              <input
                type="date"
                value={customTo}
                onChange={(e) => setCustomTo(e.target.value)}
                className="mt-1 block rounded-lg border border-border px-3 py-2 text-sm"
              />
            </label>
          </div>
        )}

        <p className="text-[11px] text-mid">
          Excel includes A–Z generation details: campaign, brand, objective, ad styles, hook,
          headline, CTA, prompt, ICP, models, asset URLs
          {tab === 'video' ? ', avatar/script fields' : ''}.
        </p>
      </div>

      <div className="p-5 space-y-4">
        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            Could not load history. {typeof error === 'string' ? error : 'Try refresh.'}
          </div>
        ) : null}

        {isLoading ? (
          <div className="space-y-2">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="skeleton h-20 rounded-xl" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="rounded-xl border border-border bg-white px-6 py-12 text-center">
            <p className="text-sm font-semibold text-navy">No {tab} history in this period</p>
            <p className="text-xs text-mid mt-1">
              Create a brief and generate variants — they will appear here.
            </p>
            <Link href="/briefs/new" className="inline-block mt-3 text-sm text-accent font-semibold underline">
              Create brief
            </Link>
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between gap-3">
              <label className="flex items-center gap-2 text-sm font-semibold text-navy cursor-pointer">
                <input
                  type="checkbox"
                  checked={allVisibleSelected}
                  onChange={toggleAllVisible}
                  className="rounded border-border"
                />
                Select all in view ({rows.length})
              </label>
              <p className="text-xs text-mid">{selectedRows.length} selected</p>
            </div>

            <div className="space-y-3">
              {rows.map((row) => {
                const v = row.variant
                const { imageUrl, videoUrl } = getVariantPreviewUrls(v)
                const checked = selectedIds.has(v.id)
                const params = (v.generation_params || {}) as Record<string, unknown>
                const models = (params.models || {}) as Record<string, unknown>
                const imagePlan = (params.image_plan || {}) as Record<string, unknown>
                const promptPreview = String(imagePlan.prompt || '').slice(0, 140)

                return (
                  <div
                    key={v.id}
                    className={cn(
                      'rounded-xl border bg-white p-4 flex gap-4 transition-colors',
                      checked ? 'border-accent/50 bg-accent/[0.03]' : 'border-border'
                    )}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleOne(v.id)}
                      className="mt-1 rounded border-border shrink-0"
                    />

                    <div className="w-20 h-20 rounded-lg overflow-hidden bg-light border border-border shrink-0">
                      {tab === 'video' && videoUrl ? (
                        <video src={videoUrl} className="w-full h-full object-cover" muted />
                      ) : imageUrl ? (
                        // eslint-disable-next-line @next/next/no-img-element
                        <img src={imageUrl} alt="" className="w-full h-full object-cover" />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center text-[10px] text-mid">
                          No media
                        </div>
                      )}
                    </div>

                    <div className="flex-1 min-w-0 space-y-1.5">
                      <div className="flex flex-wrap items-center gap-2">
                        <p className="text-sm font-bold text-navy truncate">
                          {row.brief?.title || 'Untitled brief'}
                        </p>
                        <Badge variant="gray" className="capitalize text-[10px]">
                          {v.format}
                        </Badge>
                        <Badge
                          variant={v.compliance_status === 'PASSED' ? 'green' : 'amber'}
                          className="text-[10px]"
                        >
                          {v.status}
                        </Badge>
                        <span className="text-[10px] text-mid">
                          {formatDate(v.created_at, 'MMM d, yyyy HH:mm')} · {timeAgo(v.created_at)}
                        </span>
                      </div>
                      <p className="text-xs text-charcoal">
                        <span className="font-semibold">Hook:</span> {v.hook || '—'}
                      </p>
                      <p className="text-xs text-mid">
                        <span className="font-semibold text-charcoal">Headline:</span>{' '}
                        {v.headline || '—'}
                        {' · '}
                        <span className="font-semibold text-charcoal">CTA:</span> {v.cta || '—'}
                      </p>
                      <p className="text-[11px] text-mid">
                        Brand: {row.brandName || '—'}
                        {' · '}
                        Models: {String(models.image || models.copy || v.ai_model || '—')}
                        {tab === 'video' ? ` / ${String(models.video || '—')}` : ''}
                      </p>
                      {promptPreview ? (
                        <p className="text-[11px] text-mid line-clamp-2">
                          <span className="font-semibold text-charcoal">Prompt:</span> {promptPreview}
                          {String(imagePlan.prompt || '').length > 140 ? '…' : ''}
                        </p>
                      ) : null}
                      <div className="flex flex-wrap gap-2 pt-1">
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setDetail(row)}
                        >
                          View A–Z details
                        </Button>
                        <Link
                          href={`/briefs/${v.brief_id}`}
                          className="inline-flex items-center text-xs font-semibold text-accent underline px-2"
                        >
                          Open brief
                        </Link>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </>
        )}
      </div>

      {detail && (
        <Modal
          isOpen={!!detail}
          onClose={() => setDetail(null)}
          title="Generation history details"
          size="lg"
        >
          <div className="space-y-3 max-h-[70vh] overflow-y-auto">
            {(() => {
              const { imageUrl, videoUrl } = getVariantPreviewUrls(detail.variant)
              if (videoUrl) {
                return (
                  <video
                    src={videoUrl}
                    controls
                    className="w-full max-h-[280px] rounded-lg bg-black"
                  />
                )
              }
              if (imageUrl) {
                return (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={imageUrl}
                    alt=""
                    className="w-full max-h-[280px] object-contain rounded-lg border border-border bg-light"
                  />
                )
              }
              return null
            })()}
            <dl className="space-y-2">
              {buildHistoryDetailFields(detail).map(([field, value]) => (
                <div key={field} className="grid grid-cols-[140px_1fr] gap-2 text-xs border-b border-border/60 pb-2">
                  <dt className="font-bold text-navy">{field}</dt>
                  <dd className="text-charcoal whitespace-pre-wrap break-words">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="flex justify-end gap-2 pt-2">
              <Button
                type="button"
                size="sm"
                variant="primary"
                disabled={exporting}
                onClick={() => {
                  setSelectedIds(new Set([detail.variant.id]))
                  void (async () => {
                    setExporting(true)
                    try {
                      const hydrated = await hydrateForExport([detail])
                      downloadHistoryExcel(hydrated, { tab, periodLabel })
                      toast.success('Downloaded 1 item (.xlsx)')
                    } catch {
                      toast.error('Download failed')
                    } finally {
                      setExporting(false)
                    }
                  })()
                }}
              >
                Download this item
              </Button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
