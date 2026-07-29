import type { GenerationCatalog, GenerationModelOption } from '@/types'

export type CostEstimate = {
  /** Total USD for all variants, or null when model not chosen yet */
  costUsd: number | null
  /** Per-unit USD shown in breakdown */
  unitUsd: number | null
  minutes: number | null
  modelLabel: string | null
  ready: boolean
  pendingReason: string | null
}

function findModel(
  catalog: GenerationCatalog | undefined | null,
  id: string | undefined | null,
  modality: 'image' | 'video'
): GenerationModelOption | undefined {
  if (!catalog || !id) return undefined
  const list = modality === 'image' ? catalog.image_models : catalog.video_models
  return list.find((m) => m.id === id)
}

/**
 * Estimate generation cost from the selected catalog model.
 * Never invents a dummy price — returns ready:false until a priced model is chosen.
 */
export function estimateGenerationCost(opts: {
  catalog?: GenerationCatalog | null
  mediaType: 'image' | 'video'
  imageModelId?: string
  videoModelId?: string
  variantCount: number
  videoDurationSeconds?: number
}): CostEstimate {
  const count = Math.max(0, Number(opts.variantCount) || 0)

  if (opts.mediaType === 'image') {
    const model = findModel(opts.catalog, opts.imageModelId, 'image')
    if (!model) {
      return {
        costUsd: null,
        unitUsd: null,
        minutes: null,
        modelLabel: null,
        ready: false,
        pendingReason: 'Select an image model on the brief page to see price',
      }
    }
    const unit = typeof model.cost_usd === 'number' ? model.cost_usd : null
    if (unit == null) {
      return {
        costUsd: null,
        unitUsd: null,
        minutes: null,
        modelLabel: model.label,
        ready: false,
        pendingReason: 'Pricing not available for this model yet',
      }
    }
    const seconds = model.estimated_seconds ?? 30
    return {
      costUsd: count * unit,
      unitUsd: unit,
      minutes: Math.max(1, Math.round((count * seconds) / 60)),
      modelLabel: model.label,
      ready: true,
      pendingReason: null,
    }
  }

  // Video
  const model = findModel(opts.catalog, opts.videoModelId, 'video')
  if (!model) {
    return {
      costUsd: null,
      unitUsd: null,
      minutes: null,
      modelLabel: null,
      ready: false,
      pendingReason: 'Select a video model to see price',
    }
  }
  const unit = typeof model.cost_usd === 'number' ? model.cost_usd : null
  if (unit == null) {
    return {
      costUsd: null,
      unitUsd: null,
      minutes: null,
      modelLabel: model.label,
      ready: false,
      pendingReason: 'Pricing not available for this model yet',
    }
  }
  const duration = Math.max(1, Number(opts.videoDurationSeconds) || 8)
  const perVariant =
    model.cost_unit === 'second' ? unit * duration : unit
  const seconds = model.estimated_seconds ?? Math.max(45, duration * 4)
  return {
    costUsd: count * perVariant,
    unitUsd: perVariant,
    minutes: Math.max(1, Math.round((count * seconds) / 60)),
    modelLabel: model.label,
    ready: true,
    pendingReason: null,
  }
}

export function formatUsd(amount: number | null | undefined): string {
  if (amount == null || Number.isNaN(amount)) return '—'
  return `$${amount.toFixed(2)}`
}
