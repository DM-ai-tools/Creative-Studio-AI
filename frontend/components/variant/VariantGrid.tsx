import React from 'react'
import VariantTile from './VariantTile'
import { variantGridClass } from '@/lib/creativeFormats'
import type { Variant } from '@/types'

interface VariantGridProps {
  variants: Variant[]
  isLoading?: boolean
  onApprove(id: string): void
  onReject(id: string): void
  onDelete?(id: string): void
  onRegenerate?(): void
  onView?(variant: Variant): void
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
  onView,
}: VariantGridProps) {
  if (isLoading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
        {Array.from({ length: 8 }).map((_, i) => <SkeletonTile key={i} />)}
      </div>
    )
  }

  if (variants.length === 0) {
    return (
      <div className="py-16 text-center">
        <div className="text-4xl mb-3">🎬</div>
        <p className="text-sm font-semibold text-mid">No variants yet</p>
        <p className="text-xs text-lt mt-1">Generate from a brief to create your first variant.</p>
      </div>
    )
  }

  return (
    <div className={variantGridClass(variants)}>
      {variants.map((v) => (
        <VariantTile
          key={v.id}
          variant={v}
          onApprove={onApprove}
          onReject={onReject}
          onDelete={onDelete}
          onRegenerate={onRegenerate}
          onView={onView ?? (() => {})}
        />
      ))}
    </div>
  )
}
