import React from 'react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import { cn, getFormatColor, truncate } from '@/lib/utils'
import { formatVideoErrorMessage, getVariantPreviewUrls } from '@/lib/variantMedia'
import type { Variant, ComplianceStatus } from '@/types'

interface VariantTileProps {
  variant: Variant
  onApprove(id: string): void
  onReject(id: string): void
  onDelete?(id: string): void
  onRegenerate?(): void
  onView(variant: Variant): void
}

const complianceBadge: Record<ComplianceStatus, { variant: 'green' | 'red' | 'amber' | 'gray'; label: string }> = {
  PASSED: { variant: 'green', label: 'Compliant' },
  FAILED: { variant: 'red', label: 'Failed' },
  WARNING: { variant: 'amber', label: 'Warning' },
  PENDING: { variant: 'gray', label: 'Checking' },
}

export default function VariantTile({
  variant,
  onApprove,
  onReject,
  onDelete,
  onRegenerate,
  onView,
}: VariantTileProps) {
  const cb = complianceBadge[variant.compliance_status as ComplianceStatus] ?? complianceBadge.PENDING
  const gradientClass = getFormatColor(variant.format)
  const {
    imageUrl: previewUrl,
    videoUrl,
    videoFailed,
    missingMotionMedia,
    videoError,
    subtitlesMissing,
    subtitleWarning,
    logoMissing,
    logoWarning,
  } = getVariantPreviewUrls(variant)
  const failureMessage =
    variant.status === 'FAILED' || videoFailed || missingMotionMedia
      ? formatVideoErrorMessage(videoError) || 'Video not generated'
      : null

  return (
    <div className="card-premium overflow-hidden group hover:shadow-card-hover transition-all duration-300">
      <div
        className={cn(
          'relative bg-gradient-to-br flex items-center justify-center cursor-pointer',
          variant.format === 'reel' || variant.format === 'video'
            ? 'aspect-[9/16]'
            : 'aspect-square',
          gradientClass
        )}
        onClick={() => onView(variant)}
      >
        {videoUrl ? (
          <video
            src={videoUrl}
            className="absolute inset-0 h-full w-full object-cover"
            muted
            playsInline
            preload="metadata"
          />
        ) : previewUrl ? (
          <img
            src={previewUrl}
            alt={variant.headline || variant.hook}
            className="absolute inset-0 h-full w-full object-cover"
          />
        ) : failureMessage ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-3 text-center bg-amber-950/90">
            <span className="text-amber-200 text-[10px] font-bold uppercase tracking-wide mb-1">
              Video failed
            </span>
            <p className="text-white text-[10px] leading-snug">{failureMessage}</p>
          </div>
        ) : variant.format === 'video' || variant.format === 'reel' ? (
          <span className="text-white text-4xl opacity-80">▶</span>
        ) : (
          <span className="text-white text-3xl opacity-40">🖼</span>
        )}

        <span className="absolute top-2 left-2 bg-black/50 text-white text-[9px] font-bold px-1.5 py-0.5 rounded capitalize">
          {variant.format}
        </span>

        {onDelete && (
          <button
            type="button"
            title="Delete variant"
            className={cn(
              'absolute top-2 right-2 z-10 bg-black/55 hover:bg-red-600 text-white text-[10px] font-bold px-2 py-1 rounded transition-opacity',
              variant.status === 'FAILED' || variant.status === 'REJECTED'
                ? 'opacity-100'
                : 'opacity-100 sm:opacity-0 sm:group-hover:opacity-100'
            )}
            onClick={(e) => {
              e.stopPropagation()
              onDelete(variant.id)
            }}
          >
            Delete
          </button>
        )}

        {variant.performance_score != null && (
          <span
            className={cn(
              'absolute top-2 bg-mint text-navy text-[9px] font-black px-1.5 py-0.5 rounded',
              onDelete ? 'right-14' : 'right-2'
            )}
          >
            {variant.performance_score.toFixed(1)}×
          </span>
        )}

        <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/75 to-transparent px-2 pb-2 pt-6">
          <p className="text-white text-[10px] font-semibold leading-tight">
            {truncate(variant.hook, 60)}
          </p>
        </div>

        <div className="absolute inset-0 bg-navy/80 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 p-2">
          <div className="flex items-center justify-center gap-2 flex-wrap">
            <Button
              size="sm"
              variant="primary"
              onClick={(e) => {
                e.stopPropagation()
                onApprove(variant.id)
              }}
            >
              Approve
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={(e) => {
                e.stopPropagation()
                onReject(variant.id)
              }}
            >
              Reject
            </Button>
          </div>
          <div className="flex items-center justify-center gap-2 flex-wrap">
            {onRegenerate && (
              <Button
                size="sm"
                variant="outline"
                className="!text-white !border-white/60 hover:!bg-white/10"
                onClick={(e) => {
                  e.stopPropagation()
                  onRegenerate()
                }}
              >
                Regenerate…
              </Button>
            )}
            {onDelete && (
              <Button
                size="sm"
                variant="danger"
                onClick={(e) => {
                  e.stopPropagation()
                  onDelete(variant.id)
                }}
              >
                Delete
              </Button>
            )}
          </div>
        </div>
      </div>

      {videoUrl && (subtitlesMissing || logoMissing) && (
        <div className="px-2.5 py-1.5 space-y-1 border-t border-amber-200 bg-amber-50">
          {subtitlesMissing && (
            <p className="text-[10px] text-amber-900 leading-snug">
              {subtitleWarning || 'Subtitles missing — regenerate to apply captions from your speakable script/copy.'}
            </p>
          )}
          {logoMissing && (
            <p className="text-[10px] text-amber-900 leading-snug">
              {logoWarning || 'Brand logo missing on video — check Brand Kit upload and regenerate.'}
            </p>
          )}
        </div>
      )}

      <div className="px-2.5 py-2 flex items-center justify-between gap-2">
        <Badge variant={cb.variant} size="sm">
          {cb.label}
        </Badge>
        <div className="flex items-center gap-2">
          {(variant.status === 'FAILED' || variant.status === 'REJECTED') && onDelete && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onDelete(variant.id)
              }}
              className="text-[10px] font-bold text-red-600 hover:underline"
            >
              Delete
            </button>
          )}
          {variant.status === 'REJECTED' && onRegenerate && (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation()
                onRegenerate()
              }}
              className="text-[10px] font-bold text-mint hover:underline"
            >
              Regenerate
            </button>
          )}
          <span className="text-[10px] text-lt capitalize">{variant.status}</span>
        </div>
      </div>
    </div>
  )
}
