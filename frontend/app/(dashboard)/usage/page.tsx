'use client'

import React, { useState } from 'react'
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
import type { AdminUsage, SeedanceCreditsCheck } from '@/types'

function money(n: number | null | undefined, estimated = false) {
  if (n == null || Number.isNaN(n)) return '—'
  const prefix = estimated ? '~' : ''
  if (n >= 1) return `${prefix}$${n.toFixed(2)}`
  return `${prefix}$${n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`
}

function moneyRange(low: number, high: number) {
  if (low <= 0 && high <= 0) return '—'
  if (Math.abs(low - high) < 0.01) return money(low, true)
  return `~$${low.toFixed(2)}–$${high.toFixed(2)}`
}

function tokens(n: number | null | undefined) {
  const v = Number(n || 0)
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(2)}M`
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)}k`
  return String(v)
}

const thClass =
  'text-left px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border'
const tdClass = 'px-4 py-2.5 text-mid'
const theadRowClass = 'bg-light'
const tbodyRowClass = 'border-b border-border hover:bg-light/50'

function seedanceStatusBadge(status: SeedanceCreditsCheck['status']) {
  switch (status) {
    case 'ok':
      return <Badge variant="green">Credits OK</Badge>
    case 'no_credits':
      return <Badge variant="red">No credits</Badge>
    case 'not_configured':
      return <Badge variant="gray">Not configured</Badge>
    case 'auth_error':
      return <Badge variant="red">Auth error</Badge>
    case 'connection_error':
      return <Badge variant="blue">Connection error</Badge>
    default:
      return <Badge variant="gray">Unknown</Badge>
  }
}

