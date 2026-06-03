const store = new Map<string, { data: unknown; ts: number }>()

export function getApiCache<T>(key: string, ttlMs: number): T | null {
  const hit = store.get(key)
  if (!hit) return null
  if (Date.now() - hit.ts > ttlMs) {
    store.delete(key)
    return null
  }
  return hit.data as T
}

export function setApiCache<T>(key: string, data: T): void {
  store.set(key, { data, ts: Date.now() })
}

export function clearApiCache(key?: string): void {
  if (key) store.delete(key)
  else store.clear()
}

export const API_CACHE_TTL = {
  catalog: 30 * 60 * 1000,
  brands: 5 * 60 * 1000,
  briefs: 60 * 1000,
  stats: 60 * 1000,
  variants: 60 * 1000,
} as const
