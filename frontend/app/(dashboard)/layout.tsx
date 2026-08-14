'use client'

import React, { useEffect, useState } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Sidebar from '@/components/layout/Sidebar'
import { PageLoader } from '@/components/ui/Loading'
import { AuthProvider, useAuth } from '@/hooks/useAuth'
import { ActiveBrandProvider, useActiveBrand } from '@/hooks/useActiveBrand'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { brandsApi } from '@/lib/api'
import { agencyIndustryLabel } from '@/lib/industries'
import { cn } from '@/lib/utils'

function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, isLoading, logout } = useAuth()
  const { activeBrandId, setActiveBrandId } = useActiveBrand()
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const { data: brands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands',
    ttlMs: API_CACHE_TTL.brands,
  })

  useEffect(() => {
    if (!isLoading && !user) router.replace('/login')
  }, [user, isLoading, router])

  useEffect(() => {
    document.body.style.overflow = ''
  }, [pathname])

  useEffect(() => {
    try {
      const saved = localStorage.getItem('sidebar-open')
      if (saved !== null) setSidebarOpen(saved === 'true')
    } catch {
      /* ignore */
    }
  }, [])

  const toggleSidebar = () => {
    setSidebarOpen((prev) => {
      const next = !prev
      try {
        localStorage.setItem('sidebar-open', String(next))
      } catch {
        /* ignore */
      }
      return next
    })
  }

  // If nothing selected yet, pick first brand. Only reset when the active id is truly gone
  // (deleted), not while a freshly saved brand is waiting on list refetch.
  useEffect(() => {
    if (!brands?.length) return
    if (!activeBrandId) {
      setActiveBrandId(brands[0].id)
      return
    }
    if (brands.some((b) => b.id === activeBrandId)) return
    setActiveBrandId(brands[0].id)
  }, [brands, activeBrandId, setActiveBrandId])

  if (isLoading && !user) return <PageLoader />
  if (!user) return null

  const activeBrand =
    (activeBrandId ? brands?.find((b) => b.id === activeBrandId) : undefined) ??
    brands?.[0]
  const brandSubtitle = activeBrand?.industry
    ? agencyIndustryLabel(activeBrand.industry)
    : undefined

  const handleLogout = async () => {
    await logout()
    toast.success('Signed out')
    router.push('/login')
  }

  return (
    <div className="flex h-screen max-h-screen overflow-hidden bg-mesh">
      {/* Sidebar sits in the flex flow — never overlays content */}
      <div
        className={cn(
          'hidden md:flex flex-shrink-0 h-screen transition-[width] duration-200 ease-out',
          sidebarOpen ? 'w-[240px]' : 'w-14'
        )}
      >
        <Sidebar
          user={user}
          brandName={activeBrand?.name}
          brandSubtitle={brandSubtitle || undefined}
          onLogout={handleLogout}
          collapsed={!sidebarOpen}
          onToggleCollapse={toggleSidebar}
        />
      </div>

      {/* Content starts after sidebar — title never covered */}
      <main className="flex-1 min-w-0 h-screen overflow-y-auto overflow-x-hidden">
        {children}
      </main>
    </div>
  )
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <ActiveBrandProvider>
        <DashboardShell>{children}</DashboardShell>
      </ActiveBrandProvider>
    </AuthProvider>
  )
}
