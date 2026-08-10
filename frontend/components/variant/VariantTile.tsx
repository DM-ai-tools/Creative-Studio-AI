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
  /** Retry this variant only (image). */
  onRegenerate?(): void
  /** Open batch regenerate modal. */
  onRegenerateBatch?(): void
  onView(variant: Variant): void
  isRegenerating?: boolean
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
  onRegenerateBatch,
  onView,
  isRegenerating,
}: VariantTileProps) {
  const cb = complianceBadge[variant.compliance_status as ComplianceStatus] ?? complianceBadge.PENDING
  const gradientClass = getFormatColor(variant.format)
  const {
    imageUrl: previewUrl,
    videoUrl,
    videoFailed,
    imageFailed,
    imageError,
    missingMotionMedia,
    videoError,
    subtitlesMissing,
    subtitleWarning,
    logoMissing,
    logoWarning,
  } = getVariantPreviewUrls(variant)

  const isLandscape = variant.format === 'video'
  const isPortrait = variant.format === 'reel'
  const isMotionVariant = isLandscape || isPortrait

  const imageFailureMessage =
    imageFailed || (!previewUrl && !isMotionVariant && (variant.status === 'READY' || variant.status === 'FAILED'))
      ? formatVideoErrorMessage(imageError) ||
        'Image not generated. Check Runway model settings, then regenerate.'
      : null

  const videoFailureMessage =
    variant.status === 'FAILED' || videoFailed || missingMotionMedia
      ? formatVideoErrorMessage(videoError) || 'Video not generated'
      : null

  const failureMessage = isMotionVariant ? videoFailureMessage : imageFailureMessage
  const failureLabel = isMotionVariant ? 'Video failed' : 'Image failed'
  const showImageRetry = !isMotionVariant && Boolean(imageFailureMessage) && Boolean(onRegenerate)
  const busy = Boolean(isRegenerating)

  // Inline aspect classes so Tailwind scanner always includes them
  const aspectClass = isLandscape
    ? 'aspect-video'
    : isPortrait
      ? 'aspect-[9/16]'
      : 'aspect-square'

  return (
    <div className="rounded-xl border border-border bg-surface-elevated shadow-card overflow-hidden group hover:shadow-card-hover transition-all duration-300">
      {/* ── Video / Image preview ── */}
      <div
        className={cn(
          'relative w-full bg-black cursor-pointer overflow-hidden',
          aspectClass,
          !videoUrl && !previewUrl && gradientClass,
          (!videoUrl && !previewUrl) && 'flex items-center justify-center'
        )}
        onClick={() => onView(variant)}
      >
        {videoUrl ? (
          <video
            src={videoUrl}
            className="absolute inset-0 h-full w-full object-cover"
            muted
            playsInline
            preload="none"
          />
        ) : previewUrl ? (
          <img
            src={previewUrl}
            alt={variant.headline || variant.hook}
            className="absolute inset-0 h-full w-full object-cover"
            loading="lazy"
            decoding="async"
          />
        ) : failureMessage ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center bg-amber-950/90">
            {busy ? (
              <>
                <span className="text-amber-200 text-[10px] font-bold uppercase tracking-wide">Retrying image…</span>
                <p className="text-white/80 text-[10px] leading-snug">This variant only — others stay as they are.</p>
              </>
            ) : (
              <>
                <span className="text-amber-200 text-[10px] font-bold uppercase tracking-wide mb-1">{failureLabel}</span>
                <p className="text-white text-[10px] leading-snug">{failureMessage}</p>
                {showImageRetry && (
                  <Button
                    size="sm"
                    variant="primary"
                    className="mt-1"
                    onClick={(e) => {
                      e.stopPropagation()
                      onRegenerate?.()
                    }}
                  >
                    Retry this image
                  </Button>
                )}
              </>
            )}
          </div>
        ) : busy ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center p-4 text-center bg-navy/80">
            <span className="text-mint text-[10px] font-bold uppercase tracking-wide">Generating image…</span>
          </div>
        ) : (
          <span className="text-white text-4xl opacity-60">▶</span>
        )}

        {/* Format badge */}
        <span className="absolute top-2 left-2 bg-black/60 text-white text-[9px] font-bold px-2 py-0.5 rounded-full capitalize tracking-wide">
          {isLandscape ? '16:9' : variant.format === 'reel' ? '9:16' : variant.format}
        </span>

        {/* Performance score */}
        {variant.performance_score != null && (
          <span className={cn(
            'absolute top-2 bg-mint text-navy text-[9px] font-black px-1.5 py-0.5 rounded-full',
            onDelete ? 'right-14' : 'right-2'
          )}>
            {variant.performance_score.toFixed(1)}×
          </span>
        )}

        {/* Delete button */}
        {onDelete && (
          <button
            type="button"
            title="Delete variant"
            className={cn(
              'absolute top-2 right-2 z-10 bg-black/60 hover:bg-red-600 text-white text-[9px] font-bold px-2 py-0.5 rounded-full transition-all',
              variant.status === 'FAILED' || variant.status === 'REJECTED'
                ? 'opacity-100'
                : 'opacity-0 group-hover:opacity-100'
            )}
            onClick={(e) => { e.stopPropagation(); onDelete(variant.id) }}
          >
            ✕
          </button>
        )}

        {/* Hook text overlay */}
        {(videoUrl || previewUrl) && (
          <div className="absolute bottom-0 left-0 right-0 bg-gradient-to-t from-black/80 to-transparent px-3 pb-2 pt-8">
            <p className="text-white text-[10px] font-semibold leading-snug drop-shadow">
              {truncate(variant.hook, isLandscape ? 80 : 55)}
            </p>
          </div>
        )}

        {/* Hover action overlay */}
        <div className="absolute inset-0 bg-navy/85 opacity-0 group-hover:opacity-100 transition-opacity flex flex-col items-center justify-center gap-2 p-3">
          <div className="flex items-center justify-center gap-2 flex-wrap">
            <Button size="sm" variant="primary" onClick={(e) => { e.stopPropagation(); onApprove(variant.id) }}>
              Approve
            </Button>
            <Button size="sm" variant="danger" onClick={(e) => { e.stopPropagation(); onReject(variant.id) }}>
              Reject
            </Button>
          </div>
          {onRegenerate && (
            <Button
              size="sm"
              variant="outline"
              className="!text-white !border-white/60 hover:!bg-white/10"
              disabled={busy}
              onClick={(e) => {
                e.stopPropagation()
                onRegenerate()
              }}
            >
              {showImageRetry ? 'Retry this image' : 'Regenerate this…'}
            </Button>
          )}
          {onRegenerateBatch && (
            <button
              type="button"
              className="text-[10px] text-white/70 hover:text-white underline"
              onClick={(e) => {
                e.stopPropagation()
                onRegenerateBatch()
              }}
            >
              Generate new variants…
            </button>
          )}
        </div>
      </div>

      {/* ── Warnings ── */}
      {videoUrl && (subtitlesMissing || logoMissing) && (
        <div className="px-3 py-1.5 space-y-0.5 border-t border-amber-200 bg-amber-50">
          {subtitlesMissing && (
            <p className="text-[9px] text-amber-900 leading-snug">{subtitleWarning || 'Subtitles missing — regenerate.'}</p>
          )}
          {logoMissing && (
            <p className="text-[9px] text-amber-900 leading-snug">{logoWarning || 'Brand logo missing — regenerate.'}</p>
          )}
        </div>
      )}

      {isMotionVariant && videoUrl === null && missingMotionMedia === false && variant.status === 'READY' && !previewUrl && (
        <div className="px-3 py-1.5 border-t border-amber-200 bg-amber-50">
          <p className="text-[9px] text-amber-900 leading-snug">
            Video metadata exists but the file is missing (often wiped after Railway redeploy).
            Re-upload Brand Kit logo, attach a Railway volume at /app/uploads, then regenerate.
          </p>
        </div>
      )}

      {!isMotionVariant && imageFailureMessage && (
        <div className="px-3 py-1.5 border-t border-amber-200 bg-amber-50 flex items-start justify-between gap-2">
          <p className="text-[9px] text-amber-900 leading-snug flex-1">{imageFailureMessage}</p>
          {onRegenerate && (
            <button
              type="button"
              disabled={busy}
              onClick={(e) => {
                e.stopPropagation()
                onRegenerate()
              }}
              className="shrink-0 text-[9px] font-bold text-mint hover:underline disabled:opacity-50"
            >
              {busy ? 'Retrying…' : 'Retry image'}
            </button>
          )}
        </div>
      )}

      {/* ── Bottom bar ── */}
      <div className="px-3 py-2 flex items-center justify-between gap-2">
        <Badge variant={cb.variant} size="sm">{cb.label}</Badge>
        <div className="flex items-center gap-2">
          {(variant.status === 'FAILED' || variant.status === 'REJECTED') && onDelete && (
            <button
              type="button"
              onClick={(e) => { e.stopPropagation(); onDelete(variant.id) }}
              className="text-[9px] font-bold text-red-500 hover:underline"
            >
              Delete
            </button>
          )}
          {(variant.status === 'FAILED' || variant.status === 'REJECTED' || showImageRetry) && onRegenerate && (
            <button
              type="button"
              disabled={busy}
              onClick={(e) => { e.stopPropagation(); onRegenerate() }}
              className="text-[9px] font-bold text-mint hover:underline disabled:opacity-50"
            >
              {busy ? 'Retrying…' : showImageRetry ? 'Retry image' : 'Regenerate'}
            </button>
          )}
          <span className="text-[9px] text-lt capitalize">{busy ? 'generating' : variant.status}</span>
        </div>
      </div>
    </div>
  )
}
