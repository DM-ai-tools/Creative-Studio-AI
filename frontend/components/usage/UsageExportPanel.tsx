'use client'

import React, { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { adminApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'

type Preset = '7' | '30' | '90' | 'custom'

/** The one date range shared by the page figures, the charts and both downloads. */
export type UsageRange = { preset: Preset; from: string; to: string }

type UsageExportPanelProps = {
  range: UsageRange
  onRangeChange: (range: UsageRange) => void
  userId?: string
}

const MAX_RANGE_DAYS = 366

export function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function daysAgoIso(days: number): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - days + 1)
  return d.toISOString().slice(0, 10)
}

export function customSpanDays(from: string, to: string): number {
  const a = Date.parse(`${from}T00:00:00Z`)
  const b = Date.parse(`${to}T00:00:00Z`)
  if (Number.isNaN(a) || Number.isNaN(b)) return 0
  return Math.round((b - a) / 86_400_000) + 1
}

/** Both dates filled in, start not after end, and within the allowed span. */
export function isValidCustomRange(from: string, to: string): boolean {
  const span = customSpanDays(from, to)
  return span >= 1 && span <= MAX_RANGE_DAYS
}

/** A failed download comes back as a Blob; read the server's real message out of it. */
async function exportErrorMessage(err: unknown, fallback: string): Promise<string> {
  const data = (err as { response?: { data?: unknown } })?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text()) as { detail?: unknown }
      if (typeof parsed.detail === 'string' && parsed.detail.trim()) return parsed.detail
    } catch {
      /* fall through to the generic message */
    }
  }
  return extractApiError(err, fallback)
}

export default function UsageExportPanel({
  range,
  onRangeChange,
  userId,
}: UsageExportPanelProps) {
  const { preset, from: fromDate, to: toDate } = range
  const [exporting, setExporting] = useState(false)
  const [exportingSummary, setExportingSummary] = useState(false)

  const customInvalid = preset === 'custom' && !isValidCustomRange(fromDate, toDate)
  const customError = !customInvalid
    ? null
    : !fromDate || !toDate
      ? 'Pick both a start and an end date.'
      : customSpanDays(fromDate, toDate) < 1
        ? 'The end date must be on or after the start date.'
        : `The range can be at most ${MAX_RANGE_DAYS} days.`

  const presetLabel = useMemo(() => {
    if (preset === 'custom') return `${fromDate} → ${toDate}`
    return `Last ${preset} days`
  }, [preset, fromDate, toDate])

  const applyPreset = (p: Preset) => {
    if (p === 'custom') {
      onRangeChange({ ...range, preset: 'custom' })
      return
    }
    const days = Number(p)
    onRangeChange({ preset: p, from: daysAgoIso(days), to: todayIso() })
  }

  const buildExportParams = (): { days?: number; from?: string; to?: string; user_id?: string } => {
    const params: { days?: number; from?: string; to?: string; user_id?: string } =
      preset === 'custom' ? { from: fromDate, to: toDate } : { days: Number(preset) }
    if (userId) params.user_id = userId
    return params
  }

  const downloadBlobResponse = (
    response: { data: Blob; headers: Record<string, unknown> },
    fallbackName: string,
  ) => {
    const disposition = response.headers['content-disposition'] as string | undefined
    const match = disposition?.match(/filename="([^"]+)"/)
    const filename = match?.[1] ?? fallbackName
    const url = URL.createObjectURL(response.data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const response = await adminApi.exportUsageReport(buildExportParams())
      downloadBlobResponse(response, `usage-report-${presetLabel.replace(/\s+/g, '-')}.xlsx`)
      toast.success('Full usage report downloaded')
    } catch (err) {
      toast.error(await exportErrorMessage(err, 'Could not export usage report'))
    } finally {
      setExporting(false)
    }
  }

  const handleExportSummary = async () => {
    setExportingSummary(true)
    try {
      const response = await adminApi.exportUsageSummaryReport(buildExportParams())
      downloadBlobResponse(response, `usage-summary-${presetLabel.replace(/\s+/g, '-')}.xlsx`)
      toast.success('Summary report downloaded')
    } catch (err) {
      toast.error(await exportErrorMessage(err, 'Could not export summary report'))
    } finally {
      setExportingSummary(false)
    }
  }

  return (
    <Card title="Export usage report">
      <div className="space-y-4">
        <p className="text-sm text-mid leading-relaxed">
          Both Excel files start with the <strong className="font-semibold text-charcoal">same figures shown on this
          page</strong> (spend, calls, tokens, by user / provider / model, every Seedance clip) plus a{' '}
          <strong className="font-semibold text-charcoal">Work by user</strong> sheet (images, video clips, voice-overs,
          text calls, failures). <strong className="font-semibold text-charcoal">Summary Excel</strong> is for managers
          (per user / per brand).{' '}
          <strong className="font-semibold text-charcoal">Full Excel</strong> adds clickable{' '}
          <strong className="font-semibold text-charcoal">Creatives by brand</strong> links (
          <code className="text-xs">/files/…</code>). Use the User filter for one teammate (e.g. last 7 days).
        </p>
        <div>
          <p className="text-[10px] font-bold text-lt uppercase tracking-wide mb-2">Date range</p>
          <div className="flex flex-wrap gap-2">
            {(['7', '30', '90', 'custom'] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => applyPreset(p)}
                className={`px-3.5 py-2 text-xs font-semibold rounded-full border transition-all ${
                  preset === p
                    ? 'border-accent/50 bg-accent/10 text-charcoal'
                    : 'border-border text-mid hover:border-accent/30'
                }`}
              >
                {p === 'custom' ? 'Custom dates' : `Last ${p} days`}
              </button>
            ))}
          </div>
        </div>
        {preset === 'custom' ? (
          <div className="flex flex-col sm:flex-row gap-3">
            <label className="flex flex-col gap-1 text-xs text-mid flex-1">
              From
              <input
                type="date"
                value={fromDate}
                max={toDate || undefined}
                onChange={(e) => onRangeChange({ ...range, from: e.target.value })}
                className="rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-mid flex-1">
              To
              <input
                type="date"
                value={toDate}
                min={fromDate || undefined}
                onChange={(e) => onRangeChange({ ...range, to: e.target.value })}
                className="rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
              />
            </label>
          </div>
        ) : null}
        {customError ? (
          <p className="text-xs text-red-600">{customError}</p>
        ) : (
          <p className="text-xs text-muted">
            The figures, charts and both downloads on this page use the same range: {presetLabel}.
          </p>
        )}
        <div className="flex flex-wrap gap-2">
          <Button size="sm" onClick={() => void handleExportSummary()} isLoading={exportingSummary} disabled={customInvalid}>
            Download summary Excel
          </Button>
          <Button size="sm" variant="secondary" onClick={() => void handleExport()} isLoading={exporting} disabled={customInvalid}>
            Download full Excel (with links)
          </Button>
        </div>
      </div>
    </Card>
  )
}
