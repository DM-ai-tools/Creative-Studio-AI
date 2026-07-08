/** Runway single-clip lengths (seconds). */
export const SHORT_VIDEO_DURATIONS = [5, 6, 8, 10, 12, 15] as const

/** Selecting 30 enables master script mode (8+8+8+6 = 30s total). */
export const MASTER_VIDEO_DURATION = 30

/** HeyGen / long-form ad lengths (seconds). */
export const EXTENDED_VIDEO_DURATIONS = [60, 90, 120, 180, 240] as const

export const MAX_VIDEO_DURATION_SECONDS = 240

export function isMaster30Duration(seconds: number | string | undefined): boolean {
  return Number(seconds) === MASTER_VIDEO_DURATION
}

export function isExtendedDuration(seconds: number | string | undefined): boolean {
  return EXTENDED_VIDEO_DURATIONS.includes(Number(seconds) as (typeof EXTENDED_VIDEO_DURATIONS)[number])
}

export function formatVideoDurationLabel(seconds: number): string {
  if (isMaster30Duration(seconds)) return '30s Master script'
  if (seconds === 60) return '1m'
  if (seconds === 90) return '1m 30s'
  if (seconds === 120) return '2m'
  if (seconds === 180) return '3m'
  if (seconds === 240) return '4m'
  return `${seconds}s`
}
