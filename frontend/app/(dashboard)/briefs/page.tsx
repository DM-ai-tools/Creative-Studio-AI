'use client'

import React, { useMemo, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import { SkeletonLine } from '@/components/ui/Loading'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { briefsApi } from '@/lib/api'
import { cn, timeAgo } from '@/lib/utils'
import type { Brief, BriefStatus } from '@/types'

const STATUS_TABS = ['All', 'DRAFT', 'RUNNING', 'READY', 'PARTIAL', 'EXPORTED']

type BadgeVariant = 'green' | 'mint' | 'amber' | 'red' | 'blue' | 'gray'

const statusMeta: Record<string, { badge: BadgeVariant; dot: boolean; label: string }> = {
  READY:      { badge: 'green',  dot: true,  label: 'Ready' },
  RUNNING:    { badge: 'mint',   dot: true,  label: 'Running' },
  GENERATING: { badge: 'mint',   dot: true,  label: 'Running' },
  PARTIAL:    { badge: 'amber',  dot: true,  label: 'Partial' },
  PENDING:    { badge: 'amber',  dot: false, label: 'Pending' },
  FAILED:     { badge: 'red',    dot: true,  label: 'Failed' },
  EXPORTED:   { badge: 'blue',   dot: false, label: 'Exported' },
  DRAFT:      { badge: 'gray',   dot: false, label: 'Draft' },
}

const formatIcons: Record<string, string> = {
  static: '🖼',
  video: '🎬',
  reel: '📱',
  carousel: '🎠',
}

function BriefCard({ brief, onReset, onDelete }: {
  brief: Brief
  onReset?: (id: string, e: React.MouseEvent) => void
  onDelete: (id: string, e: React.MouseEvent) => void
}) {
  const router = useRouter()
  const meta = statusMeta[brief.status] ?? statusMeta.DRAFT
  const isStuck = brief.status === 'RUNNING' && brief.completed_variants === 0
  const progress = brief.variant_count > 0
    ? Math.round((brief.completed_variants / brief.variant_count) * 100)
    : 0

  return (
    <div
      className={cn(
        'group relative bg-surface-elevated rounded-2xl border overflow-hidden cursor-pointer',
        'transition-all duration-250 ease-premium',
        'hover:shadow-card-hover hover:-translate-y-[2px]',
        isStuck
          ? 'border-amber-200/70 shadow-[0_0_0_1px_rgba(245,158,11,0.15)]'
          : 'border-border shadow-card hover:border-accent/25'
      )}
      onClick={() => router.push(`/briefs/${brief.id}`)}
    >
      {/* Status bar top */}
      {brief.status === 'RUNNING' && (
        <div className="absolute top-0 left-0 right-0 h-[2px] overflow-hidden">
          <div
            className="h-full bg-accent-gradient animate-pulse rounded-full"
            style={{ width: `${Math.max(progress, 20)}%`, transition: 'width 1s ease' }}
          />
        </div>
      )}

      <div className="p-5">
        {/* Header */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <h3 className="text-[13px] font-bold text-charcoal leading-snug group-hover:text-accent transition-colors duration-200 line-clamp-2 flex-1" style={{ letterSpacing: '-0.01em' }}>
            {brief.title}
          </h3>
          <Badge variant={meta.badge} dot={meta.dot} className="shrink-0 mt-0.5">
            {meta.label}
          </Badge>
        </div>

        {/* Formats */}
        {brief.formats?.length > 0 && (
          <div className="flex flex-wrap gap-1.5 mb-3.5">
            {brief.formats.map((f) => (
              <span
                key={f}
                className="inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[10px] font-semibold text-muted bg-surface border border-border/60 capitalize"
              >
                <span>{formatIcons[f] || '📄'}</span>
                {f}
              </span>
            ))}
          </div>
        )}

        {/* Progress row */}
        <div className="flex items-center justify-between gap-2 mb-4">
          <div className="flex items-center gap-1.5 text-[11px] text-muted font-medium">
            <svg className="w-3.5 h-3.5 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M3 4.5h14.25M3 9h9.75M3 13.5h9.75m4.5-4.5v12m0 0l-3.75-3.75M17.25 21L21 17.25" />
            </svg>
            <span>
              <strong className="text-charcoal">{brief.completed_variants}</strong>
              /{brief.variant_count} variants
            </span>
          </div>
          <span className="text-[10px] text-muted">{timeAgo(brief.created_at)}</span>
        </div>

        {/* Progress bar */}
        {brief.variant_count > 0 && (
          <div className="h-1 rounded-full bg-surface mb-4 overflow-hidden">
            <div
              className="h-full rounded-full transition-all duration-500 ease-premium"
              style={{
                width: `${progress}%`,
                background: progress === 100
                  ? 'linear-gradient(90deg,#a3d16b,#8bb85a)'
                  : 'linear-gradient(90deg,#fbbf24,#f59e0b)',
              }}
            />
          </div>
        )}

        {/* Stuck warning */}
        {isStuck && (
          <div className="flex items-center gap-2 px-3 py-2 rounded-xl bg-amber-50 border border-amber-200/70 mb-3.5 text-[10px] text-amber-800 font-medium">
            <svg className="w-3.5 h-3.5 shrink-0 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" />
            </svg>
            Session ended — open brief and click Generate
          </div>
        )}

        {/* Actions */}
        <div
          className="flex items-center gap-2"
          onClick={(e) => e.stopPropagation()}
        >
          {isStuck && onReset && (
            <Button size="xs" variant="outline" onClick={(e) => onReset(brief.id, e)}>
              Reset
            </Button>
          )}
          <Link href={`/briefs/${brief.id}`} className="flex-1">
            <Button size="xs" variant="outline" className="w-full">
              Open brief →
            </Button>
          </Link>
          <Button
            size="xs"
            variant="ghost"
            className="text-red-500 hover:text-red-600 hover:bg-red-50"
            onClick={(e) => onDelete(brief.id, e)}
          >
            <svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0" />
            </svg>
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function BriefsPage() {
  const router = useRouter()
  const [activeStatus, setActiveStatus] = useState('All')
  const [search, setSearch] = useState('')

  const { data: briefs, isLoading, refetch } = useApi(
    () => briefsApi.list({ limit: 200, ...(activeStatus !== 'All' ? { status: activeStatus } : {}) }),
    [activeStatus],
    { cacheKey: `briefs/list/${activeStatus}`, ttlMs: API_CACHE_TTL.briefs }
  )

  const stuckRunning = useMemo(
    () => (briefs ?? []).filter((b: Brief) => b.status === 'RUNNING' && b.completed_variants === 0),
    [briefs]
  )

  const filtered = useMemo(() => {
    if (!search.trim()) return briefs ?? []
    const q = search.toLowerCase()
    return (briefs ?? []).filter((b: Brief) =>
      b.title.toLowerCase().includes(q) ||
      b.objective?.toLowerCase().includes(q) ||
      b.product_name?.toLowerCase().includes(q)
    )
  }, [briefs, search])

  const handleReset = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try { await briefsApi.update(id, { status: 'DRAFT' }); toast.success('Brief reset to Draft'); refetch() }
    catch { toast.error('Could not reset brief') }
  }

  const handleResetAll = async () => {
    if (!stuckRunning.length) return
    if (!confirm(`Reset ${stuckRunning.length} stuck brief(s) to DRAFT?`)) return
    try {
      await Promise.all(stuckRunning.map((b: Brief) => briefsApi.update(b.id, { status: 'DRAFT' })))
      toast.success('Stuck briefs reset')
      refetch()
    } catch { toast.error('Could not reset all') }
  }

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this brief? This cannot be undone.')) return
    try { await briefsApi.delete(id); toast.success('Brief deleted'); refetch() }
    catch { toast.error('Failed to delete') }
  }

  return (
    <div className="min-h-full">
      <Topbar
        title="Briefs"
        subtitle={briefs ? `${briefs.length} brief${briefs.length !== 1 ? 's' : ''}` : undefined}
        actions={
          <Button
            variant="primary"
            size="sm"
            leftIcon={<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>}
            onClick={() => router.push('/briefs/new')}
          >
            New Brief
          </Button>
        }
      />

      {/* Filter bar */}
      <div className="sticky top-[57px] z-10 bg-surface-elevated/90 backdrop-blur-md border-b border-border/60 px-6 py-3 flex items-center gap-3">
        {/* Search */}
        <div className="relative flex-1 max-w-xs">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted pointer-events-none" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search briefs…"
            className="w-full h-8 pl-8 pr-3 border border-border rounded-xl text-[12px] text-charcoal bg-surface placeholder:text-muted/60 transition-all duration-200 focus:border-accent focus:bg-surface-elevated focus:ring-2 focus:ring-accent/15 focus:outline-none"
          />
        </div>

        {/* Status tabs */}
        <div className="flex items-center gap-1 overflow-x-auto scrollbar-none">
          {STATUS_TABS.map((s) => (
            <button
              key={s}
              onClick={() => { setActiveStatus(s); setSearch('') }}
              className={cn(
                'px-3 py-1.5 rounded-lg text-[11px] font-semibold whitespace-nowrap transition-all duration-150',
                activeStatus === s
                  ? 'bg-charcoal text-white shadow-xs'
                  : 'text-muted hover:text-charcoal hover:bg-surface'
              )}
            >
              {s}
            </button>
          ))}
        </div>

        {stuckRunning.length > 0 && (
          <Button size="xs" variant="outline" className="border-amber-300 text-amber-700 shrink-0" onClick={() => void handleResetAll()}>
            Reset {stuckRunning.length} stuck
          </Button>
        )}
      </div>

      <div className="p-6">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div key={i} className="bg-surface-elevated rounded-2xl border border-border p-5 space-y-3 shadow-card">
                <div className="flex justify-between gap-3">
                  <SkeletonLine className="h-4 flex-1" />
                  <SkeletonLine className="h-4 w-14 rounded-full" />
                </div>
                <div className="flex gap-2">
                  <SkeletonLine className="h-6 w-16 rounded-lg" />
                  <SkeletonLine className="h-6 w-16 rounded-lg" />
                </div>
                <SkeletonLine className="h-1.5 w-full rounded-full" />
                <div className="flex gap-2 pt-1">
                  <SkeletonLine className="h-7 flex-1 rounded-xl" />
                  <SkeletonLine className="h-7 w-7 rounded-xl" />
                </div>
              </div>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-20 text-center">
            <div
              className="w-16 h-16 rounded-2xl flex items-center justify-center mb-5"
              style={{ background: 'linear-gradient(135deg,rgba(163,209,107,0.12),rgba(163,209,107,0.06))' }}
            >
              <svg className="w-8 h-8 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m0 12.75h7.5m-7.5 3H12M10.5 2.25H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
              </svg>
            </div>
            <h3 className="text-base font-bold text-charcoal mb-2">
              {search ? 'No results found' : 'No briefs yet'}
            </h3>
            <p className="text-[12px] text-muted max-w-[260px] leading-relaxed mb-6">
              {search
                ? `No briefs match "${search}". Try a different search.`
                : 'Create your first brief to start generating AI-powered creatives.'}
            </p>
            {!search && (
              <Button
                variant="primary"
                leftIcon={<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>}
                onClick={() => router.push('/briefs/new')}
              >
                Create first brief
              </Button>
            )}
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
            {filtered.map((b: Brief) => (
              <BriefCard
                key={b.id}
                brief={b}
                onReset={handleReset}
                onDelete={handleDelete}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
