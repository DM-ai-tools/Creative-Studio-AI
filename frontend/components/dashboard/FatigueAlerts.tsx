import React from 'react'
import Badge from '@/components/ui/Badge'
import Button from '@/components/ui/Button'
import type { FatigueAlert } from '@/types'
import { formatROAS } from '@/lib/utils'

interface FatigueAlertsProps {
  alerts: FatigueAlert[]
  onReplace(variantId: string): void
  onPause(variantId: string): void
}

export default function FatigueAlerts({ alerts, onReplace, onPause }: FatigueAlertsProps) {
  if (alerts.length === 0) {
    return <p className="text-sm text-lt py-4 text-center">No fatigue alerts — all variants performing well.</p>
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-xs">
        <thead>
          <tr className="bg-light">
            {['Variant', 'Personal Best', 'Current 7d ROAS', 'Drop', 'Frequency', 'Action'].map((h) => (
              <th key={h} className="text-left px-3 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr key={a.variant_id} className="border-b border-border hover:bg-light/50">
              <td className="px-3 py-2.5 font-semibold text-navy max-w-[200px] truncate">{a.hook}</td>
              <td className="px-3 py-2.5 text-mid">{formatROAS(a.roas_personal_best)}</td>
              <td className="px-3 py-2.5 text-mid">{formatROAS(a.roas_7d)}</td>
              <td className="px-3 py-2.5">
                <Badge variant={a.drop_pct >= 50 ? 'red' : 'amber'}>−{a.drop_pct}%</Badge>
              </td>
              <td className="px-3 py-2.5 text-mid">{a.frequency_7d.toFixed(1)}</td>
              <td className="px-3 py-2.5">
                <div className="flex gap-1">
                  <Button size="sm" variant="primary" onClick={() => onReplace(a.variant_id)}>
                    Replace
                  </Button>
                  <Button size="sm" variant="outline" onClick={() => onPause(a.variant_id)}>
                    Pause
                  </Button>
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
