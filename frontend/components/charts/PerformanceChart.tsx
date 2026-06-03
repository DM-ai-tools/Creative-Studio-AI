'use client'

import React from 'react'
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, Legend,
} from 'recharts'
import { formatDate } from '@/lib/utils'
import type { PerformanceMetric } from '@/types'

interface PerformanceChartProps {
  data: PerformanceMetric[]
  metric?: 'roas' | 'ctr' | 'impressions' | 'spend'
}

const metricConfig = {
  roas: { label: 'ROAS', color: '#00C2A8', format: (v: number) => `${v.toFixed(2)}×` },
  ctr: { label: 'CTR', color: '#1F4DB5', format: (v: number) => `${(v * 100).toFixed(2)}%` },
  impressions: { label: 'Impressions', color: '#6B3FA0', format: (v: number) => v.toLocaleString() },
  spend: { label: 'Spend ($)', color: '#F59E0B', format: (v: number) => `$${v.toFixed(2)}` },
}

export default function PerformanceChart({ data, metric = 'roas' }: PerformanceChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-48 text-sm text-lt">
        No performance data available yet.
      </div>
    )
  }

  const cfg = metricConfig[metric]
  const chartData = data.map((d) => ({
    date: formatDate(d.date, 'MMM d'),
    value: d[metric] as number,
  }))

  return (
    <ResponsiveContainer width="100%" height={240}>
      <LineChart data={chartData} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#E0E6EF" />
        <XAxis dataKey="date" tick={{ fontSize: 10, fill: '#8EA3BC' }} axisLine={false} tickLine={false} />
        <YAxis tick={{ fontSize: 10, fill: '#8EA3BC' }} axisLine={false} tickLine={false} tickFormatter={cfg.format} width={56} />
        <Tooltip
          formatter={(v: number) => [cfg.format(v), cfg.label]}
          labelStyle={{ fontSize: 11, color: '#0F1B3D' }}
          contentStyle={{ border: '1px solid #E0E6EF', borderRadius: 8, fontSize: 11 }}
        />
        <Line
          type="monotone"
          dataKey="value"
          name={cfg.label}
          stroke={cfg.color}
          strokeWidth={2}
          dot={false}
          activeDot={{ r: 4 }}
        />
      </LineChart>
    </ResponsiveContainer>
  )
}
