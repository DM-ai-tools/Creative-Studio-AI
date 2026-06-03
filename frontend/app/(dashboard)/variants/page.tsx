'use client'

import React, { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import VariantGrid from '@/components/variant/VariantGrid'
import Modal from '@/components/ui/Modal'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { ChipToggle } from '@/components/ui/ChipToggle'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { briefsApi, generationApi, variantsApi } from '@/lib/api'
import { mapCreativeFormatOptions } from '@/lib/creativeFormats'
import { getVariantPreviewUrls } from '@/lib/variantMedia'
import { cn, formatDate } from '@/lib/utils'
import type { Variant, AdFormat, ComplianceStatus } from '@/types'

export default function VariantsPage() {
  const [formatFilter, setFormatFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [briefFilter, setBriefFilter] = useState('all')
  const [selectedVariant, setSelectedVariant] = useState<Variant | null>(null)

  const { data: catalog } = useApi(() => generationApi.getCatalog(), [], {
    cacheKey: 'generation/catalog-v2',
    ttlMs: API_CACHE_TTL.catalog,
  })
  const { data: briefs } = useApi(() => briefsApi.list(), [], {
    cacheKey: 'briefs',
    ttlMs: API_CACHE_TTL.briefs,
  })
  const { data: variants, isLoading, refetch } = useApi(
    () => variantsApi.list({
      ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
    }),
    [statusFilter]
  )

  const formatOptions = useMemo(
    () => [
      { id: 'all', label: 'All formats' },
      ...mapCreativeFormatOptions(catalog?.creative_formats ?? []),
    ],
    [catalog]
  )
  const statusOptions = useMemo(
    () => [
      { id: 'all', label: 'All statuses' },
      { id: 'READY', label: 'Ready' },
      { id: 'APPROVED', label: 'Approved' },
      { id: 'PENDING', label: 'Pending' },
      { id: 'FAILED', label: 'Failed' },
      { id: 'REJECTED', label: 'Rejected' },
    ],
    []
  )

  const filtered = (variants ?? []).filter((variant: Variant) => {
    if (formatFilter !== 'all' && variant.format !== formatFilter) return false
    if (briefFilter !== 'all' && variant.brief_id !== briefFilter) return false
    return true
  })

  const selectedBrief = briefs?.find((brief) => brief.id === briefFilter)

  const handleApprove = async (id: string) => {
    try {
      await variantsApi.approve(id)
      toast.success('Approved')
      refetch()
    } catch { toast.error('Failed') }
  }

  const handleReject = async (id: string) => {
    try {
      await variantsApi.reject(id)
      toast.success('Rejected')
      refetch()
    } catch { toast.error('Failed') }
  }

  const handleDelete = async (id: string) => {
    if (!window.confirm('Delete this variant? This cannot be undone.')) return
    try {
      await variantsApi.delete(id)
      toast.success('Variant deleted')
      if (selectedVariant?.id === id) setSelectedVariant(null)
      refetch()
    } catch {
      toast.error('Failed to delete variant')
    }
  }

  return (
    <div>
      <Topbar
        title={selectedBrief ? `Variant Library · ${selectedBrief.title}` : 'Variant Library'}
        subtitle={`${filtered.length} variant${filtered.length !== 1 ? 's' : ''}`}
        actions={
          <>
            <Button variant="outline" size="sm">Filter</Button>
            <Button variant="secondary" size="sm">Send to Compliance</Button>
            <Button variant="primary" size="sm">Export Selected</Button>
          </>
        }
      />

      <div className="px-5 py-3 bg-white border-b border-border flex flex-wrap gap-2">
        {briefFilter !== 'all' && selectedBrief && (
          <ChipToggle
            label={`Brief: ${selectedBrief.title} ✕`}
            selected
            onToggle={() => setBriefFilter('all')}
          />
        )}
        {formatOptions.map((option) => (
          <ChipToggle
            key={option.id}
            label={option.label}
            selected={formatFilter === option.id}
            onToggle={() => setFormatFilter(option.id)}
          />
        ))}
        {statusOptions.map((option) => (
          <ChipToggle
            key={option.id}
            label={option.label}
            selected={statusFilter === option.id}
            onToggle={() => setStatusFilter(option.id)}
          />
        ))}
        {(briefs ?? []).slice(0, 4).map((brief) => (
          <ChipToggle
            key={brief.id}
            label={`Brief: ${brief.title}`}
            selected={briefFilter === brief.id}
            onToggle={() => setBriefFilter(briefFilter === brief.id ? 'all' : brief.id)}
          />
        ))}
      </div>

      <div className="p-5">
        <VariantGrid
          variants={filtered}
          isLoading={isLoading}
          onApprove={handleApprove}
          onReject={handleReject}
          onDelete={handleDelete}
          onView={setSelectedVariant}
        />
      </div>

      {selectedVariant && (
        <Modal
          isOpen={!!selectedVariant}
          onClose={() => setSelectedVariant(null)}
          title="Variant Detail"
          size="lg"
        >
          <div className="space-y-3">
            {(() => {
              const {
                imageUrl: imageSrc,
                videoUrl: videoSrc,
                imageFailed,
                imageError,
                videoFailed,
                videoError,
                missingMotionMedia,
              } = getVariantPreviewUrls(selectedVariant)
              if (videoSrc) {
                const isReel =
                  selectedVariant.format === 'reel' || selectedVariant.format === 'video'
                return (
                  <div
                    className={cn(
                      'mx-auto w-full max-w-[360px] rounded-lg border border-border bg-black overflow-hidden',
                      isReel && 'aspect-[9/16]'
                    )}
                  >
                    <video
                      src={videoSrc}
                      className="h-full w-full object-cover"
                      controls
                      playsInline
                    />
                  </div>
                )
              }
              if (imageSrc) {
                return (
                  <img
                    src={imageSrc}
                    alt={selectedVariant.headline || selectedVariant.hook}
                    className="w-full rounded-lg border border-border max-h-[420px] object-contain bg-light"
                  />
                )
              }
              if (videoFailed || missingMotionMedia) {
                return (
                  <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    Video not generated.{' '}
                    {videoError ||
                      'Check Runway API credits (RUNWAYML_API_KEY), then delete this variant and generate again from the brief.'}
                  </p>
                )
              }
              if (
                imageFailed &&
                selectedVariant.format !== 'video' &&
                selectedVariant.format !== 'reel'
              ) {
                return (
                  <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
                    Image not generated. {imageError || 'Add Runway credits and regenerate this brief.'}
                  </p>
                )
              }
              return null
            })()}
            <div className="flex items-center gap-2 flex-wrap">
              <Badge variant="gray" className="capitalize">{selectedVariant.format}</Badge>
              <Badge variant={selectedVariant.compliance_status === 'PASSED' ? 'green' : 'amber'}>
                {selectedVariant.compliance_status}
              </Badge>
              <span className="text-xs text-lt">{formatDate(selectedVariant.created_at)}</span>
            </div>
            <div>
              <p className="text-[10px] font-bold text-lt uppercase tracking-wide mb-1">Hook</p>
              <p className="text-sm font-semibold text-navy">{selectedVariant.hook}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-lt uppercase tracking-wide mb-1">Headline</p>
              <p className="text-sm text-navy">{selectedVariant.headline}</p>
            </div>
            <div>
              <p className="text-[10px] font-bold text-lt uppercase tracking-wide mb-1">Body Copy</p>
              <p className="text-sm text-mid leading-relaxed">{selectedVariant.body_copy}</p>
            </div>
            <div className="flex flex-wrap gap-2 pt-2">
              <button
                onClick={() => { handleApprove(selectedVariant.id); setSelectedVariant(null) }}
                className="flex-1 min-w-[100px] bg-mint text-navy text-sm font-bold py-2 rounded-lg hover:bg-[#00A892]"
              >
                Approve
              </button>
              <button
                onClick={() => { handleReject(selectedVariant.id); setSelectedVariant(null) }}
                className="flex-1 min-w-[100px] bg-red-100 text-red-700 text-sm font-bold py-2 rounded-lg hover:bg-red-200"
              >
                Reject
              </button>
              <button
                onClick={() => { handleDelete(selectedVariant.id) }}
                className="flex-1 min-w-[100px] border border-border text-navy text-sm font-bold py-2 rounded-lg hover:bg-light"
              >
                Delete
              </button>
            </div>
          </div>
        </Modal>
      )}
    </div>
  )
}
