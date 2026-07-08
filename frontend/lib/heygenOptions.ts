import type { CatalogOption } from '@/types'

export const HEYGEN_CUSTOM = 'custom'

export interface HeyGenVideoSettings {
  aspectRatio: string
  aspectRatioCustom: string
  scene: string
  sceneCustom: string
  cameraFraming: string
  cameraFramingCustom: string
  deliveryStyle: string
  deliveryStyleCustom: string
  brollInsert: string
  brollInsertCustom: string
  music: string
  musicCustom: string
  captions: boolean
  burnInCaptions: boolean
  brandStyledOverlay: boolean
  visualCues: string
  sceneBrollDirections: string
}

export const DEFAULT_HEYGEN_SETTINGS: HeyGenVideoSettings = {
  aspectRatio: '9:16',
  aspectRatioCustom: '',
  scene: 'office',
  sceneCustom: '',
  cameraFraming: 'medium_close',
  cameraFramingCustom: '',
  deliveryStyle: 'conversational',
  deliveryStyleCustom: '',
  brollInsert: 'directed',
  brollInsertCustom: '',
  music: 'upbeat_acoustic',
  musicCustom: '',
  captions: true,
  burnInCaptions: true,
  brandStyledOverlay: true,
  visualCues: '',
  sceneBrollDirections: '',
}

export const HEYGEN_ASPECT_OPTIONS: CatalogOption[] = [
  { id: '9:16', label: '9:16 — Reels / Stories' },
  { id: '1:1', label: '1:1 — Feed' },
  { id: '16:9', label: '16:9 — YouTube' },
]

export const HEYGEN_SCENE_OPTIONS: CatalogOption[] = [
  { id: 'office', label: 'Professional agency / IT office (recommended)' },
  { id: 'neutral_studio', label: 'Neutral studio (tech-agency backdrop)' },
  { id: 'coffee_shop', label: 'Coffee shop interior (warm)' },
  { id: 'outdoor', label: 'Outdoor natural light' },
]

export const HEYGEN_CAMERA_OPTIONS: CatalogOption[] = [
  { id: 'medium_close', label: 'Medium close-up' },
  { id: 'head_shoulders', label: 'Head & shoulders' },
  { id: 'waist_up', label: 'Waist up' },
]

export const HEYGEN_DELIVERY_OPTIONS: CatalogOption[] = [
  { id: 'conversational', label: 'Conversational (default)' },
  { id: 'energetic', label: 'Energetic' },
  { id: 'calm', label: 'Calm & authoritative' },
]

export const HEYGEN_BROLL_OPTIONS: CatalogOption[] = [
  { id: 'directed', label: 'Use my scene directions (recommended)' },
  { id: 'auto', label: 'Auto-suggest (HeyGen picks B-roll)' },
  { id: 'product', label: 'Product inserts' },
  { id: 'none', label: 'Avatar only' },
]

export const HEYGEN_MUSIC_OPTIONS: CatalogOption[] = [
  { id: 'upbeat_acoustic', label: 'Upbeat — acoustic' },
  { id: 'soft_ambient', label: 'Soft ambient' },
  { id: 'none', label: 'No music' },
]

function optionLabel(options: CatalogOption[], id: string): string {
  return options.find((o) => o.id === id)?.label ?? id
}

function resolvedLabel(
  options: CatalogOption[],
  id: string,
  customText: string
): string {
  if (id === HEYGEN_CUSTOM) {
    return customText.trim() || 'Custom'
  }
  return optionLabel(options, id)
}

function resolveFromApi(
  options: CatalogOption[],
  id: unknown,
  label: unknown,
  fallback: string
): { id: string; custom: string } {
  const sid = String(id ?? '').trim()
  if (options.some((o) => o.id === sid)) {
    return { id: sid || fallback, custom: '' }
  }
  const customText = String(label ?? sid).trim()
  if (customText) {
    return { id: HEYGEN_CUSTOM, custom: customText }
  }
  return { id: fallback, custom: '' }
}

