export type ImageVisualStyleId =
  | ''
  | 'auto'
  | 'sketch_illustration'
  | 'flat_cartoon'
  | 'clay_3d'
  | '3d_metaphor'

export interface ImageVisualStyleOption {
  value: ImageVisualStyleId
  label: string
  hint: string
}

/** Optional campaign visual treatment — influences image prompts (not typography). */
export const IMAGE_VISUAL_STYLE_OPTIONS: ImageVisualStyleOption[] = [
  {
    value: '',
    label: 'Auto (AI decides)',
    hint: 'Photography or graphic card based on use case and MD brief.',
  },
  {
    value: 'sketch_illustration',
    label: 'Sketch / hand-drawn',
    hint: 'Cross-hatched pencil editorial on parchment — educational diagram style.',
  },
  {
    value: 'flat_cartoon',
    label: 'Flat cartoon',
    hint: 'Exhausted character + competitor empties scattered — hero product fresh in corner (any industry).',
  },
  {
    value: 'clay_3d',
    label: '3D clay / figurine',
    hint: 'Before/after figurines — failed alternatives in early panels, hero product in final panel.',
  },
  {
    value: '3d_metaphor',
    label: '3D metaphor',
    hint: 'Symbolic 3D scene + hero product as solution — never hero brand on failed props.',
  },
]

export function normalizeImageVisualStyle(value: unknown): ImageVisualStyleId {
  const raw = String(value || '').trim().toLowerCase().replace(/-/g, '_')
  if (!raw || raw === 'auto') return ''
  if (IMAGE_VISUAL_STYLE_OPTIONS.some((o) => o.value === raw)) return raw as ImageVisualStyleId
  return ''
}

export function imageVisualStyleLabel(value: unknown): string {
  const id = normalizeImageVisualStyle(value)
  if (!id) return IMAGE_VISUAL_STYLE_OPTIONS[0].label
  return IMAGE_VISUAL_STYLE_OPTIONS.find((o) => o.value === id)?.label ?? 'Custom'
}