export default function UsagePage() {
  const router = useRouter()
  const { user } = useAuth()
  const { data, isLoading, refetch } = useApi(() => adminApi.getUsage(), [])
  const [seedanceCheck, setSeedanceCheck] = useState<SeedanceCreditsCheck | null>(null)
  const [seedanceChecking, setSeedanceChecking] = useState(false)
  const [seedanceCheckError, setSeedanceCheckError] = useState<string | null>(null)

  const runSeedanceCheck = async () => {
    setSeedanceChecking(true)
    setSeedanceCheckError(null)
    try {
      const result = await adminApi.checkSeedanceCredits()
      setSeedanceCheck(result)
    } catch (err: unknown) {
      const message =
        err instanceof Error ? err.message : 'Could not check Seedance credits.'
      setSeedanceCheckError(message)
    } finally {
      setSeedanceChecking(false)
    }
  }

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
  const seedance = usage?.seedance
  const hasSeedance = (seedance?.successful_clips ?? 0) > 0 || (seedance?.failed_calls ?? 0) > 0

  return (
    <div>
      <Topbar
        title="Usage & costs"
        subtitle="API spend, request volume, and model breakdown — last 30 days"
      />

      <div className="p-5 space-y-5">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-3 flex-1">
            {[
              { label: 'Total spend', value: isLoading ? '—' : money(totals?.cost_usd) },
              { label: 'API calls', value: isLoading ? '—' : totals?.calls },
              { label: 'Tokens', value: isLoading ? '—' : tokens(totals?.total_tokens) },
              { label: 'Credits', value: isLoading ? '—' : (totals?.credits ?? 0).toFixed(1) },
            ].map((item) => (
              <Card key={item.label}>
                <div className="text-xs font-bold text-lt uppercase tracking-wide mb-1">
                  {item.label}
                </div>
                <div className="text-2xl font-extrabold text-navy tabular-nums">{item.value}</div>
              </Card>
            ))}
          </div>
          <Button size="sm" variant="secondary" onClick={() => refetch()}>
            Refresh
          </Button>
        </div>

        <UsageAnalyticsDashboard usage={usage ?? { totals: { calls: 0, failed_calls: 0, prompt_tokens: 0, completion_tokens: 0, total_tokens: 0, credits: 0, cost_usd: 0 }, by_provider: [], by_model: [], recent: [] }} loading={isLoading} />

        <Card title="Seedance / BytePlus billing">
          <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="space-y-1 max-w-2xl">
                <p className="text-sm text-mid leading-relaxed">
                  Check whether your BytePlus ModelArk account can accept new Seedance 2.0 and 2.5
                  video jobs. This replaces manual probe scripts in the backend.
                </p>
                {seedanceCheck?.probe_note && (
                  <p className="text-xs text-muted leading-relaxed">{seedanceCheck.probe_note}</p>
                )}
              </div>
              <Button size="sm" onClick={runSeedanceCheck} disabled={seedanceChecking}>
                {seedanceChecking ? 'Checking…' : 'Check Seedance credits'}
              </Button>
            </div>

            {seedanceCheckError && (
              <p className="text-sm text-red-600">{seedanceCheckError}</p>
            )}

            {seedanceCheck && (
              <div className="rounded-xl border border-border bg-light/40 p-4 space-y-4">
                <div className="flex flex-wrap items-center gap-3">
                  {seedanceStatusBadge(seedanceCheck.status)}
                  <span className="text-sm text-navy font-semibold">{seedanceCheck.message}</span>
                  <span className="text-xs text-lt">
                    Checked {seedanceCheck.checked_at ? timeAgo(seedanceCheck.checked_at) : 'just now'}
                  </span>
                </div>

                {seedanceCheck.task_history && (
                  <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                    {[
                      { label: 'Total tasks', value: seedanceCheck.task_history.total_tasks },
                      { label: 'Recent succeeded', value: seedanceCheck.task_history.recent_succeeded },
                      { label: 'Recent failed', value: seedanceCheck.task_history.recent_failed },
                      { label: 'Billing failures', value: seedanceCheck.task_history.recent_billing_failures },
                    ].map((item) => (
                      <div key={item.label} className="rounded-lg bg-white/70 px-3 py-2">
                        <div className="text-[10px] font-bold text-lt uppercase tracking-wide mb-0.5">
                          {item.label}
                        </div>
                        <div className="text-lg font-extrabold text-navy tabular-nums">{item.value}</div>
                      </div>
                    ))}
                  </div>
                )}

                {(seedanceCheck.models?.length ?? 0) > 0 && (
                  <div className="overflow-x-auto">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className={theadRowClass}>
                          {['Model', 'API model', 'Billing', 'Details'].map((h) => (
                            <th key={h} className={thClass}>{h}</th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {seedanceCheck.models.map((row) => (
                          <tr key={row.catalog_id} className={tbodyRowClass}>
                            <td className={`${tdClass} font-semibold text-navy`}>{row.label}</td>
                            <td className={`${tdClass} font-mono text-[11px] break-all`}>{row.api_model}</td>
                            <td className={tdClass}>
                              <Badge
                                variant={
                                  row.billing_status === 'ok'
                                    ? 'green'
                                    : row.billing_status === 'no_credits'
                                      ? 'red'
                                      : 'gray'
                                }
                              >
                                {row.billing_status}
                              </Badge>
                            </td>
                            <td className={tdClass}>{row.message}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}
          </div>
        </Card>

        {hasSeedance && (
          <Card title="Seedance / BytePlus video" padding={false}>
            <div className="p-4 border-b border-border space-y-4">
              <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
                {[
                  { label: 'Successful clips', value: seedance?.successful_clips ?? 0 },
                  { label: 'Failed calls', value: seedance?.failed_calls ?? 0 },
                  { label: 'Completion tokens', value: tokens(seedance?.total_tokens) },
                  {
                    label: 'Est. spend',
                    value: moneyRange(seedance?.cost_usd_low ?? 0, seedance?.cost_usd_high ?? 0),
                  },
                ].map((item) => (
                  <div key={item.label} className="rounded-xl bg-light/60 px-3 py-2.5">
                    <div className="text-[10px] font-bold text-lt uppercase tracking-wide mb-0.5">
                      {item.label}
                    </div>
                    <div className="text-lg font-extrabold text-navy tabular-nums">{item.value}</div>
                  </div>
                ))}
              </div>
              {seedance?.pricing_note && (
                <p className="text-xs text-muted leading-relaxed">{seedance.pricing_note}</p>
              )}
            </div>

            {(seedance?.by_model?.length ?? 0) > 0 && (
              <div className="border-b border-border">
                <div className="px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide bg-light">
                  By Seedance model
                </div>
                <table className="w-full text-xs">
                  <thead>
                    <tr className={theadRowClass}>
                      {['Model', 'Clips', 'Failed', 'Tokens', 'Est. spend'].map((h) => (
                        <th key={h} className={thClass}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(seedance?.by_model ?? []).map((row) => (
                      <tr key={row.model} className={tbodyRowClass}>
                        <td className={`${tdClass} font-semibold text-navy break-all`}>{row.model}</td>
                        <td className={tdClass}>{row.clips}</td>
                        <td className={tdClass}>{row.failed}</td>
                        <td className={tdClass}>{tokens(row.tokens)}</td>
                        <td className={`${tdClass} font-semibold text-navy`}>
                          {moneyRange(row.cost_usd_low, row.cost_usd_high)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <div>
              <div className="px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide bg-light">
                Recent Seedance clips
              </div>
              <div className="overflow-x-auto max-h-[360px] overflow-y-auto">
                <table className="w-full text-xs">
                  <thead>
                    <tr className={`${theadRowClass} sticky top-0 z-10`}>
                      {['When', 'Client', 'Task ID', 'Model', 'Tokens', 'Est. spend', 'Notes'].map((h) => (
                        <th key={h} className={thClass}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {(seedance?.recent_clips ?? []).length === 0 ? (
                      <tr>
                        <td colSpan={7} className="px-4 py-6 text-center text-mid">
                          No successful Seedance clips in this period.
                        </td>
                      </tr>
                    ) : (
                      (seedance?.recent_clips ?? []).map((row) => (
                        <tr key={row.id} className={tbodyRowClass}>
                          <td className={`${tdClass} whitespace-nowrap text-lt`}>
                            {row.created_at ? timeAgo(row.created_at) : '—'}
                          </td>
                          <td className={tdClass}>{row.client || '—'}</td>
                          <td className={`${tdClass} font-mono text-[11px] max-w-[140px] truncate`} title={row.task_id ?? undefined}>
                            {row.task_id || '—'}
                          </td>
                          <td className={`${tdClass} max-w-[160px] truncate`} title={row.model}>{row.model}</td>
                          <td className={tdClass}>{tokens(row.tokens)}</td>
                          <td className={`${tdClass} font-semibold text-navy`}>
                            {moneyRange(row.cost_usd_low, row.cost_usd_high)}
                          </td>
                          <td className={tdClass}>
                            {row.recovered ? (
                              <Badge variant="blue">Recovered</Badge>
                            ) : (
                              <Badge variant="green">OK</Badge>
                            )}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </Card>
        )}

        <div className="grid lg:grid-cols-2 gap-4">
          <Card title="By API / provider" padding={false}>
            <table className="w-full text-xs">
              <thead>
                <tr className={theadRowClass}>
                  {['Provider', 'Calls', 'Tokens', 'Credits', 'Spend'].map((h) => (
                    <th key={h} className={thClass}>{h}</th>
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
                      <tr key={row.name} className={tbodyRowClass}>
                        <td className={`${tdClass} font-semibold text-navy capitalize`}>{row.name}</td>
                        <td className={tdClass}>{row.calls}</td>
                        <td className={tdClass}>{tokens(row.tokens)}</td>
                        <td className={tdClass}>{row.credits.toFixed(1)}</td>
                        <td className={`${tdClass} font-semibold text-navy`}>{money(row.cost_usd)}</td>
                      </tr>
                    ))}
              </tbody>
            </table>
          </Card>

          <Card title="By model" padding={false}>
            <div className="overflow-x-auto max-h-[360px]">
              <table className="w-full text-xs">
                <thead>
                  <tr className={theadRowClass}>
                    {['Model', 'Calls', 'Tokens', 'Credits', 'Spend'].map((h) => (
                      <th key={h} className={thClass}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(usage?.by_model ?? []).map((row) => (
                    <tr key={row.name} className={tbodyRowClass}>
                      <td className={`${tdClass} font-semibold text-navy break-all`}>{row.name}</td>
                      <td className={tdClass}>{row.calls}</td>
                      <td className={tdClass}>{tokens(row.tokens)}</td>
                      <td className={tdClass}>{row.credits.toFixed(1)}</td>
                      <td className={`${tdClass} font-semibold text-navy`}>{money(row.cost_usd)}</td>
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
                <tr className={`${theadRowClass} sticky top-0 z-10`}>
                  {['When', 'Client', 'Provider', 'Model', 'Operation', 'Tokens', 'Credits', 'Spend', 'Status'].map((h) => (
                    <th key={h} className={thClass}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(usage?.recent ?? []).map((row) => (
                  <tr key={row.id} className={tbodyRowClass}>
                    <td className={`${tdClass} whitespace-nowrap text-lt`}>{row.created_at ? timeAgo(row.created_at) : '—'}</td>
                    <td className={tdClass}>{row.client || '—'}</td>
                    <td className={`${tdClass} capitalize`}>{row.provider}</td>
                    <td className={`${tdClass} max-w-[180px] truncate`} title={row.model}>{row.model || '—'}</td>
                    <td className={`${tdClass} max-w-[200px] truncate`} title={row.operation}>{row.operation}</td>
                    <td className={tdClass}>{tokens(row.total_tokens)}</td>
                    <td className={tdClass}>{Number(row.credits || 0).toFixed(1)}</td>
                    <td className={`${tdClass} font-semibold text-navy`}>
                      {money(row.cost_usd, row.cost_estimated)}
                    </td>
                    <td className={tdClass}>
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
