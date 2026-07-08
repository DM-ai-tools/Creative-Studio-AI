'use client'

import React, { useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { generationApi } from '@/lib/api'
import { downloadStrategyExcel } from '@/lib/exportStrategyExcel'
import type { StrategyPreviewResult } from '@/types'

export interface StrategyPreviewInputs {
  campaign_name: string
  brand_name: string
  product_name: string
  offer: string
  target_audience: string
  ad_copy_tone: string
  cta: string
  target_seconds: number
  hook_frameworks: string[]
  objective: string
  placements: string[]
  formats: string[]
  website_url?: string
}

interface StrategyPreviewPanelProps {
  getInputs: () => StrategyPreviewInputs
  canBuild: boolean
  onPreviewChange?: (preview: StrategyPreviewResult | null) => void
}

function SectionBlock({
  title,
  children,
  accent = 'violet',
}: {
  title: string
  children: React.ReactNode
  accent?: 'violet' | 'emerald' | 'amber' | 'sky'
}) {
  const border =
    accent === 'emerald'
      ? 'border-emerald-200'
      : accent === 'amber'
        ? 'border-amber-200'
        : accent === 'sky'
          ? 'border-sky-200'
          : 'border-violet-200'
  const label =
    accent === 'emerald'
      ? 'text-emerald-700'
      : accent === 'amber'
        ? 'text-amber-800'
        : accent === 'sky'
          ? 'text-sky-700'
          : 'text-violet-700'
  return (
    <div className={`rounded-xl border ${border} bg-white/80 p-3`}>
      <p className={`text-[10px] font-bold uppercase tracking-wide mb-2 ${label}`}>{title}</p>
      {children}
    </div>
  )
}

export default function StrategyPreviewPanel({ getInputs, canBuild, onPreviewChange }: StrategyPreviewPanelProps) {
  const [competitorsText, setCompetitorsText] = useState('')
  const [loading, setLoading] = useState(false)
  const [preview, setPreview] = useState<StrategyPreviewResult | null>(null)

  const handleBuild = async () => {
    const inputs = getInputs()
    if (!inputs.target_audience && !inputs.offer && !inputs.product_name) {
      toast.error('Fill Target Audience, Offer, or Product first.')
      return
    }
    const competitors = competitorsText
      .split(/[,;\n]/)
      .map((s) => s.trim())
      .filter(Boolean)

    setLoading(true)
    try {
      const result = await generationApi.generateStrategyPreview({
        ...inputs,
        competitors,
      })
      setPreview(result)
      onPreviewChange?.(result)
      toast.success('Strategy preview ready — share or download for your manager')
    } catch (err) {
      console.error(err)
      toast.error('Could not build strategy preview')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="card-premium p-5 space-y-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="label-ui">Creative Strategy</p>
          <p className="text-[11px] text-mid mt-0.5">
            ICP, HALO, hooks &amp; body — before you generate
          </p>
        </div>
      </div>

      <Input
        label="Competitors (optional)"
        placeholder="e.g. Agency X, Competitor Y — comma separated"
        value={competitorsText}
        onChange={(e) => setCompetitorsText(e.target.value)}
      />

      <Button
        type="button"
        size="sm"
        variant="primary"
        className="w-full"
        isLoading={loading}
        disabled={!canBuild || loading}
        onClick={() => void handleBuild()}
      >
        Build strategy preview
      </Button>

      {!preview && (
        <p className="text-[11px] text-mid">
          Lists ICP profile, 3 hook options, HALO strategy, body outline, and competitor positioning.
        </p>
      )}

      {preview && (
        <div className="space-y-3 max-h-[min(70vh,640px)] overflow-y-auto pr-1">
          <SectionBlock title="Script framework" accent="sky">
            <p className="text-xs font-semibold text-navy">{preview.framework_name}</p>
            <p className="text-[11px] text-mid mt-1">{preview.framework_description}</p>
            <p className="text-[11px] text-mid mt-1">
              {preview.framework_structure.join(' → ')}
            </p>
          </SectionBlock>

          <SectionBlock title="ICP profile" accent="violet">
            <div className="space-y-1.5 max-h-36 overflow-y-auto">
              {Object.entries(preview.icp_fields).map(([key, val]) => (
                <div key={key}>
                  <p className="text-[10px] font-bold text-violet-600">{key}</p>
                  <p className="text-[11px] text-navy leading-snug">{val}</p>
                </div>
              ))}
            </div>
          </SectionBlock>

          <SectionBlock title="Hook options" accent="amber">
            <ol className="list-decimal list-inside space-y-1.5">
              {preview.hook_options.map((hook, i) => (
                <li key={i} className="text-[11px] text-navy leading-snug">
                  {hook}
                </li>
              ))}
            </ol>
          </SectionBlock>

          <SectionBlock title="HALO strategy" accent="emerald">
            <div className="space-y-1.5 text-[11px]">
              <p><span className="font-bold text-emerald-800">H — Hook:</span> {preview.halo_strategy.hook}</p>
              <p><span className="font-bold text-emerald-800">A — Agitate:</span> {preview.halo_strategy.agitate}</p>
              <p><span className="font-bold text-emerald-800">L — Lift:</span> {preview.halo_strategy.lift}</p>
              <p><span className="font-bold text-emerald-800">O — Offer:</span> {preview.halo_strategy.offer}</p>
            </div>
          </SectionBlock>

          <SectionBlock title="Body outline">
            <div className="space-y-2">
              {preview.body_outline.map((block, i) => (
                <div key={i} className="border-b border-violet-100 pb-2 last:border-0">
                  <p className="text-[11px] font-semibold text-navy">
                    {block.section}
                    {block.duration_hint ? (
                      <span className="text-mid font-normal"> · {block.duration_hint}</span>
                    ) : null}
                  </p>
                  <p className="text-[11px] text-mid mt-0.5">{block.talking_points}</p>
                </div>
              ))}
            </div>
          </SectionBlock>

          <SectionBlock title="Competitor positioning" accent="amber">
            <p className="text-[11px] text-navy leading-relaxed">{preview.competitor_positioning}</p>
            <ul className="mt-2 space-y-1">
              {preview.differentiation_points.map((pt, i) => (
                <li key={i} className="text-[11px] text-mid flex gap-1.5">
                  <span className="text-amber-600">✦</span> {pt}
                </li>
              ))}
            </ul>
          </SectionBlock>

          <Button
            type="button"
            size="sm"
            variant="outline"
            className="w-full"
            onClick={() => downloadStrategyExcel(preview)}
          >
            Download strategy only (.csv)
          </Button>
          <p className="text-[10px] text-mid text-center">
            For full Steps 1–9 + approved script, use <strong>Download brief Excel</strong> below.
          </p>
        </div>
      )}
    </div>
  )
}
