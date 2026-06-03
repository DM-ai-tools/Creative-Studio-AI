'use client'

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { authApi } from '@/lib/api'
import { authStorage } from '@/lib/auth'
import type { User } from '@/types'

interface AuthContextType {
  user: User | null
  isLoading: boolean
  isAuthenticated: boolean
  login(email: string, password: string): Promise<void>
  register(data: { email: string; password: string; full_name: string; tenant_name: string }): Promise<void>
  logout(): Promise<void>
  refreshUser(): Promise<void>
}

const AuthContext = createContext<AuthContextType | null>(null)

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null)
  const [isLoading, setIsLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    try {
      const me = await authApi.getMe()
      setUser(me)
      authStorage.setUser(me)
    } catch {
      authStorage.clear()
      setUser(null)
    }
  }, [])

  useEffect(() => {
    const token = authStorage.getAccessToken()
    if (!token) {
      setIsLoading(false)
      return
    }

    const cached = authStorage.getUser()
    if (cached) {
      setUser(cached)
      setIsLoading(false)
    }

    let cancelled = false
    const timeout = window.setTimeout(() => {
      if (!cancelled) setIsLoading(false)
    }, 8000)

    refreshUser().finally(() => {
      cancelled = true
      window.clearTimeout(timeout)
      setIsLoading(false)
    })

    return () => {
      cancelled = true
      window.clearTimeout(timeout)
    }
  }, [refreshUser])

  const login = useCallback(async (email: string, password: string) => {
    const data = await authApi.login({ email, password })
    authStorage.setTokens(data.access_token, data.refresh_token)
    authStorage.setUser(data.user)
    setUser(data.user)
  }, [])

  const register = useCallback(
    async (data: { email: string; password: string; full_name: string; tenant_name: string }) => {
      const res = await authApi.register(data)
      authStorage.setTokens(res.access_token, res.refresh_token)
      authStorage.setUser(res.user)
      setUser(res.user)
    },
    []
  )

  const logout = useCallback(async () => {
    try { await authApi.logout() } catch { /* ignore */ }
    authStorage.clear()
    setUser(null)
  }, [])

  return (
    <AuthContext.Provider
      value={{ user, isLoading, isAuthenticated: !!user, login, register, logout, refreshUser }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextType {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within AuthProvider')
  return ctx
}
