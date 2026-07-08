import type { CatalogOption } from '@/types'

/** UI labels — internal ids stay `video` / `reel` for API compatibility. */
export const CREATIVE_FORMAT_LABELS: Record<string, string> = {
  static: 'Static',
  video: 'Landscape',
  reel: 'Portrait',
  carousel: 'Carousel',
}

/** UI labels for platform placements (backend ids unchanged). */
export const PLACEMENT_LABELS: Record<string, string> = {
  feed: 'Feed (1:1, 4:5)',
  landscape: 'Landscape (16:9)',
  reels: 'Portrait — Reels (9:16)',
  stories: 'Portrait — Stories (9:16)',
  marketplace: 'Marketplace (1:1)',
}

const LANDSCAPE_PLACEMENT_FALLBACK: CatalogOption = {
  id: 'landscape',
  label: PLACEMENT_LABELS.landscape,
}

export function mapPlacementOptions(options: CatalogOption[]): CatalogOption[] {
  const base =
    options.length && !options.some((o) => o.id === 'landscape')
      ? [options[0], LANDSCAPE_PLACEMENT_FALLBACK, ...options.slice(1)]
      : options.length
        ? options
        : [
            { id: 'feed', label: PLACEMENT_LABELS.feed },
            LANDSCAPE_PLACEMENT_FALLBACK,
            { id: 'reels', label: PLACEMENT_LABELS.reels },
            { id: 'stories', label: PLACEMENT_LABELS.stories },
            { id: 'marketplace', label: PLACEMENT_LABELS.marketplace },
          ]
  return base.map((o) => ({
    ...o,
    label: PLACEMENT_LABELS[o.id] ?? o.label,
  }))
}

export function isPortraitPlacement(id: string): boolean {
  return id === 'reels' || id === 'stories'
}

export function isLandscapePlacement(id: string): boolean {
  return id === 'landscape'
}

export function isVideoFormat(id: string): boolean {
  return id === 'video' || id === 'reel'
}

export function isPortraitVideoFormat(id: string): boolean {
  return id === 'reel'
}

export function isLandscapeVideoFormat(id: string): boolean {
  return id === 'video'
}

/** CSS aspect class for video preview tiles and detail modals. */
export function videoPreviewAspectClass(format: string): string {
  if (format === 'reel' || format === 'stories') return 'aspect-[9/16] w-full'
  if (format === 'video') return 'aspect-video w-full'
  return 'aspect-square w-full'
}

/** object-fit for detail modal view — shows full video without cropping */
export function videoModalObjectFit(format: string): 'cover' | 'contain' {
  return format === 'video' ? 'contain' : 'cover'
}

/** Grid layout — landscape tiles use 2 cols on medium screens, portrait uses 3-4 */
export function variantGridClass(variants: { format: string }[]): string {
  const hasLandscape = variants.some((v) => v.format === 'video')
  const hasPortrait = variants.some((v) => v.format === 'reel' || v.format === 'stories')
  if (hasLandscape && !hasPortrait) {
    return 'grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3'
  }
  if (hasLandscape && hasPortrait) {
    return 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3'
  }
  return 'grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3'
}

export function mapCreativeFormatOptions(options: CatalogOption[]): CatalogOption[] {
  return options.map((o) => ({
    ...o,
    label: CREATIVE_FORMAT_LABELS[o.id] ?? o.label,
  }))
}

export function aspectHintFromFormats(
  formats: string[],
  placements: string[] = []
): string {
  const hasPortrait = formats.includes('reel')
  const hasLandscape = formats.includes('video')
  if (hasPortrait && hasLandscape) return '9:16 Portrait · 16:9 Landscape — up to 4 minutes each'
  if (hasPortrait) return '9:16 (Portrait) — up to 4 minutes'
  if (hasLandscape) return '16:9 (Landscape) — up to 4 minutes'
  const hasLandscapePlacement = placements.some(isLandscapePlacement)
  const hasPortraitPlacement = placements.some(isPortraitPlacement)
  if (hasLandscapePlacement && hasPortraitPlacement) {
    return '16:9 Landscape · 9:16 Portrait'
  }
  if (hasLandscapePlacement) return '16:9 (Landscape)'
  if (hasPortraitPlacement) return '9:16 (Portrait)'
  if (placements.some((p) => p === 'feed')) return '1:1 or 4:5'
  return 'Select a placement (Landscape 16:9 or Portrait 9:16)'
}

export function formatDisplayLabel(id: string): string {
  return CREATIVE_FORMAT_LABELS[id] ?? id
}
