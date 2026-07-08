import type { PerformanceStatsContext } from '@/types'

/** Merge OCR results from multiple dashboard screenshots. */
export function mergePerformanceStats(
  contexts: PerformanceStatsContext[]
): PerformanceStatsContext | null {
  const valid = contexts.filter(Boolean)
  if (valid.length === 0) return null
  if (valid.length === 1) return valid[0]

  const proofLines: string[] = []
  const metrics: { label: string; value: string }[] = []
  const summaries: string[] = []
  const industries: string[] = []
  const campaigns: string[] = []

  const scalarKeys = [
    'headline_stat',
    'roas',
    'roi',
    'conversions',
    'clicks',
    'purchases_sales',
    'revenue',
    'conversion_value',
    'cost',
    'cost_per_conversion',
    'conv_value_per_cost',
    'lead_forms',
    'timeline',
    'growth_story',
  ] as const

  const merged: PerformanceStatsContext = {
    industry: '',
    campaign_type: '',
    headline_stat: '',
    roas: '',
    roi: '',
    conversions: '',
    clicks: '',
    purchases_sales: '',
    revenue: '',
    conversion_value: '',
    cost: '',
    cost_per_conversion: '',
    conv_value_per_cost: '',
    lead_forms: '',
    timeline: '',
    growth_story: '',
    metrics: [],
    script_proof_lines: [],
    summary_for_script: '',
  }

  valid.forEach((ctx, index) => {
    const label = ctx.industry || ctx.campaign_type || `Dashboard ${index + 1}`
    if (ctx.industry && !industries.includes(ctx.industry)) industries.push(ctx.industry)
    if (ctx.campaign_type && !campaigns.includes(ctx.campaign_type)) {
      campaigns.push(ctx.campaign_type)
    }
    ctx.script_proof_lines.forEach((line) => {
      if (line.trim() && !proofLines.includes(line.trim())) proofLines.push(line.trim())
    })
    ctx.metrics.forEach((m) => {
      if (m.label && m.value) {
        metrics.push({ label: `${label}: ${m.label}`, value: m.value })
      }
    })
    const block = (ctx.summary_for_script || '').trim()
    if (block) summaries.push(`--- ${label} ---\n${block}`)

    scalarKeys.forEach((key) => {
      const val = (ctx[key] || '').trim()
      if (!val) return
      const existing = (merged[key] || '').trim()
      if (!existing) {
        merged[key] = val
      } else if (!existing.includes(val)) {
        merged[key] = `${existing}; ${val}`
      }
    })
  })

  merged.industry = industries.join(' · ')
  merged.campaign_type = campaigns.join(' · ')
  merged.script_proof_lines = proofLines
  merged.metrics = metrics
  merged.summary_for_script = summaries.join('\n\n')
  return merged
}
