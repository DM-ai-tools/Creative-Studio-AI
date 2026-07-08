'use client'

import React, { useState } from 'react'
import Topbar from '@/components/layout/Topbar'
import Card from '@/components/ui/Card'
import MetricCard from '@/components/dashboard/MetricCard'
import PerformanceChart from '@/components/charts/PerformanceChart'
import { useApi } from '@/hooks/useApi'
import { performanceApi } from '@/lib/api'
import { formatROAS, formatCurrency, formatNumber, timeAgo } from '@/lib/utils'
import type { TopPerformer } from '@/types'

const DAY_OPTIONS = [
  { label: '7d', value: 7 },
  { label: '30d', value: 30 },
  { label: '90d', value: 90 },
]

export default function PerformancePage() {
  const [days, setDays] = useState(30)
  const [chartMetric, setChartMetric] = useState<'roas' | 'ctr' | 'impressions' | 'spend'>('roas')

  const { data: stats, isLoading: statsLoading } = useApi(() => performanceApi.getDashboardStats(), [])
  const { data: topPerformers, isLoading: perfLoading } = useApi(() => performanceApi.getTopPerformers(10), [])
  const { data: fatigueAlerts } = useApi(() => performanceApi.getFatigueAlerts(), [])

  return (
    <div>
      <Topbar
        title="Performance Analytics"
        subtitle="ROAS, CTR, and fatigue analysis across all variants"
        actions={
          <div className="flex gap-1 bg-light rounded-lg p-1">
            {DAY_OPTIONS.map((opt) => (
              <button
                key={opt.value}
                onClick={() => setDays(opt.value)}
                className={`px-3 py-1 text-xs font-bold rounded-md transition-colors ${
                  days === opt.value ? 'bg-white text-navy shadow-sm' : 'text-lt hover:text-navy'
                }`}
              >
                {opt.label}
              </button>
            ))}
          </div>
        }
      />

      <div className="p-5 space-y-5">
        {/* KPI row */}
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
          <MetricCard label="Active Variants" value={stats?.active_variants ?? '—'} isLoading={statsLoading} />
          <MetricCard label="Avg ROAS (7d)" value={stats ? formatROAS(stats.avg_roas_7d) : '—'} isLoading={statsLoading} />
          <MetricCard
            label="Brand Safety Pass"
            value={
              stats?.brand_safety_pass_rate == null
                ? '—'
                : `${(stats.brand_safety_pass_rate * 100).toFixed(1)}%`
            }
            change={stats?.brand_safety_pass_rate == null ? 'No checks yet' : undefined}
            isLoading={statsLoading}
          />
          <MetricCard label="Fatigued" value={stats?.fatigued_count ?? '—'} isLoading={statsLoading} valueColor={stats?.fatigued_count ? 'text-red-500' : undefined} />
        </div>

        {/* Chart */}
        <Card
          title="ROAS Trend"
          action={
            <div className="flex gap-1">
              {(['roas', 'ctr', 'impressions', 'spend'] as const).map((m) => (
                <button
                  key={m}
                  onClick={() => setChartMetric(m)}
                  className={`px-2 py-0.5 text-[10px] font-bold rounded uppercase ${
                    chartMetric === m ? 'bg-mint text-navy' : 'text-lt hover:text-navy'
                  }`}
                >
                  {m}
                </button>
              ))}
            </div>
          }
        >
          <PerformanceChart data={[]} metric={chartMetric} />
          <p className="text-center text-xs text-lt mt-2">Live Meta performance sync uses the configured server access token.</p>
        </Card>

        {/* Top performers table */}
        <Card title="Top Variants by ROAS" padding={false}>
          <table className="w-full text-xs">
            <thead>
              <tr className="bg-light">
                {['Variant', 'Format', 'ROAS (7d)', 'Status'].map((h) => (
                  <th key={h} className="text-left px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border">{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {perfLoading
                ? [...Array(5)].map((_, i) => (
                    <tr key={i}><td colSpan={4} className="px-4 py-3"><div className="skeleton h-4 rounded" /></td></tr>
                  ))
                : (topPerformers ?? []).map((p: TopPerformer) => (
                    <tr key={p.variant_id} className="border-b border-border hover:bg-light/50">
                      <td className="px-4 py-2.5 font-semibold text-navy max-w-[240px] truncate">{p.hook}</td>
                      <td className="px-4 py-2.5 text-mid capitalize">{p.format}</td>
                      <td className="px-4 py-2.5 font-bold text-green-600">{formatROAS(p.roas_7d)}</td>
                      <td className="px-4 py-2.5 text-mid capitalize">{p.status}</td>
                    </tr>
                  ))}
              {!perfLoading && !topPerformers?.length && (
                <tr><td colSpan={4} className="px-4 py-8 text-center text-lt">No performance data yet.</td></tr>
              )}
            </tbody>
          </table>
        </Card>

        {fatigueAlerts && fatigueAlerts.length > 0 && (
          <Card title={`⚠ Creative Fatigue (${fatigueAlerts.length})`} padding={false}>
            <p className="px-4 py-3 text-xs text-mid">
              {fatigueAlerts.length} variant{fatigueAlerts.length !== 1 ? 's' : ''} showing signs of audience fatigue (ROAS &lt; 75% of personal best with frequency &gt; 4.0).
              Visit <a href="/dashboard" className="text-mint font-semibold">Dashboard</a> to take action.
            </p>
          </Card>
        )}
      </div>
    </div>
  )
}
