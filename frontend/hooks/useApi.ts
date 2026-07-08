'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { clearApiCache, getApiCache, setApiCache } from '@/lib/apiCache'

export type UseApiOptions = {
  /** Stable key — enables in-memory cache and instant revisits */
  cacheKey?: string
  ttlMs?: number
}

export function useApi<T>(
  fetcher: () => Promise<T>,
  deps: unknown[] = [],
  options?: UseApiOptions
): { data: T | null; isLoading: boolean; error: string | null; refetch: () => void } {
  const cacheKey = options?.cacheKey
  const ttlMs = options?.ttlMs ?? 60_000

  const [data, setData] = useState<T | null>(() => {
    if (!cacheKey) return null
    return getApiCache<T>(cacheKey, ttlMs)
  })
  const [isLoading, setIsLoading] = useState(() => {
    if (!cacheKey) return true
    return getApiCache<T>(cacheKey, ttlMs) === null
  })
  const [error, setError] = useState<string | null>(null)
  const mountedRef = useRef(true)

  const load = useCallback(
    async (opts?: { background?: boolean }) => {
      const cached = cacheKey ? getApiCache<T>(cacheKey, ttlMs) : null
      if (cached) {
        setData(cached)
        if (!opts?.background) setIsLoading(false)
      } else if (!opts?.background) {
        setIsLoading(true)
      }
      setError(null)
      try {
        const result = await fetcher()
        if (mountedRef.current) {
          setData(result)
          if (cacheKey) setApiCache(cacheKey, result)
        }
      } catch (err: unknown) {
        if (mountedRef.current) {
          const msg =
            (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
            'An error occurred'
          setError(msg)
        }
      } finally {
        if (mountedRef.current) setIsLoading(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [...deps, cacheKey, ttlMs]
  )

  const refetch = useCallback(
    (opts?: { background?: boolean }) => {
      if (cacheKey && !opts?.background) clearApiCache(cacheKey)
      return load({ background: opts?.background })
    },
    [cacheKey, load]
  )

  useEffect(() => {
    mountedRef.current = true
    const cached = cacheKey ? getApiCache<T>(cacheKey, ttlMs) : null
    load({ background: !!cached })
    return () => {
      mountedRef.current = false
    }
  }, [load, cacheKey, ttlMs])

  return { data, isLoading, error, refetch }
}
