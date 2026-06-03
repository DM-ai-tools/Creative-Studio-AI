'use client'

import React, { useCallback, useState } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import MetricCard from '@/components/dashboard/MetricCard'
import FatigueAlerts from '@/components/dashboard/FatigueAlerts'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { useApi } from '@/hooks/useApi'
import { briefsApi, performanceApi, variantsApi } from '@/lib/api'
import { getBriefStatusColor, formatROAS, timeAgo } from '@/lib/utils'
import type { Brief, BriefStatus, FatigueAlert, TopPerformer } from '@/types'

const statusBadgeVariant = (s: BriefStatus) => {
  const map: Record<BriefStatus, 'green' | 'mint' | 'amber' | 'red' | 'blue' | 'gray'> = {
    READY: 'green', RUNNING: 'mint', GENERATING: 'mint',
    PENDING: 'amber', FAILED: 'red', EXPORTED: 'blue',
    DRAFT: 'gray', PARTIAL: 'amber',
  } as Record<BriefStatus, 'green' | 'mint' | 'amber' | 'red' | 'blue' | 'gray'>
  return map[s] ?? 'gray'
}

export default function DashboardPage() {
  const router = useRouter()
  const { data: stats, isLoading: statsLoading } = useApi(() => performanceApi.getDashboardStats(), [])
  const { data: briefs, isLoading: briefsLoading } = useApi(() => briefsApi.list({ limit: 5 }), [])
  const { data: topPerformers, isLoading: perfLoading } = useApi(() => performanceApi.getTopPerformers(), [])
  const { data: fatigueAlerts, isLoading: fatigueLoading, refetch: refetchAlerts } = useApi(
    () => variantsApi.getFatigueAlerts(), []
  )

  const handleReplace = useCallback(async (variantId: string) => {
    try {
      await variantsApi.regenerate(variantId)
      toast.success('Variant queued for regeneration')
      refetchAlerts()
    } catch {
      toast.error('Failed to regenerate variant')
    }
  }, [refetchAlerts])

  const handlePause = useCallback(async (variantId: string) => {
    try {
      await variantsApi.update(variantId, { status: 'REJECTED' })
      toast.success('Variant paused')
      refetchAlerts()
    } catch {
      toast.error('Failed to pause variant')
    }
  }, [refetchAlerts])

  return (
    <div>
      <Topbar
        title="Dashboard"
        actions={
          <>
            <Button variant="outline" size="sm">Export Report</Button>
            <Button variant="primary" size="sm" onClick={() => router.push('/briefs/new')}>
              + New Brief
            </Button>
          </>
        }
      />

      <div className="p-6 md:p-8 space-y-6 max-w-[1600px]">
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-4">
          <MetricCard
            label="Active Variants"
            value={stats?.active_variants ?? '—'}
            change="this week"
            changeDirection="up"
            isLoading={statsLoading}
          />
          <MetricCard
            label="Avg ROAS (7d)"
            value={stats ? formatROAS(stats.avg_roas_7d) : '—'}
            change="vs prior period"
            changeDirection="up"
            isLoading={statsLoading}
          />
          <MetricCard
            label="Brand-Safety Pass"
            value={stats ? `${(stats.brand_safety_pass_rate * 100).toFixed(1)}%` : '—'}
            change="pass rate"
            changeDirection="up"
            isLoading={statsLoading}
          />
          <MetricCard
            label="Fatigued (Action Needed)"
            value={stats?.fatigued_count ?? '—'}
            change="Replace or pause"
            changeDirection={stats?.fatigued_count ? 'down' : 'neutral'}
            isLoading={statsLoading}
            valueColor={stats?.fatigued_count ? 'text-red-500' : 'text-charcoal'}
          />
        </div>

        {/* Two-col: Briefs + Top Performers */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
          {/* Recent Briefs */}
          <div className="lg:col-span-2">
            <Card
              title="Recent Briefs"
              action={<Link href="/briefs" className="text-xs text-accent font-semibold hover:underline">View all →</Link>}
              padding={false}
            >
              {briefsLoading ? (
                <div className="p-4 space-y-2">
                  {[...Array(4)].map((_, i) => <div key={i} className="skeleton h-8 rounded" />)}
                </div>
              ) : (
                <table className="data-table">
                  <thead>
                    <tr>
                      {['Brief', 'Format', 'Variants', 'Status', 'Created'].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(briefs ?? []).map((b: Brief) => (
                      <tr
                        key={b.id}
                        className="cursor-pointer"
                        onClick={() => router.push(`/briefs/${b.id}`)}
                      >
                        <td className="max-w-[200px] truncate">{b.title}</td>
                        <td>{b.formats?.join(', ') || '—'}</td>
                        <td>{b.completed_variants}/{b.variant_count}</td>
                        <td><Badge variant={statusBadgeVariant(b.status as BriefStatus)}>{b.status}</Badge></td>
                        <td className="text-subtle whitespace-nowrap">{timeAgo(b.created_at)}</td>
                      </tr>
                    ))}
                    {!briefsLoading && !briefs?.length && (
                      <tr>
                        <td colSpan={5} className="py-10 text-center text-muted">
                          No briefs yet.{' '}
                          <Link href="/briefs" className="text-accent font-semibold hover:underline">
                            Create one →
                          </Link>
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              )}
            </Card>
          </div>

          {/* Top Performers */}
          <Card title="Top Performers (7d)" padding={false}>
            <div className="divide-y divide-border/60">
              {perfLoading
                ? [...Array(4)].map((_, i) => <div key={i} className="p-4 skeleton h-12 mx-4 my-2 rounded-xl" />)
                : (topPerformers ?? []).map((p: TopPerformer) => (
                    <div
                      key={p.variant_id}
                      className="px-5 py-3.5 flex items-center justify-between hover:bg-accent/[0.03] transition-colors"
                    >
                      <div className="min-w-0">
                        <div className="text-sm font-semibold text-charcoal truncate max-w-[180px]">
                          {p.hook}
                        </div>
                        <div className="text-xs text-muted capitalize mt-0.5">{p.format}</div>
                      </div>
                      <span className="text-sm font-bold text-success tabular-nums">
                        {formatROAS(p.roas_7d)}
                      </span>
                    </div>
                  ))}
              {!perfLoading && !topPerformers?.length && (
                <p className="p-6 text-sm text-muted text-center">No performance data yet.</p>
              )}
            </div>
          </Card>
        </div>

        {/* Fatigue Alerts */}
        {(fatigueAlerts?.length ?? 0) > 0 && (
          <Card
            title={`⚠ Fatigue Alerts (${fatigueAlerts?.length})`}
            padding={false}
          >
            <FatigueAlerts
              alerts={(fatigueAlerts ?? []) as FatigueAlert[]}
              onReplace={handleReplace}
              onPause={handlePause}
            />
          </Card>
        )}
      </div>
    </div>
  )
}
