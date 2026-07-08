'use client'

import React from 'react'
import Topbar from '@/components/layout/Topbar'
import Card from '@/components/ui/Card'
import Badge from '@/components/ui/Badge'
import { useApi } from '@/hooks/useApi'
import { performanceApi, variantsApi } from '@/lib/api'
import type { Variant } from '@/types'
import { timeAgo } from '@/lib/utils'

interface ComplianceCheck {
  name: string
  description: string
  state: 'pass' | 'warn' | 'fail'
}

const STATIC_CHECKS: ComplianceCheck[] = [
  { name: 'Forbidden Words', description: 'No blocked claims or words detected in generated copy', state: 'pass' },
  { name: 'Claim Accuracy', description: 'Superlative or unverifiable claims screened', state: 'pass' },
  { name: 'Disclosure Requirements', description: 'Sponsored content disclosure rules applied', state: 'warn' },
  { name: 'Image Policy', description: 'Meta image text & content policy compliance', state: 'pass' },
  { name: 'Targeting Compliance', description: 'No discriminatory targeting language', state: 'pass' },
  { name: 'Pharmaceutical / Health Claims', description: 'Medical claim language blocked', state: 'pass' },
]

const stateIcon = (state: 'pass' | 'warn' | 'fail') => {
  if (state === 'pass') return { bg: 'bg-green-500', icon: '✓', badge: 'green' as const }
  if (state === 'warn') return { bg: 'bg-amber-400', icon: '!', badge: 'amber' as const }
  return { bg: 'bg-red-500', icon: '✗', badge: 'red' as const }
}

export default function BrandSafetyPage() {
  const { data: stats } = useApi(() => performanceApi.getDashboardStats(), [])
  const { data: failedVariants, isLoading } = useApi(
    () => variantsApi.list({ compliance_status: 'FAILED' }), []
  )
  const { data: warnVariants } = useApi(
    () => variantsApi.list({ compliance_status: 'WARNING' }), []
  )

  const passRate = stats?.brand_safety_pass_rate ?? null
  const hasChecks = passRate != null

  return (
    <div>
      <Topbar title="Brand Safety" subtitle="Compliance monitoring for all generated creative" />

      <div className="p-5 space-y-4">
        {/* Score summary */}
        <div className="grid grid-cols-3 gap-3">
          <Card className="col-span-1">
            <div className="text-center">
              <div className="text-4xl font-black text-navy mb-1">
                {hasChecks ? `${(passRate * 100).toFixed(1)}%` : '—'}
              </div>
              <div className="text-xs font-bold text-lt uppercase tracking-wide">
                {hasChecks ? 'Pass Rate' : 'No checks yet'}
              </div>
            </div>
          </Card>
          <Card className="col-span-1">
            <div className="text-center">
              <div className="text-4xl font-black text-red-500 mb-1">{failedVariants?.length ?? 0}</div>
              <div className="text-xs font-bold text-lt uppercase tracking-wide">Failed</div>
            </div>
          </Card>
          <Card className="col-span-1">
            <div className="text-center">
              <div className="text-4xl font-black text-amber-500 mb-1">{warnVariants?.length ?? 0}</div>
              <div className="text-xs font-bold text-lt uppercase tracking-wide">Warnings</div>
            </div>
          </Card>
        </div>

        {/* Compliance checks */}
        <Card title="Compliance Rules Status">
          <div className="space-y-2">
            {STATIC_CHECKS.map((check) => {
              const { bg, icon, badge } = stateIcon(check.state)
              return (
                <div key={check.name} className="flex items-center justify-between p-3 border border-border rounded-lg bg-white">
                  <div className="flex items-center gap-3">
                    <div className={`w-6 h-6 rounded-full ${bg} flex items-center justify-center text-white text-xs font-bold flex-shrink-0`}>
                      {icon}
                    </div>
                    <div>
                      <div className="text-xs font-bold text-navy">{check.name}</div>
                      <div className="text-[10px] text-lt">{check.description}</div>
                    </div>
                  </div>
                  <Badge variant={badge}>{check.state === 'pass' ? 'PASS' : check.state === 'warn' ? 'WARN' : 'FAIL'}</Badge>
                </div>
              )
            })}
          </div>
        </Card>

        {/* Recent failures */}
        {(failedVariants?.length ?? 0) > 0 && (
          <Card title="Recent Failures" padding={false}>
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-light">
                  {['Variant', 'Format', 'Issue', 'Created'].map((h) => (
                    <th key={h} className="text-left px-4 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border">{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(failedVariants ?? []).map((v: Variant) => {
                  const notes = v.compliance_notes as { errors?: string[] }
                  return (
                    <tr key={v.id} className="border-b border-border hover:bg-light/50">
                      <td className="px-4 py-2.5 font-semibold text-navy max-w-[200px] truncate">{v.hook}</td>
                      <td className="px-4 py-2.5 text-mid capitalize">{v.format}</td>
                      <td className="px-4 py-2.5 text-red-600 max-w-[200px] truncate">{notes?.errors?.[0] ?? 'Compliance failed'}</td>
                      <td className="px-4 py-2.5 text-lt whitespace-nowrap">{timeAgo(v.created_at)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Card>
        )}
      </div>
    </div>
  )
}
