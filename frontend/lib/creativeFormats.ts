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
  if (hasPortrait && hasLandscape) return '9:16 Portrait · 16:9 Landscape — 30s each'
  if (hasPortrait) return '9:16 (Portrait) — up to 30 seconds'
  if (hasLandscape) return '16:9 (Landscape) — up to 30 seconds'
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
