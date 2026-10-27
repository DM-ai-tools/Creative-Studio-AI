'use client'

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'
import { useAuth } from '@/hooks/useAuth'

const LEGACY_STORAGE_KEY = 'cs-active-brand-id'
const CHANGE_EVENT = 'cs-active-brand-change'

function storageKeyForUser(userId: string | undefined): string | null {
  const id = (userId || '').trim()
  return id ? `${LEGACY_STORAGE_KEY}:${id}` : null
}

function readStoredBrandId(userId: string | undefined): string | null {
  if (typeof window === 'undefined') return null
  const key = storageKeyForUser(userId)
  if (!key) return null
  try {
    return localStorage.getItem(key)
  } catch {
    return null
  }
}

function writeStoredBrandId(userId: string | undefined, id: string | null) {
  if (typeof window === 'undefined') return
  const key = storageKeyForUser(userId)
  if (!key) return
  try {
    if (id) localStorage.setItem(key, id)
    else localStorage.removeItem(key)
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: { userId, brandId: id } }))
}

interface ActiveBrandContextType {
  activeBrandId: string | null
  setActiveBrandId: (id: string | null) => void
}

const ActiveBrandContext = createContext<ActiveBrandContextType | null>(null)

export function ActiveBrandProvider({ children }: { children: React.ReactNode }) {
  const { user } = useAuth()
  const userId = user?.id

  const [activeBrandId, setActiveBrandIdState] = useState<string | null>(null)

  useEffect(() => {
    setActiveBrandIdState(readStoredBrandId(userId))
  }, [userId])

  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      const key = storageKeyForUser(userId)
      if (key && e.key === key) setActiveBrandIdState(e.newValue)
    }
    const onCustom = (e: Event) => {
      const detail = (e as CustomEvent<{ userId?: string; brandId?: string | null }>).detail
      if (detail?.userId && detail.userId !== userId) return
      setActiveBrandIdState(detail?.brandId ?? null)
    }
    window.addEventListener('storage', onStorage)
    window.addEventListener(CHANGE_EVENT, onCustom)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(CHANGE_EVENT, onCustom)
    }
  }, [userId])

  const setActiveBrandId = useCallback(
    (id: string | null) => {
      const next = (id || '').trim() || null
      setActiveBrandIdState(next)
      writeStoredBrandId(userId, next)
    },
    [userId],
  )

  const value = useMemo(
    () => ({ activeBrandId, setActiveBrandId }),
    [activeBrandId, setActiveBrandId],
  )

  return (
    <ActiveBrandContext.Provider value={value}>{children}</ActiveBrandContext.Provider>
  )
}

export function useActiveBrand() {
  const ctx = useContext(ActiveBrandContext)
  if (!ctx) {
    throw new Error('useActiveBrand must be used within ActiveBrandProvider')
  }
  return ctx
}

/** Safe setter for pages that may run outside the provider (should not happen in dashboard). */
export function setActiveBrandIdGlobal(id: string | null, userId?: string) {
  writeStoredBrandId(userId, (id || '').trim() || null)
}
