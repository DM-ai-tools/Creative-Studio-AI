import React from 'react'
import { motion, useReducedMotion } from 'framer-motion'
import VariantTile from './VariantTile'
import GeneratingDots from './GeneratingDots'
import EmptyState from '@/components/ui/EmptyState'
import { Images } from 'lucide-react'
import { variantGridClass } from '@/lib/creativeFormats'
import type { Variant } from '@/types'

interface VariantGridProps {
  variants: Variant[]
  isLoading?: boolean
  onApprove(id: string): void
  onReject(id: string): void
  onDelete?(id: string): void
  /** Per-variant regenerate (e.g. retry failed image only). */
  onRegenerate?(variantId: string): void
  /** Opens the batch regenerate settings modal (all-new generation). */
  onRegenerateBatch?(): void
  onView?(variant: Variant): void
  regeneratingId?: string | null
  /** Creatives still being made that have no row yet: shown as live "generating" tiles. */
  pendingCount?: number
  /** CSS aspect-ratio for those tiles, e.g. "1 / 1". */
  pendingAspect?: string
  /** When the run began (ms) and the usual seconds per image, so every tile's % agrees. */
  generatingStartedAt?: number
  expectedSeconds?: number
}

function SkeletonTile() {
  return (
    <div className="bg-white border border-border rounded-xl overflow-hidden">
      <div className="aspect-square skeleton" />
      <div className="p-2.5 flex justify-between">
        <div className="skeleton h-4 w-16 rounded-full" />
        <div className="skeleton h-4 w-12 rounded" />
      </div>
    </div>
  )
}

export default function VariantGrid({
  variants,
  isLoading,
  onApprove,
  onReject,
  onDelete,
  onRegenerate,
  onRegenerateBatch,
  onView,
  regeneratingId,
  pendingCount = 0,
  pendingAspect = '1 / 1',
  generatingStartedAt,
  expectedSeconds,
}: VariantGridProps) {
  const reduce = useReducedMotion()

  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => <SkeletonTile key={i} />)}
      </div>
    )
  }

  if (variants.length === 0 && pendingCount === 0) {
    return (
      <EmptyState
        icon={Images}
        title="No creatives yet"
        description="Generate from a brief and your first creative will appear here."
      />
    )
  }

  return (
    <div className={variants.length ? variantGridClass(variants) : 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3'}>
      {variants.map((v, i) => (
        <motion.div
          key={v.id}
          initial={reduce ? false : { opacity: 0, y: 14, scale: 0.98 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1], delay: reduce ? 0 : Math.min(i, 8) * 0.05 }}
        >
        <VariantTile
          variant={v}
          onApprove={onApprove}
          onReject={onReject}
          onDelete={onDelete}
          onRegenerate={onRegenerate ? () => onRegenerate(v.id) : undefined}
          onRegenerateBatch={onRegenerateBatch}
          onView={onView ?? (() => {})}
          isRegenerating={regeneratingId === v.id || v.status === 'GENERATING'}
          generatingStartedAt={generatingStartedAt}
          expectedSeconds={expectedSeconds}
        />
        </motion.div>
      ))}
      {Array.from({ length: pendingCount }).map((_, i) => (
        <div
          key={`pending-${i}`}
          className="rounded-xl border border-border bg-surface-elevated shadow-card overflow-hidden"
        >
          <div className="relative w-full" style={{ aspectRatio: pendingAspect }}>
            <GeneratingDots expectedSeconds={expectedSeconds} startedAt={generatingStartedAt} />
          </div>
          <div className="px-3 py-2 flex items-center justify-between">
            <span className="text-[10px] font-semibold text-mid">Creative {variants.length + i + 1}</span>
            <span className="text-[10px] text-lt">Creating…</span>
          </div>
        </div>
      ))}
    </div>
  )
}
