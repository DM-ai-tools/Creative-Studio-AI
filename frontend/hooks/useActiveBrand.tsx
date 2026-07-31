'use client'

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react'

const STORAGE_KEY = 'cs-active-brand-id'
const CHANGE_EVENT = 'cs-active-brand-change'

function readStoredBrandId(): string | null {
  if (typeof window === 'undefined') return null
  try {
    return localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function writeStoredBrandId(id: string | null) {
  if (typeof window === 'undefined') return
  try {
    if (id) localStorage.setItem(STORAGE_KEY, id)
    else localStorage.removeItem(STORAGE_KEY)
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new CustomEvent(CHANGE_EVENT, { detail: id }))
}

interface ActiveBrandContextType {
  activeBrandId: string | null
  setActiveBrandId: (id: string | null) => void
}

const ActiveBrandContext = createContext<ActiveBrandContextType | null>(null)

export function ActiveBrandProvider({ children }: { children: React.ReactNode }) {
  // Hydrate from localStorage on first client render so sidebar/brief pages
  // see the last-selected brand immediately (avoids always flashing brands[0]).
  const [activeBrandId, setActiveBrandIdState] = useState<string | null>(() =>
    readStoredBrandId()
  )

  useEffect(() => {
    setActiveBrandIdState(readStoredBrandId())

    const onStorage = (e: StorageEvent) => {
      if (e.key === STORAGE_KEY) setActiveBrandIdState(e.newValue)
    }
    const onCustom = (e: Event) => {
      const detail = (e as CustomEvent<string | null>).detail
      setActiveBrandIdState(detail ?? null)
    }
    window.addEventListener('storage', onStorage)
    window.addEventListener(CHANGE_EVENT, onCustom)
    return () => {
      window.removeEventListener('storage', onStorage)
      window.removeEventListener(CHANGE_EVENT, onCustom)
    }
  }, [])

  const setActiveBrandId = useCallback((id: string | null) => {
    const next = (id || '').trim() || null
    setActiveBrandIdState(next)
    writeStoredBrandId(next)
  }, [])

  const value = useMemo(
    () => ({ activeBrandId, setActiveBrandId }),
    [activeBrandId, setActiveBrandId]
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
export function setActiveBrandIdGlobal(id: string | null) {
  writeStoredBrandId((id || '').trim() || null)
}
