/** Runway single-clip lengths (seconds). */
export const SHORT_VIDEO_DURATIONS = [5, 6, 8, 10, 12, 15] as const

/** Selecting 30 enables master script mode (8+8+8+6 = 30s total). */
export const MASTER_VIDEO_DURATION = 30

export function isMaster30Duration(seconds: number | string | undefined): boolean {
  return Number(seconds) === MASTER_VIDEO_DURATION
}

export function formatVideoDurationLabel(seconds: number): string {
  if (isMaster30Duration(seconds)) return '30s Master script'
  return `${seconds}s`
}
