'use client'

import React, { useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import { useApi } from '@/hooks/useApi'
import { briefsApi } from '@/lib/api'
import { timeAgo } from '@/lib/utils'
import type { Brief, BriefStatus } from '@/types'

import { API_CACHE_TTL } from '@/lib/apiCache'

const STATUS_TABS = ['All', 'DRAFT', 'PENDING', 'RUNNING', 'READY', 'EXPORTED']

const statusBadge = (s: BriefStatus) => {
  const map: Record<string, 'green' | 'mint' | 'amber' | 'red' | 'blue' | 'gray'> = {
    READY: 'green', RUNNING: 'mint', PENDING: 'amber',
    FAILED: 'red', EXPORTED: 'blue', DRAFT: 'gray', PARTIAL: 'amber',
  }
  return map[s] ?? 'gray'
}

export default function BriefsPage() {
  const router = useRouter()
  const [activeStatus, setActiveStatus] = useState('All')

  const { data: briefs, isLoading, refetch } = useApi(
    () => briefsApi.list(activeStatus !== 'All' ? { status: activeStatus } : {}),
    [activeStatus],
    { cacheKey: `briefs/list/${activeStatus}`, ttlMs: API_CACHE_TTL.briefs }
  )

  const runningBriefs = (briefs ?? []).filter((b: Brief) => b.status === 'RUNNING')
  const stuckRunning = runningBriefs.filter((b: Brief) => b.completed_variants === 0)

  const handleResetStuck = async (briefId: string, e: React.MouseEvent) => {
    e.stopPropagation()
    try {
      await briefsApi.update(briefId, { status: 'DRAFT' })
      toast.success('Brief reset — open it and click Generate video when ready')
      refetch()
    } catch {
      toast.error('Could not reset brief')
    }
  }

  const handleResetAllStuck = async () => {
    if (!stuckRunning.length) return
    if (!confirm(`Reset ${stuckRunning.length} stuck brief(s) to DRAFT?`)) return
    try {
      await Promise.all(stuckRunning.map((b: Brief) => briefsApi.update(b.id, { status: 'DRAFT' })))
      toast.success('Stuck briefs reset')
      refetch()
    } catch {
      toast.error('Could not reset all briefs')
    }
  }

  const handleDelete = async (id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    if (!confirm('Delete this brief?')) return
    try {
      await briefsApi.delete(id)
      toast.success('Brief deleted')
      refetch()
    } catch {
      toast.error('Failed to delete')
    }
  }

  return (
    <div>
      <Topbar
        title="Briefs"
        subtitle={`${briefs?.length ?? 0} brief${briefs?.length !== 1 ? 's' : ''}`}
        actions={
          <Button variant="primary" size="sm" onClick={() => router.push('/briefs/new')}>
            + New Brief
          </Button>
        }
      />

      {/* Status tabs */}
      <div className="px-5 pt-4 flex gap-1.5 border-b border-border bg-white">
        {STATUS_TABS.map((s) => (
          <button
            key={s}
            onClick={() => setActiveStatus(s)}
            className={`px-3 py-2 text-xs font-semibold rounded-t-lg border-b-2 transition-colors ${
              activeStatus === s
                ? 'border-mint text-mint bg-[rgba(0,194,168,0.06)]'
                : 'border-transparent text-mid hover:text-navy'
            }`}
          >
            {s}
          </button>
        ))}
      </div>

      {activeStatus === 'RUNNING' && stuckRunning.length > 0 && (
        <div className="mx-5 mt-4 rounded-lg border border-amber-300 bg-amber-50 px-4 py-3 text-xs text-amber-950 flex flex-wrap items-center justify-between gap-2">
          <p>
            These show <strong>RUNNING</strong> from an old session — video does <strong>not</strong>{' '}
            auto-start when you open the app. Reset them, then open a brief and click{' '}
            <strong>Generate video</strong>.
          </p>
          <Button type="button" size="sm" variant="outline" onClick={() => void handleResetAllStuck()}>
            Reset all stuck ({stuckRunning.length})
          </Button>
        </div>
      )}

      <div className="p-5">
        {isLoading ? (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[...Array(4)].map((_, i) => (
              <div key={i} className="bg-white border border-border rounded-xl p-4 space-y-2">
                <div className="skeleton h-4 w-3/4 rounded" />
                <div className="skeleton h-3 w-1/2 rounded" />
                <div className="skeleton h-3 w-1/3 rounded" />
              </div>
            ))}
          </div>
        ) : briefs?.length === 0 ? (
          <div className="py-20 text-center">
            <div className="text-4xl mb-3">📝</div>
            <p className="text-sm font-semibold text-mid">No briefs yet</p>
            <p className="text-xs text-lt mt-1 mb-4">Create a brief to start generating AI-powered variants.</p>
            <Button variant="primary" onClick={() => router.push('/briefs/new')}>Create your first brief</Button>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {(briefs ?? []).map((b: Brief) => (
              <div
                key={b.id}
                className="bg-white border border-border rounded-xl p-4 cursor-pointer hover:shadow-md transition-shadow"
                onClick={() => router.push(`/briefs/${b.id}`)}
              >
                <div className="flex items-start justify-between mb-2">
                  <h3 className="text-sm font-bold text-navy pr-2">{b.title}</h3>
                  <Badge variant={statusBadge(b.status as BriefStatus)}>{b.status}</Badge>
                </div>
                <div className="flex flex-wrap gap-1.5 mb-3">
                  {b.formats?.map((f) => (
                    <span key={f} className="text-[10px] font-semibold bg-light text-mid px-2 py-0.5 rounded capitalize">{f}</span>
                  ))}
                </div>
                <div className="flex items-center justify-between">
                  <span className="text-xs text-lt">
                    {b.completed_variants}/{b.variant_count} variants · {timeAgo(b.created_at)}
                    {b.status === 'RUNNING' && b.completed_variants === 0 && (
                      <span className="text-amber-700 font-semibold"> · likely stuck</span>
                    )}
                  </span>
                  <div className="flex gap-1.5" onClick={(e) => e.stopPropagation()}>
                    {b.status === 'RUNNING' && b.completed_variants === 0 && (
                      <Button
                        size="sm"
                        variant="outline"
                        onClick={(e) => void handleResetStuck(b.id, e)}
                      >
                        Reset
                      </Button>
                    )}
                    <Link href={`/briefs/${b.id}`}><Button size="sm" variant="outline">View</Button></Link>
                    <Button size="sm" variant="danger" onClick={(e) => handleDelete(b.id, e)}>Delete</Button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
