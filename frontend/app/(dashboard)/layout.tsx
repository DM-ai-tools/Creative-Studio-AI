'use client'

import React, { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Sidebar from '@/components/layout/Sidebar'
import { PageLoader } from '@/components/ui/Loading'
import { AuthProvider, useAuth } from '@/hooks/useAuth'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { brandsApi } from '@/lib/api'
import { agencyIndustryLabel } from '@/lib/industries'

function DashboardShell({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const pathname = usePathname()
  const { user, isLoading, logout } = useAuth()
  const { data: brands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands',
    ttlMs: API_CACHE_TTL.brands,
  })

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login')
    }
  }, [user, isLoading, router])

  // Always clear body scroll lock on navigation (modals / generating UI can leave it stuck).
  useEffect(() => {
    document.body.style.overflow = ''
  }, [pathname])

  if (isLoading && !user) return <PageLoader />
  if (!user) return null

  const activeBrand = brands?.[0]
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
      <Sidebar
        user={user}
        brandName={activeBrand?.name}
        brandSubtitle={brandSubtitle || undefined}
        onLogout={handleLogout}
      />
      <main className="flex-1 min-w-0 h-screen overflow-y-auto overflow-x-hidden">{children}</main>
    </div>
  )
}

export default function DashboardLayout({ children }: { children: React.ReactNode }) {
  return (
    <AuthProvider>
      <DashboardShell>{children}</DashboardShell>
    </AuthProvider>
  )
}
