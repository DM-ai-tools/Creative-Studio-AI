'use client'

import CountUp from '@/components/ui/CountUp'
import IconBadge from '@/components/ui/IconBadge'
import { IconImage, IconPalette, IconTrending, IconShield, IconWand } from '@/components/ui/icons'
import { getVariantPreviewUrls } from '@/lib/variantMedia'
import { Flame } from 'lucide-react'
import GeneratingDots from '@/components/variant/GeneratingDots'
import EmptyState from '@/components/ui/EmptyState'
import { FolderKanban, TrendingUp } from 'lucide-react'
import React, { useCallback } from 'react'
import Link from 'next/link'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Button from '@/components/ui/Button'
import Badge from '@/components/ui/Badge'
import { SkeletonLine } from '@/components/ui/Loading'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { briefsApi, performanceApi, variantsApi } from '@/lib/api'
import { UI, briefStatusLabel } from '@/lib/uiLabels'
import { getBriefStatusColor, formatROAS, timeAgo } from '@/lib/utils'
import type { Brief, BriefStatus, FatigueAlert, TopPerformer, Variant } from '@/types'

/* ── helpers ── */
function statusConfig(s: BriefStatus): { variant: 'green' | 'mint' | 'amber' | 'red' | 'blue' | 'gray'; dot: boolean } {
  const map: Record<string, 'green' | 'mint' | 'amber' | 'red' | 'blue' | 'gray'> = {
    READY: 'green', RUNNING: 'mint', GENERATING: 'mint',
    PENDING: 'amber', PARTIAL: 'amber',
    FAILED: 'red', EXPORTED: 'blue', DRAFT: 'gray',
  }
  return { variant: map[s] ?? 'gray', dot: true }
}

/* ── Metric Card ── */
function MetricCard({
  label,
  value,
  sub,
  trend,
  isLoading,
  accent = false,
  icon,
  tone = 'accent',
}: {
  label: string
  value: string | number
  sub?: string
  trend?: { dir: 'up' | 'down' | 'neutral'; label: string }
  isLoading?: boolean
  accent?: boolean
  icon?: React.ReactNode
  tone?: 'accent' | 'dark' | 'soft' | 'sky' | 'violet' | 'amber' | 'rose'
}) {
  return (
    <div className={`group relative bg-surface-elevated rounded-2xl p-5 border overflow-hidden transition-all duration-250 ease-premium hover:shadow-card-hover hover:-translate-y-px ${accent ? 'border-accent/25 shadow-[0_0_0_1px_rgba(163,209,107,0.2),0_4px_16px_rgba(163,209,107,0.08)]' : 'border-border shadow-card'}`}>
      {accent && (
        <div className="absolute left-0 top-0 bottom-0 w-[3px]" style={{ background: 'linear-gradient(180deg,#a3d16b,#8bb85a)', boxShadow: '0 0 8px rgba(163,209,107,0.45)' }} />
      )}
      {icon && <IconBadge icon={icon} tone={tone} className="absolute right-4 top-4" />}
      {/* Label */}
      <p className="text-[10px] font-bold text-muted uppercase tracking-[0.1em] mb-3">{label}</p>
      {/* Value */}
      {isLoading ? (
        <div className="space-y-2">
          <SkeletonLine className="h-7 w-20" />
          <SkeletonLine className="h-3 w-28" />
        </div>
      ) : (
        <>
          <div className="text-[2rem] font-black text-charcoal leading-none tracking-tight count-up" style={{ letterSpacing: '-0.03em' }}>
            <CountUp value={value} />
          </div>
          {sub && <p className="text-[11px] text-muted mt-1.5 font-medium">{sub}</p>}
          {trend && (
            <div className={`inline-flex items-center gap-1 mt-2 text-[10px] font-semibold px-1.5 py-0.5 rounded-md ${trend.dir === 'up' ? 'text-emerald-700 bg-emerald-50' : trend.dir === 'down' ? 'text-red-600 bg-red-50' : 'text-muted bg-surface'}`}>
              {trend.dir === 'up' && '↑'}
              {trend.dir === 'down' && '↓'}
              {trend.label}
            </div>
          )}
        </>
      )}
    </div>
  )
}

