import { clsx, type ClassValue } from 'clsx'
import { format, formatDistanceToNow } from 'date-fns'
import type { BriefStatus, ComplianceStatus, VariantStatus } from '@/types'

export function cn(...inputs: ClassValue[]): string {
  return clsx(inputs)
}

export function formatDate(date: string | Date, fmt = 'MMM d, yyyy'): string {
  try {
    return format(new Date(date), fmt)
  } catch {
    return ''
  }
}

export function timeAgo(date: string | Date): string {
  try {
    return formatDistanceToNow(new Date(date), { addSuffix: true })
  } catch {
    return ''
  }
}

export function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(amount)
}

export function formatROAS(roas: number): string {
  return `${roas.toFixed(2)}×`
}

export function formatPercent(value: number, decimals = 1): string {
  return `${(value * 100).toFixed(decimals)}%`
}

export function formatNumber(n: number): string {
  return new Intl.NumberFormat('en-US').format(n)
}

export function truncate(str: string, max: number): string {
  return str.length > max ? str.slice(0, max - 1) + '…' : str
}

export function slugify(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-|-$/g, '')
}

export function getBriefStatusColor(status: BriefStatus): string {
  const map: Record<BriefStatus, string> = {
    DRAFT: 'bg-gray-100 text-gray-600',
    PENDING: 'bg-amber-100 text-amber-700',
    RUNNING: 'bg-teal-100 text-teal-700',
    READY: 'bg-green-100 text-green-700',
    PARTIAL: 'bg-orange-100 text-orange-700',
    FAILED: 'bg-red-100 text-red-700',
    EXPORTED: 'bg-accent/15 text-[#3d5c22]',
  }
  return map[status] ?? 'bg-gray-100 text-gray-600'
}

export function getVariantStatusColor(status: VariantStatus): string {
  const map: Record<VariantStatus, string> = {
    PENDING: 'bg-gray-100 text-gray-600',
    GENERATING: 'bg-teal-100 text-teal-700',
    READY: 'bg-green-100 text-green-700',
    FAILED: 'bg-red-100 text-red-700',
    APPROVED: 'bg-accent/15 text-[#3d5c22]',
    REJECTED: 'bg-red-100 text-red-600',
    EXPORTED: 'bg-purple-100 text-purple-700',
  }
  return map[status] ?? 'bg-gray-100 text-gray-600'
}

export function getComplianceStatusColor(status: ComplianceStatus): string {
  const map: Record<ComplianceStatus, string> = {
    PENDING: 'bg-gray-100 text-gray-600',
    PASSED: 'bg-green-100 text-green-700',
    FAILED: 'bg-red-100 text-red-700',
    WARNING: 'bg-amber-100 text-amber-700',
  }
  return map[status] ?? 'bg-gray-100 text-gray-600'
}

export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1_048_576) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / 1_048_576).toFixed(1)} MB`
}

export function getFormatColor(format: string): string {
  const map: Record<string, string> = {
    static: 'from-navy2 to-navy',
    reel: 'from-teal to-navy',
    video: 'from-mint to-teal',
    carousel: 'from-purple-600 to-navy2',
  }
  return map[format] ?? 'from-navy2 to-navy'
}

export function assetUrl(url?: string | null, cacheKey?: string | number): string | null {
  if (!url) return null
  const version = cacheKey != null ? `?v=${encodeURIComponent(String(cacheKey))}` : ''
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return version ? `${url}${url.includes('?') ? '&' : '?'}v=${encodeURIComponent(String(cacheKey))}` : url
  }
  const path = url.startsWith('/') ? url : `/${url}`
  if (typeof window !== 'undefined') {
    return `${path}${version}`
  }
  const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
  const origin = api.replace(/\/api\/v1$/, '')
  return `${origin}${path}${version}`
}
