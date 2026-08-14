'use client'

import React from 'react'
import { useRouter } from 'next/navigation'
import Topbar from '@/components/layout/Topbar'
import Card from '@/components/ui/Card'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import UsageAnalyticsDashboard from '@/components/usage/UsageAnalyticsDashboard'
import { useApi } from '@/hooks/useApi'
import { adminApi } from '@/lib/api'
import { useAuth } from '@/hooks/useAuth'
import { timeAgo } from '@/lib/utils'
import type { AdminUsage } from '@/types'

function money(n: number | null | undefined) {
  if (n == null || Number.isNaN(n)) return '—'
  if (n >= 1) return `$${n.toFixed(2)}`
  return `$${n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`
}

function tokens(n: number | null | undefined) {
  const v = Number(n || 0)
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`
  return String(v)
}

export default function UsagePage() {
  const router = useRouter()
  const { user } = useAuth()
  const { data, isLoading, refetch } = useApi(() => adminApi.getUsage(), [])

  if (user?.role !== 'admin') {
    return (
      <div className="p-10 text-center">
        <p className="text-sm text-mid">Admin access required.</p>
        <Button className="mt-3" onClick={() => router.push('/dashboard')}>Back to Dashboard</Button>
      </div>
    )
  }

  const usage: AdminUsage | null = data
  const totals = usage?.totals

  return (
    <div className="min-h-full bg-[#050506]">
      <Topbar
        title="Usage"
        subtitle="API spend, request volume, and model breakdown — last 30 days"
      />

      <div className="p-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2">
            {[
              { label: 'Total spend', value: isLoading ? '—' : money(totals?.cost_usd) },
              { label: 'API calls', value: isLoading ? '—' : totals?.calls },
              { label: 'Tokens', value: isLoading ? '—' : tokens(totals?.total_tokens) },
              { label: 'Credits', value: isLoading ? '—' : (totals?.credits ?? 0).toFixed(1) },
            ].map((item) => (
              <div
                key={item.label}
                className="rounded-xl border border-[#2a2a2e] bg-[#111114] px-4 py-2.5 min-w-[120px]"
              >
                <div className="text-[10px] font-bold text-[#8e8e93] uppercase tracking-wide">
                  {item.label}
                </div>
                <div className="text-lg font-bold text-[#f5f5f7] tabular-nums">{item.value}</div>
              </div>
            ))}
          </div>
          <Button size="sm" variant="secondary" onClick={() => refetch()}>
            Refresh
          </Button>
        </div>

        <UsageAnalyticsDashboard usage={usage ?? { totals: { calls: 0, failed_calls: 0, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, credits: 0, cost_usd: 0 }, by_provider: [], by_model: [], recent: [] }} loading={isLoading} />

        <div className="grid lg:grid-cols-2 gap-4">
          <Card title="By API / provider" padding={false}>
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-light">
                  {['Provider', 'Calls', 'Tokens', 'Credits', 'Spend'].map((h) => (
                    <th key={h} className="text-left px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {isLoading
                  ? [...Array(3)].map((_, i) => (
                      <tr key={i}><td colSpan={5} className="px-4 py-3"><div className="skeleton h-5 rounded" /></td></tr>
                    ))
                  : (usage?.by_provider ?? []).length === 0
                    ? <tr><td colSpan={5} className="px-4 py-6 text-center text-mid">No API usage recorded yet.</td></tr>
                    : (usage?.by_provider ?? []).map((row) => (
                      <tr key={row.name} className="border-b border-border">
                        <td className="px-4 py-2.5 font-semibold text-navy capitalize">{row.name}</td>
                        <td className="px-4 py-2.5">{row.calls}</td>
                        <td className="px-4 py-2.5">{tokens(row.tokens)}</td>
                        <td className="px-4 py-2.5">{row.credits.toFixed(1)}</td>
                        <td className="px-4 py-2.5 font-semibold">{money(row.cost_usd)}</td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </Card>

          <Card title="By model" padding={false}>
            <div className="overflow-x-auto max-h-[360px]">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-light">
                    {['Model', 'Calls', 'Tokens', 'Credits', 'Spend'].map((h) => (
                      <th key={h} className="text-left px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(usage?.by_model ?? []).map((row) => (
                    <tr key={row.name} className="border-b border-border">
                      <td className="px-4 py-2.5 font-semibold text-navy break-all">{row.name}</td>
                      <td className="px-4 py-2.5">{row.calls}</td>
                      <td className="px-4 py-2.5">{tokens(row.tokens)}</td>
                      <td className="px-4 py-2.5">{row.credits.toFixed(1)}</td>
                      <td className="px-4 py-2.5 font-semibold">{money(row.cost_usd)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>

        <Card title="Recent API calls" padding={false}>
          <div className="overflow-x-auto max-h-[420px] overflow-y-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-light sticky top-0 z-10">
                  {['When', 'Client', 'Provider', 'Model', 'Operation', 'Tokens', 'Credits', 'Spend', 'Status'].map((h) => (
                    <th key={h} className="text-left px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(usage?.recent ?? []).map((row) => (
                  <tr key={row.id} className="border-b border-border hover:bg-light/50">
                    <td className="px-4 py-2.5 text-lt whitespace-nowrap">{row.created_at ? timeAgo(row.created_at) : '—'}</td>
                    <td className="px-4 py-2.5">{row.client || '—'}</td>
                    <td className="px-4 py-2.5 capitalize">{row.provider}</td>
                    <td className="px-4 py-2.5 max-w-[180px] truncate" title={row.model}>{row.model || '—'}</td>
                    <td className="px-4 py-2.5 max-w-[200px] truncate" title={row.operation}>{row.operation}</td>
                    <td className="px-4 py-2.5">{tokens(row.total_tokens)}</td>
                    <td className="px-4 py-2.5">{Number(row.credits || 0).toFixed(1)}</td>
                    <td className="px-4 py-2.5 font-semibold">{money(row.cost_usd)}</td>
                    <td className="px-4 py-2.5">
                      <Badge variant={row.success ? 'green' : 'red'}>{row.success ? 'OK' : 'Failed'}</Badge>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </div>
  )
}