/* ── Page ── */
export default function DashboardPage() {
  const router = useRouter()

  const { data: stats, isLoading: statsLoading } = useApi(
    () => performanceApi.getDashboardStats(), [],
    { cacheKey: 'stats/dashboard', ttlMs: API_CACHE_TTL.stats }
  )
  const { data: briefs, isLoading: briefsLoading } = useApi(
    () => briefsApi.list({ limit: 5 }), [],
    { cacheKey: 'briefs/recent', ttlMs: API_CACHE_TTL.briefs }
  )
  const { data: recentCreatives, isLoading: creativesLoading } = useApi(
    () => variantsApi.list({ limit: 8 }), [],
    { cacheKey: 'variants/recent', ttlMs: API_CACHE_TTL.briefs }
  )
  const { data: topPerformers, isLoading: perfLoading } = useApi(
    () => performanceApi.getTopPerformers(), [],
    { cacheKey: 'performance/top', ttlMs: API_CACHE_TTL.stats }
  )
  const { data: fatigueAlerts, refetch: refetchAlerts } = useApi(
    () => variantsApi.getFatigueAlerts(), [],
    { cacheKey: 'fatigue-alerts', ttlMs: API_CACHE_TTL.stats }
  )

  const handleReplace = useCallback(async (id: string) => {
    try { await variantsApi.regenerate(id); toast.success('Queued for regeneration'); refetchAlerts() }
    catch { toast.error('Failed to regenerate') }
  }, [refetchAlerts])

  const handlePause = useCallback(async (id: string) => {
    try { await variantsApi.update(id, { status: 'REJECTED' }); toast.success('Variant paused'); refetchAlerts() }
    catch { toast.error('Failed to pause') }
  }, [refetchAlerts])

  const hasStats = !statsLoading && stats
  const passRate = hasStats && stats.brand_safety_pass_rate != null
    ? `${(stats.brand_safety_pass_rate * 100).toFixed(1)}%` : '—'

  return (
    <div className="min-h-full">
      <Topbar
        title="Dashboard"
        subtitle="Your creative performance at a glance"
        actions={
          <>
            <Button variant="outline" size="sm">Export Report</Button>
            <Button
              variant="primary"
              size="sm"
              leftIcon={<svg className="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" /></svg>}
              onClick={() => router.push('/briefs/new')}
            >
              {UI.newProject}
            </Button>
          </>
        }
      />

      <div className="relative isolate p-6 max-w-[1600px] space-y-6">
        {/* a quiet field of dots behind the top of the page */}
        <div
          className="pointer-events-none absolute inset-x-0 top-0 -z-10 h-72 opacity-60"
          style={{ maskImage: 'linear-gradient(to bottom, black, transparent)', WebkitMaskImage: 'linear-gradient(to bottom, black, transparent)' }}
        >
          <GeneratingDots ambient />
        </div>

        {/* ── Metric Cards ── */}
        <div className="grid grid-cols-2 xl:grid-cols-4 gap-4">
          <MetricCard
            label="Active Variants"
            icon={<IconImage />}
            tone="accent"
            value={hasStats ? stats.active_variants ?? '—' : '—'}
            sub="across all campaigns"
            accent
            isLoading={statsLoading}
          />
          <MetricCard
            label="Avg ROAS (7d)"
            icon={<IconTrending />}
            tone="sky"
            value={hasStats ? formatROAS(stats.avg_roas_7d) : '—'}
            sub="return on ad spend"
            trend={hasStats ? { dir: 'up', label: 'vs prior period' } : undefined}
            isLoading={statsLoading}
          />
          <MetricCard
            label={UI.brandContentChecks}
            icon={<IconShield />}
            tone="violet"
            value={passRate}
            sub={hasStats && stats.brand_safety_pass_rate != null ? 'compliance pass rate' : 'No checks yet'}
            isLoading={statsLoading}
          />
          <MetricCard
            label="Fatigue Alerts"
            icon={<Flame />}
            tone="amber"
            value={hasStats ? stats.fatigued_count ?? 0 : '—'}
            sub="variants need attention"
            trend={hasStats && (stats.fatigued_count ?? 0) > 0 ? { dir: 'down', label: 'Replace or pause' } : { dir: 'neutral', label: 'All good' }}
            isLoading={statsLoading}
          />
        </div>

        {/* ── Main Grid ── */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">

          {/* Recent Briefs */}
          <div className="lg:col-span-2">
            <div className="bg-surface-elevated rounded-2xl border border-border shadow-card overflow-hidden">
              <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 bg-gradient-to-r from-surface/50 to-transparent">
                <div>
                  <h3 className="text-sm font-bold text-charcoal tracking-tight">Recent projects</h3>
                  <p className="text-[11px] text-muted mt-0.5">Latest creative campaigns</p>
                </div>
                <Link href="/briefs" className="text-[11px] font-bold text-accent hover:text-accent-dark transition-colors flex items-center gap-1">
                  View all
                  <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}><path strokeLinecap="round" strokeLinejoin="round" d="M8.25 4.5l7.5 7.5-7.5 7.5" /></svg>
                </Link>
              </div>

              {briefsLoading ? (
                <div className="p-4 space-y-3">
                  {[...Array(4)].map((_, i) => (
                    <div key={i} className="flex items-center gap-4 py-1">
                      <SkeletonLine className="h-4 flex-1" />
                      <SkeletonLine className="h-4 w-16" />
                      <SkeletonLine className="h-4 w-12" />
                    </div>
                  ))}
                </div>
              ) : !briefs?.length ? (
                <EmptyState
                  icon={FolderKanban}
                  title="No projects yet"
                  description="Create your first project to start generating AI-powered creative content."
                  action={<Button size="sm" onClick={() => router.push('/briefs/new')}>{UI.newProject}</Button>}
                />
              ) : (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="bg-surface/60">
                      {['Project', 'Format', 'Creatives', 'Status', 'Created'].map(h => (
                        <th key={h} className="text-left px-4 py-2.5 text-[10px] font-bold text-muted/80 uppercase tracking-[0.08em] border-b border-border/50 first:pl-5 last:pr-5">
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(briefs ?? []).map((b: Brief, i: number) => {
                      const { variant, dot } = statusConfig(b.status as BriefStatus)
                      return (
                        <tr
                          key={b.id}
                          className="border-b border-border/40 cursor-pointer transition-colors duration-150 hover:bg-accent/[0.025] group"
                          style={{ animationDelay: `${i * 0.04}s` }}
                          onClick={() => router.push(`/briefs/${b.id}`)}
                        >
                          <td className="pl-5 pr-4 py-3.5 font-semibold text-charcoal max-w-[220px] truncate group-hover:text-accent transition-colors duration-150">
                            {b.title}
                          </td>
                          <td className="px-4 py-3.5 text-muted text-[12px]">
                            {b.formats?.join(', ') || '—'}
                          </td>
                          <td className="px-4 py-3.5 text-muted text-[12px] font-medium">
                            <span className="text-charcoal font-bold">{b.completed_variants}</span>
                            <span className="text-muted/60">/{b.variant_count}</span>
                          </td>
                          <td className="px-4 py-3.5">
                            <Badge variant={variant} dot={dot}>
                              {briefStatusLabel(b.status, b.completed_variants, b.variant_count)}
                            </Badge>
                          </td>
                          <td className="pr-5 py-3.5 text-[11px] text-muted whitespace-nowrap">
                            {timeAgo(b.created_at)}
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              )}
            </div>
          </div>

          {/* Top Performers */}
          <div className="bg-surface-elevated rounded-2xl border border-border shadow-card overflow-hidden">
            <div className="flex items-center justify-between px-5 py-4 border-b border-border/60 bg-gradient-to-r from-surface/50 to-transparent">
              <div>
                <h3 className="text-sm font-bold text-charcoal tracking-tight">Top Performers</h3>
                <p className="text-[11px] text-muted mt-0.5">Last 7 days by ROAS</p>
              </div>
              <Link href="/performance" className="text-[11px] font-bold text-accent hover:text-accent-dark transition-colors">Analytics →</Link>
            </div>

            {perfLoading ? (
              <div className="p-4 space-y-3">
                {[...Array(4)].map((_, i) => (
                  <div key={i} className="flex items-center justify-between gap-3 py-1">
                    <div className="flex-1 space-y-1.5">
                      <SkeletonLine className="h-3.5 w-3/4" />
                      <SkeletonLine className="h-2.5 w-1/2" />
                    </div>
                    <SkeletonLine className="h-4 w-12" />
                  </div>
                ))}
              </div>
            ) : !topPerformers?.length ? (
              <EmptyState
                icon={TrendingUp}
                title="No data yet"
                description="Performance data appears after your ads start running."
              />
            ) : (
              <div className="divide-y divide-border/40">
                {(topPerformers ?? []).map((p: TopPerformer, i: number) => (
                  <div
                    key={p.variant_id}
                    className="flex items-center justify-between gap-3 px-5 py-3.5 hover:bg-accent/[0.025] transition-colors duration-150"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span
                        className="w-5 h-5 rounded-full flex items-center justify-center text-[9px] font-black shrink-0"
                        style={{
                          background: i === 0 ? 'linear-gradient(135deg,#a3d16b,#8bb85a)' : 'rgba(191,192,197,0.2)',
                          color: i === 0 ? 'white' : '#6b6b73',
                        }}
                      >
                        {i + 1}
                      </span>
                      <div className="min-w-0">
                        <div className="text-[12px] font-semibold text-charcoal truncate">{p.hook}</div>
                        <div className="text-[10px] text-muted capitalize mt-0.5">{p.format}</div>
                      </div>
                    </div>
                    <div className="text-sm font-black tabular-nums shrink-0" style={{ color: '#4a7a20' }}>
                      {formatROAS(p.roas_7d)}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* ── Fatigue Alerts ── */}
        {(fatigueAlerts?.length ?? 0) > 0 && (
          <div className="bg-surface-elevated rounded-2xl border border-amber-200/60 shadow-card overflow-hidden">
            <div className="flex items-center gap-3 px-5 py-4 border-b border-amber-200/50 bg-amber-50/40">
              <div className="w-7 h-7 rounded-xl bg-amber-100 flex items-center justify-center shrink-0">
                <svg className="w-4 h-4 text-amber-600" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                </svg>
              </div>
              <div>
                <h3 className="text-sm font-bold text-amber-800">Fatigue Alerts</h3>
                <p className="text-[11px] text-amber-600">{fatigueAlerts?.length} variant{(fatigueAlerts?.length ?? 0) > 1 ? 's' : ''} need attention</p>
              </div>
            </div>
            <div className="divide-y divide-border/40">
              {(fatigueAlerts ?? []).map((alert: FatigueAlert) => (
                <div key={alert.variant_id} className="flex items-center justify-between gap-4 px-5 py-3.5">
                  <div className="min-w-0 flex-1">
                    <p className="text-[12px] font-semibold text-charcoal truncate">{alert.hook}</p>
                    <p className="text-[10px] text-muted mt-0.5 capitalize">
                      {alert.format} · {alert.drop_pct}% ROAS drop · {alert.frequency_7d}× freq.
                    </p>
                  </div>
                  <div className="flex items-center gap-2 shrink-0">
                    <Button size="xs" variant="outline" onClick={() => handlePause(alert.variant_id)}>Pause</Button>
                    <Button size="xs" onClick={() => handleReplace(alert.variant_id)}>Replace</Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* ── Latest creatives: a gallery of the newest pictures ── */}
        <div className="bg-surface-elevated rounded-2xl border border-border shadow-card overflow-hidden">
          <div className="flex items-center justify-between px-5 py-4 border-b border-border/60">
            <div>
              <h3 className="text-sm font-bold text-charcoal">Latest creatives</h3>
              <p className="text-[11px] text-muted mt-0.5">Your newest images and videos</p>
            </div>
            <Link href="/variants" className="text-[12px] font-semibold text-[#6f9b3f] hover:underline">
              Open library →
            </Link>
          </div>
          {creativesLoading ? (
            <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3 p-5">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="aspect-square rounded-xl skeleton" />
              ))}
            </div>
          ) : (recentCreatives ?? []).length === 0 ? (
            <EmptyState
              compact
              title="No creatives yet"
              description="Generate a project and your newest pictures show up here."
            />
          ) : (
            <div className="grid grid-cols-2 sm:grid-cols-4 xl:grid-cols-8 gap-3 p-5">
              {(recentCreatives ?? []).map((v: Variant) => {
                const { imageUrl, videoUrl } = getVariantPreviewUrls(v)
                return (
                  <Link
                    key={v.id}
                    href={v.brief_id ? `/briefs/${v.brief_id}` : '/variants'}
                    className="group relative aspect-square overflow-hidden rounded-xl border border-border bg-surface shadow-card transition-all duration-300 ease-premium hover:-translate-y-1 hover:shadow-card-hover"
                    title={v.headline || v.hook}
                  >
                    {imageUrl ? (
                      <img src={imageUrl} alt={v.headline || v.hook} loading="lazy" className="h-full w-full object-cover transition-transform duration-500 group-hover:scale-105" />
                    ) : videoUrl ? (
                      <video src={videoUrl} muted playsInline preload="metadata" className="h-full w-full object-cover" />
                    ) : (
                      <div className="flex h-full w-full items-center justify-center text-lt">
                        <IconImage className="h-6 w-6" />
                      </div>
                    )}
                    <span className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/60 to-transparent p-2 pt-6 text-[10px] font-semibold capitalize text-white opacity-0 transition-opacity group-hover:opacity-100">
                      {v.format}
                    </span>
                  </Link>
                )
              })}
            </div>
          )}
        </div>

        {/* ── Quick actions ── */}
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
          {[
            { title: 'Set up Brand Kit', desc: 'Upload your logo, colours and voice guidelines.', href: '/brand-kit', icon: <IconPalette />, tone: 'violet' as const },
            { title: 'Create a new project', desc: 'Generate AI-powered image and video ad creatives.', href: '/briefs/new', icon: <IconWand />, tone: 'accent' as const },
            { title: 'View performance', desc: 'Watch ROAS, CTR and fatigue across all variants.', href: '/performance', icon: <IconTrending />, tone: 'sky' as const },
          ].map(({ title, desc, href, icon, tone }) => (
            <Link
              key={href}
              href={href}
              className="group flex items-start gap-4 bg-surface-elevated rounded-2xl border border-border p-5 shadow-card hover:shadow-card-hover hover:border-accent/30 hover:-translate-y-px transition-all duration-250 ease-premium"
            >
              <IconBadge icon={icon} tone={tone} size="lg" />
              <span>
                <span className="block text-sm font-bold text-charcoal mb-1 group-hover:text-[#5b8a2d] transition-colors">{title}</span>
                <span className="block text-[12px] text-muted leading-relaxed">{desc}</span>
              </span>
            </Link>
          ))}
        </div>
      </div>
    </div>
  )
}
