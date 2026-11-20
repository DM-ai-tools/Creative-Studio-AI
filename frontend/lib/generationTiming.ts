/**
 * How long this account's images really take, measured in the browser and remembered (last 10 runs).
 * The image service reports no progress, so the % on a generating tile is time elapsed over this number.
 */
const KEY = 'cs-image-seconds'
export const DEFAULT_IMAGE_SECONDS = 50

function readAll(): number[] {
  try {
    const raw = JSON.parse(window.localStorage.getItem(KEY) || '[]')
    return Array.isArray(raw) ? raw.map(Number).filter((n) => Number.isFinite(n) && n >= 8 && n <= 600) : []
  } catch {
    return []
  }
}

/** The typical time for one image, in seconds (median of the measured runs, else a sensible default). */
export function expectedImageSeconds(): number {
  const all = readAll().sort((a, b) => a - b)
  if (!all.length) return DEFAULT_IMAGE_SECONDS
  return Math.round(all[Math.floor(all.length / 2)])
}

/** Remember how long an image really took. Absurdly short or long runs are ignored. */
export function recordImageSeconds(seconds: number): void {
  if (!Number.isFinite(seconds) || seconds < 8 || seconds > 600) return
  try {
    window.localStorage.setItem(KEY, JSON.stringify([...readAll(), Math.round(seconds)].slice(-10)))
  } catch {
    /* storage can be blocked: the default is used */
  }
}
