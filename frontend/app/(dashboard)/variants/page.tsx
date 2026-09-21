'use client'

import React, { useMemo, useState } from 'react'
import Link from 'next/link'
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
import { mapCreativeFormatOptions, videoPreviewAspectClass, videoModalObjectFit } from '@/lib/creativeFormats'
import { getVariantPreviewUrls } from '@/lib/variantMedia'
import { cn, formatDate } from '@/lib/utils'
import type { Variant, AdFormat, ComplianceStatus } from '@/types'

export default function VariantsPage() {
  const [formatFilter, setFormatFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState('all')
  const [briefFilter, setBriefFilter] = useState('all')
  const [selectedVariant, setSelectedVariant] = useState<Variant | null>(null)

  const { data: catalog } = useApi(() => generationApi.getCatalog(false), [], {
    cacheKey: 'generation/catalog-v5',
    ttlMs: API_CACHE_TTL.catalog,
  })
  const { data: briefs } = useApi(() => briefsApi.list({ limit: 200 }), [], {
    cacheKey: 'briefs',
    ttlMs: API_CACHE_TTL.briefs,
  })
  const { data: variants, isLoading, error, refetch } = useApi(
    () =>
      variantsApi.list({
        limit: 300,
        ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
      }),
    [statusFilter],
    { cacheKey: `variants-library/${statusFilter}`, ttlMs: API_CACHE_TTL.variants }
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
  const readyBriefs = (briefs ?? []).filter((b) => (b.completed_variants ?? 0) > 0)

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

  const handleRefresh = () => {
    void refetch()
    toast.success('Refreshing variants…')
  }

  return (
    <div>
      <Topbar
        title={selectedBrief ? `Variant Library · ${selectedBrief.title}` : 'Variant Library'}
        subtitle={`${filtered.length} variant${filtered.length !== 1 ? 's' : ''}`}
        actions={
          <>
            <Button variant="outline" size="sm" onClick={handleRefresh}>
              Refresh
            </Button>
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

      <div className="p-5 space-y-4">
        {error ? (
          <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            <p className="font-semibold">Could not load variants</p>
            <p className="text-xs mt-1">{typeof error === 'string' ? error : 'Request failed'}</p>
            <Button variant="outline" size="sm" className="mt-2" onClick={handleRefresh}>
              Try again
            </Button>
          </div>
        ) : null}

        {!isLoading && !error && filtered.length === 0 && readyBriefs.length > 0 ? (
          <div className="rounded-xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
            <p className="font-semibold">Variants exist on briefs but aren’t showing here</p>
            <p className="text-xs mt-1">
              Open a brief below to view them, or click Refresh. Your latest brief has{' '}
              {readyBriefs[0]?.completed_variants}/{readyBriefs[0]?.variant_count} variants.
            </p>
            <div className="mt-2 flex flex-wrap gap-2">
              {readyBriefs.slice(0, 5).map((b) => (
                <Link
                  key={b.id}
                  href={`/briefs/${b.id}`}
                  className="text-xs font-semibold text-accent underline"
                >
                  {b.title} ({b.completed_variants})
                </Link>
              ))}
            </div>
          </div>
        ) : null}

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
                return (
                  <div
                    className={cn(
                      'mx-auto w-full rounded-lg border border-border bg-black overflow-hidden',
                      selectedVariant.format === 'video' ? 'max-w-3xl' : 'max-w-[360px]',
                      videoPreviewAspectClass(selectedVariant.format)
                    )}
                  >
                    <video
                      src={videoSrc}
                      className={cn(
                        'h-full w-full bg-black',
                        videoModalObjectFit(selectedVariant.format) === 'contain'
                          ? 'object-contain'
                          : 'object-cover'
                      )}
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
                    Image not generated.{' '}
                    {imageError ||
                      'Check OpenAI image model / credits, then regenerate this brief.'}
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
            {(() => {
              const { imageUrl, videoUrl } = getVariantPreviewUrls(selectedVariant)
              const downloadUrl = videoUrl || imageUrl
              if (!downloadUrl) return null
              const isVideo = Boolean(videoUrl)
              const ext = isVideo ? 'mp4' : 'png'
              const filename = `${(selectedVariant.headline || selectedVariant.hook || 'variant').replace(/[^a-z0-9]/gi, '-').toLowerCase()}.${ext}`
              return (
                <a
                  href={downloadUrl}
                  download={filename}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center justify-center gap-2 w-full border-2 border-accent text-accent text-sm font-bold py-2 rounded-lg hover:bg-accent/5 transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" strokeWidth={2.2} viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2M7 10l5 5 5-5M12 15V3" />
                  </svg>
                  Download {isVideo ? 'video' : 'image'}
                </a>
              )
            })()}
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
