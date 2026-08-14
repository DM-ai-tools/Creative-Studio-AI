'use client'

import React, { useMemo } from 'react'
import { format, parseISO } from 'date-fns'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import type { AdminUsage } from '@/types'

const CHART_COLORS = [
  '#5B9BD5',
  '#A4C639',
  '#FFC000',
  '#00B0A8',
  '#4472C4',
  '#ED7D31',
  '#7030A0',
  '#9E9E9E',
]

const darkTooltipStyle = {
  backgroundColor: '#1c1c1f',
  border: '1px solid #333',
  borderRadius: 8,
  color: '#f5f5f7',
  fontSize: 12,
}

function formatDayLabel(iso: string) {
  try {
    return format(parseISO(iso), 'd MMM')
  } catch {
    return iso
  }
}

function moneyAxis(v: number) {
  if (v >= 1000) return `$${(v / 1000).toFixed(1)}k`
  if (v >= 1) return `$${v.toFixed(0)}`
  if (v >= 0.01) return `$${v.toFixed(2)}`
  return `$${v.toFixed(4)}`
}

function countAxis(v: number) {
  if (v >= 1000) return `${(v / 1000).toFixed(1)}k`
  return String(Math.round(v))
}

type Props = {
  usage: AdminUsage
  loading?: boolean
}

export default function UsageAnalyticsDashboard({ usage, loading }: Props) {
  const models = usage.chart_models?.length ? usage.chart_models : ['Other']
  const colorMap = useMemo(() => {
    const map: Record<string, string> = {}
    models.forEach((m, i) => {
      map[m] = CHART_COLORS[i % CHART_COLORS.length]
    })
    return map
  }, [models])

  const costData = usage.daily_cost ?? []
  const requestData = usage.daily_requests ?? []
  const maxCost = Math.max(...costData.map((d) => d.total ?? 0), 0.01)
  const maxReq = Math.max(...requestData.map((d) => d.total ?? 0), 1)

  if (loading) {
    return (
      <div className="rounded-2xl border border-[#2a2a2e] bg-[#0c0c0e] p-8 min-h-[520px] flex items-center justify-center">
        <div className="text-sm text-[#8e8e93]">Loading usage analytics…</div>
      </div>
    )
  }

  if (!costData.length) {
    return (
      <div className="rounded-2xl border border-[#2a2a2e] bg-[#0c0c0e] p-12 text-center">
        <p className="text-[#f5f5f7] font-semibold mb-1">No usage data yet</p>
        <p className="text-sm text-[#8e8e93]">
          Generate a brief, scrape a brand, or run image generation to populate the charts.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-[#2a2a2e] bg-[#0c0c0e] text-[#f5f5f7] overflow-hidden">
      {/* Main cost chart */}
      <div className="px-5 pt-5 pb-2">
        <div className="flex items-baseline justify-between gap-4 mb-4">
          <div>
            <h2 className="text-lg font-semibold tracking-tight">Usage cost over time</h2>
            <p className="text-xs text-[#8e8e93] mt-0.5">
              Last {usage.period_days ?? 30} days · estimated USD by model
            </p>
          </div>
          <p className="text-2xl font-bold tabular-nums">
            ${(usage.totals?.cost_usd ?? 0).toFixed(2)}
          </p>
        </div>
        <div className="h-[280px] w-full">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={costData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid stroke="#2a2a2e" strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="date"
                tickFormatter={formatDayLabel}
                tick={{ fill: '#8e8e93', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                minTickGap={32}
              />
              <YAxis
                tickFormatter={moneyAxis}
                tick={{ fill: '#8e8e93', fontSize: 11 }}
                axisLine={false}
                tickLine={false}
                domain={[0, maxCost * 1.15 || 1]}
                width={48}
              />
              <Tooltip
                contentStyle={darkTooltipStyle}
                labelFormatter={(label) => formatDayLabel(String(label))}
                formatter={(value: number, name: string) => [`$${Number(value).toFixed(4)}`, name]}
              />
              {models.map((model, i) => (
                <Bar
                  key={model}
                  dataKey={model}
                  stackId="cost"
                  fill={colorMap[model] ?? CHART_COLORS[i % CHART_COLORS.length]}
                  radius={i === models.length - 1 ? [2, 2, 0, 0] : [0, 0, 0, 0]}
                  maxBarSize={28}
                />
              ))}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Legend */}
      <div className="px-5 py-3 border-t border-[#2a2a2e] flex flex-wrap gap-x-5 gap-y-2 justify-center">
        {models.map((model) => (
          <div key={model} className="flex items-center gap-2 text-xs text-[#c7c7cc]">
            <span
              className="w-2.5 h-2.5 rounded-sm shrink-0"
              style={{ backgroundColor: colorMap[model] }}
            />
            <span>{model}</span>
          </div>
        ))}
      </div>

      {/* Bottom row */}
      <div className="grid md:grid-cols-2 gap-px bg-[#2a2a2e] border-t border-[#2a2a2e]">
        <div className="bg-[#0c0c0e] p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Usage type</h3>
            <span className="text-[10px] text-[#8e8e93] uppercase tracking-wide">Daily total</span>
          </div>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={costData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <defs>
                  <linearGradient id="usageArea" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#7030A0" stopOpacity={0.45} />
                    <stop offset="100%" stopColor="#7030A0" stopOpacity={0.05} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#2a2a2e" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis
                  tickFormatter={moneyAxis}
                  tick={{ fill: '#8e8e93', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  domain={[0, maxCost * 1.15 || 1]}
                  width={44}
                />
                <Tooltip
                  contentStyle={darkTooltipStyle}
                  labelFormatter={(label) => formatDayLabel(String(label))}
                  formatter={(value: number) => [`$${Number(value).toFixed(4)}`, 'Total spend']}
                />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke="#7030A0"
                  strokeWidth={2}
                  fill="url(#usageArea)"
                />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="bg-[#0c0c0e] p-5">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-semibold">Request volume by model</h3>
            <span className="text-[10px] text-[#8e8e93] uppercase tracking-wide">
              {usage.totals?.calls ?? 0} calls
            </span>
          </div>
          <div className="h-[200px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={requestData} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="#2a2a2e" strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="date" hide />
                <YAxis
                  tickFormatter={countAxis}
                  tick={{ fill: '#8e8e93', fontSize: 10 }}
                  axisLine={false}
                  tickLine={false}
                  domain={[0, maxReq * 1.15 || 1]}
                  width={44}
                />
                <Tooltip
                  contentStyle={darkTooltipStyle}
                  labelFormatter={(label) => formatDayLabel(String(label))}
                  formatter={(value: number, name: string) => [Math.round(Number(value)), name]}
                />
                <Legend wrapperStyle={{ display: 'none' }} />
                {models.map((model, i) => (
                  <Bar
                    key={`req-${model}`}
                    dataKey={model}
                    stackId="req"
                    fill={colorMap[model] ?? CHART_COLORS[i % CHART_COLORS.length]}
                    maxBarSize={20}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>
    </div>
  )
}
