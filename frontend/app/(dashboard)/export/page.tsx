'use client'

import React, { useState } from 'react'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import Card from '@/components/ui/Card'
import Badge from '@/components/ui/Badge'
import { useApi } from '@/hooks/useApi'
import { metaApi, variantsApi } from '@/lib/api'
import type { Variant } from '@/types'
import { assetUrl } from '@/lib/utils'

export default function ExportPage() {
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [campaignName, setCampaignName] = useState('')
  const [adSetName, setAdSetName] = useState('')
  const [isExporting, setIsExporting] = useState(false)

  const { data: variants, isLoading } = useApi(() => variantsApi.list({ status: 'APPROVED' }), [])
  const { data: metaStatus } = useApi(() => metaApi.getStatus(), [])

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const handleExport = async () => {
    if (selected.size === 0) {
      toast.error('Select at least one variant')
      return
    }
    if (!campaignName) {
      toast.error('Enter campaign name')
      return
    }
    if (!metaStatus?.connected) {
      toast.error('Meta credentials are not configured on the server')
      return
    }

    setIsExporting(true)
    try {
      const result = await metaApi.exportVariants({
        variant_ids: Array.from(selected),
        campaign_name: campaignName,
        ad_set_name: adSetName || undefined,
      })
      toast.success(result.message)
      setSelected(new Set())
    } catch {
      toast.error('Meta export failed')
    } finally {
      setIsExporting(false)
    }
  }

  return (
    <div>
      <Topbar
        title="Export to Meta"
        subtitle="Push approved variants using configured Meta credentials"
        actions={
          <Button variant="primary" isLoading={isExporting} onClick={handleExport}>
            Export {selected.size > 0 ? `(${selected.size})` : ''} to Meta
          </Button>
        }
      />

      <div className="p-5 space-y-4">
        <Card title="Export Configuration">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <Input
              label="Campaign Name"
              placeholder="Spring 2025 — Click Trends"
              value={campaignName}
              onChange={(event) => setCampaignName(event.target.value)}
            />
            <Input
              label="Ad Set Name"
              placeholder="Broad — LAL 2%"
              value={adSetName}
              onChange={(event) => setAdSetName(event.target.value)}
            />
          </div>
          <div className="mt-3 p-3 rounded-lg border border-border bg-light">
            <div className="flex items-center justify-between gap-3">
              <div>
                <p className="text-xs font-semibold text-navy">Meta integration</p>
                <p className="text-[11px] text-lt mt-1">
                  {metaStatus?.connected
                    ? 'Server credentials are active. Exports use the configured access token.'
                    : metaStatus?.message || 'Configure META_APP_ID and META_ACCESS_TOKEN in backend/.env.'}
                </p>
              </div>
              <Badge variant={metaStatus?.connected ? 'green' : 'amber'}>
                {metaStatus?.connected ? 'Connected' : 'Not connected'}
              </Badge>
            </div>
          </div>
        </Card>

        <div>
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-navy">
              Approved Variants ({variants?.length ?? 0})
              {selected.size > 0 && <span className="ml-2 text-mint">{selected.size} selected</span>}
            </h3>
            {(variants?.length ?? 0) > 0 && (
              <button
                onClick={() =>
                  setSelected(
                    selected.size === variants?.length
                      ? new Set()
                      : new Set((variants ?? []).map((variant: Variant) => variant.id))
                  )
                }
                className="text-xs text-mint font-semibold hover:underline"
              >
                {selected.size === variants?.length ? 'Deselect all' : 'Select all'}
              </button>
            )}
          </div>

          {isLoading ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[...Array(4)].map((_, index) => (
                <div key={index} className="aspect-square skeleton rounded-xl" />
              ))}
            </div>
          ) : variants?.length === 0 ? (
            <div className="py-16 text-center">
              <p className="text-sm text-mid">No approved variants yet.</p>
              <p className="text-xs text-lt mt-1">Approve variants in Variants or Brief Detail pages first.</p>
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {(variants ?? []).map((variant: Variant) => {
                const pipeline = variant.generation_params?.pipeline as { image?: { url?: string } } | undefined
                const previewUrl = assetUrl(pipeline?.image?.url)
                return (
                  <div
                    key={variant.id}
                    onClick={() => toggleSelect(variant.id)}
                    className={`cursor-pointer rounded-xl overflow-hidden border-2 transition-colors ${
                      selected.has(variant.id) ? 'border-mint' : 'border-transparent'
                    }`}
                  >
                    <div className="aspect-square bg-gradient-to-br from-navy2 to-navy flex items-center justify-center relative">
                      {previewUrl ? (
                        <img src={previewUrl} alt={variant.hook} className="absolute inset-0 h-full w-full object-cover" />
                      ) : (
                        <span className="text-white text-2xl opacity-40">🖼</span>
                      )}
                      {selected.has(variant.id) && (
                        <div className="absolute top-2 right-2 w-5 h-5 bg-mint rounded-full flex items-center justify-center">
                          <span className="text-navy text-xs font-bold">✓</span>
                        </div>
                      )}
                      <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/70 to-transparent p-2">
                        <p className="text-white text-[10px] font-semibold leading-tight line-clamp-2">{variant.hook}</p>
                      </div>
                    </div>
                    <div className="bg-white px-2 py-1.5 flex justify-between items-center">
                      <span className="text-[10px] font-semibold text-mid capitalize">{variant.format}</span>
                      <Badge variant="green" size="sm">Approved</Badge>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
