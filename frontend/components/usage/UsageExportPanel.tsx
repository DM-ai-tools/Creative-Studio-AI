'use client'

import React, { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { adminApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'

type Preset = '7' | '30' | '90' | 'custom'

type UsageExportPanelProps = {
  periodDays: number
  onPeriodDaysChange: (days: number) => void
  userId?: string
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

function daysAgoIso(days: number): string {
  const d = new Date()
  d.setUTCDate(d.getUTCDate() - days + 1)
  return d.toISOString().slice(0, 10)
}

export default function UsageExportPanel({
  periodDays,
  onPeriodDaysChange,
  userId,
}: UsageExportPanelProps) {
  const [preset, setPreset] = useState<Preset>(
    periodDays === 7 ? '7' : periodDays === 90 ? '90' : periodDays === 30 ? '30' : 'custom'
  )
  const [fromDate, setFromDate] = useState(daysAgoIso(30))
  const [toDate, setToDate] = useState(todayIso())
  const [exporting, setExporting] = useState(false)

  const presetLabel = useMemo(() => {
    if (preset === 'custom') return `${fromDate} → ${toDate}`
    return `Last ${preset} days`
  }, [preset, fromDate, toDate])

  const applyPreset = (p: Preset) => {
    setPreset(p)
    if (p === 'custom') return
    const days = Number(p)
    onPeriodDaysChange(days)
    setFromDate(daysAgoIso(days))
    setToDate(todayIso())
  }

  const handleExport = async () => {
    setExporting(true)
    try {
      const params: { days?: number; from?: string; to?: string; user_id?: string } =
        preset === 'custom'
          ? { from: fromDate, to: toDate }
          : { days: Number(preset) || periodDays }
      if (userId) params.user_id = userId
      const response = await adminApi.exportUsageReport(params)
      const blob = response.data
      const disposition = response.headers['content-disposition'] as string | undefined
      const match = disposition?.match(/filename="([^"]+)"/)
      const filename = match?.[1] ?? `usage-report-${presetLabel.replace(/\s+/g, '-')}.xlsx`
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = filename
      a.click()
      URL.revokeObjectURL(url)
      toast.success('Usage report downloaded')
    } catch (err) {
      toast.error(extractApiError(err, 'Could not export usage report'))
    } finally {
      setExporting(false)
    }
  }

  return (
    <Card title="Export usage report">
      <div className="space-y-4">
        <p className="text-sm text-mid leading-relaxed">
          Download Excel for your <strong className="font-semibold text-charcoal">reporting manager</strong>:
          each row includes the <strong className="font-semibold text-charcoal">user, workspace, brand, model, media type and cost</strong>, plus separate{' '}
          <strong className="font-semibold text-charcoal">Image link</strong> and{' '}
          <strong className="font-semibold text-charcoal">Video link</strong> columns (clickable on
          production). On local dev only, a disk path column is included. Open the{' '}
          <strong className="font-semibold text-charcoal">Read me</strong> tab before sending.
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
                onChange={(e) => setFromDate(e.target.value)}
                className="rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
              />
            </label>
            <label className="flex flex-col gap-1 text-xs text-mid flex-1">
              To
              <input
                type="date"
                value={toDate}
                onChange={(e) => setToDate(e.target.value)}
                className="rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
              />
            </label>
          </div>
        ) : (
          <p className="text-xs text-muted">Dashboard charts use the same range: {presetLabel}.</p>
        )}
        <Button size="sm" onClick={() => void handleExport()} isLoading={exporting}>
          Download Excel (.xlsx)
        </Button>
      </div>
    </Card>
  )
}