/** Payload stored on brief.key_benefits.heygen_settings for the API. */
export function heygenSettingsForApi(settings: HeyGenVideoSettings) {
  return {
    aspect_ratio: settings.aspectRatio,
    aspect_ratio_label: resolvedLabel(
      HEYGEN_ASPECT_OPTIONS,
      settings.aspectRatio,
      settings.aspectRatioCustom
    ),
    aspect_ratio_custom: settings.aspectRatioCustom,
    scene: settings.scene,
    scene_label: resolvedLabel(HEYGEN_SCENE_OPTIONS, settings.scene, settings.sceneCustom),
    scene_custom: settings.sceneCustom,
    camera_framing: settings.cameraFraming,
    camera_framing_label: resolvedLabel(
      HEYGEN_CAMERA_OPTIONS,
      settings.cameraFraming,
      settings.cameraFramingCustom
    ),
    camera_framing_custom: settings.cameraFramingCustom,
    delivery_style: settings.deliveryStyle,
    delivery_style_label: resolvedLabel(
      HEYGEN_DELIVERY_OPTIONS,
      settings.deliveryStyle,
      settings.deliveryStyleCustom
    ),
    delivery_style_custom: settings.deliveryStyleCustom,
    broll_insert: settings.brollInsert,
    broll_insert_label: resolvedLabel(
      HEYGEN_BROLL_OPTIONS,
      settings.brollInsert,
      settings.brollInsertCustom
    ),
    broll_insert_custom: settings.brollInsertCustom,
    music: settings.music,
    music_label: resolvedLabel(HEYGEN_MUSIC_OPTIONS, settings.music, settings.musicCustom),
    music_custom: settings.musicCustom,
    captions: settings.captions,
    burn_in_captions: settings.burnInCaptions,
    brand_styled_overlay: settings.brandStyledOverlay,
    visual_cues: settings.visualCues,
    scene_broll_directions: settings.sceneBrollDirections,
  }
}

export function heygenSettingsFromApi(raw: Record<string, unknown> | undefined): HeyGenVideoSettings {
  if (!raw) return { ...DEFAULT_HEYGEN_SETTINGS }

  const aspect = resolveFromApi(
    HEYGEN_ASPECT_OPTIONS,
    raw.aspect_ratio,
    raw.aspect_ratio_label ?? raw.aspect_ratio_custom,
    DEFAULT_HEYGEN_SETTINGS.aspectRatio
  )
  const scene = resolveFromApi(
    HEYGEN_SCENE_OPTIONS,
    raw.scene,
    raw.scene_label ?? raw.scene_custom,
    DEFAULT_HEYGEN_SETTINGS.scene
  )
  const camera = resolveFromApi(
    HEYGEN_CAMERA_OPTIONS,
    raw.camera_framing,
    raw.camera_framing_label ?? raw.camera_framing_custom,
    DEFAULT_HEYGEN_SETTINGS.cameraFraming
  )
  const delivery = resolveFromApi(
    HEYGEN_DELIVERY_OPTIONS,
    raw.delivery_style,
    raw.delivery_style_label ?? raw.delivery_style_custom,
    DEFAULT_HEYGEN_SETTINGS.deliveryStyle
  )
  const broll = resolveFromApi(
    HEYGEN_BROLL_OPTIONS,
    raw.broll_insert,
    raw.broll_insert_label ?? raw.broll_insert_custom,
    DEFAULT_HEYGEN_SETTINGS.brollInsert
  )
  const music = resolveFromApi(
    HEYGEN_MUSIC_OPTIONS,
    raw.music,
    raw.music_label ?? raw.music_custom,
    DEFAULT_HEYGEN_SETTINGS.music
  )

  return {
    aspectRatio: aspect.id,
    aspectRatioCustom: aspect.custom || String(raw.aspect_ratio_custom ?? ''),
    scene: scene.id,
    sceneCustom: scene.custom || String(raw.scene_custom ?? ''),
    cameraFraming: camera.id,
    cameraFramingCustom: camera.custom || String(raw.camera_framing_custom ?? ''),
    deliveryStyle: delivery.id,
    deliveryStyleCustom: delivery.custom || String(raw.delivery_style_custom ?? ''),
    brollInsert: broll.id,
    brollInsertCustom: broll.custom || String(raw.broll_insert_custom ?? ''),
    music: music.id,
    musicCustom: music.custom || String(raw.music_custom ?? ''),
    captions: raw.captions !== false,
    burnInCaptions: raw.burn_in_captions !== false,
    brandStyledOverlay: raw.brand_styled_overlay !== false,
    visualCues: String(raw.visual_cues ?? ''),
    sceneBrollDirections: String(raw.scene_broll_directions ?? ''),
  }
}

export function withCustomOption(options: CatalogOption[]): CatalogOption[] {
  return [...options, { id: HEYGEN_CUSTOM, label: 'Custom…' }]
}
