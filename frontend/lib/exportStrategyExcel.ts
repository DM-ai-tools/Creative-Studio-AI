import type { StrategyPreviewResult } from '@/types'

function escCell(value: string): string {
  return `"${String(value ?? '').replace(/"/g, '""')}"`
}

/** Build a UTF-8 CSV with BOM — opens cleanly in Excel. */
export function strategyPreviewToCsv(data: StrategyPreviewResult): string {
  const rows: string[][] = [['Section', 'Field', 'Value']]

  const add = (section: string, field: string, value: string) => {
    rows.push([section, field, value])
  }

  add('Campaign', 'Campaign Name', data.campaign_name)
  add('Campaign', 'Brand', data.brand_name)
  add('Campaign', 'Product', data.product_name)
  add('Campaign', 'Offer / Key Message', data.offer)
  add('Campaign', 'Objective', data.objective)
  add('Campaign', 'Target Audience', data.target_audience)
  add('Campaign', 'Tone', data.ad_copy_tone)
  add('Campaign', 'CTA', data.cta)
  add('Campaign', 'Duration (seconds)', String(data.target_seconds))
  add('Campaign', 'Hook Frameworks', data.hook_frameworks.join(', '))
  add('Campaign', 'Competitors', data.competitors.join(', ') || '—')
  if (data.website_url) add('Campaign', 'Website URL', data.website_url)

  add('Script Framework', 'Name', data.framework_name)
  add('Script Framework', 'Description', data.framework_description)
  add('Script Framework', 'Structure', data.framework_structure.join(' → '))

  add('ICP Profile', 'Full Text', data.icp_text)
  for (const [key, val] of Object.entries(data.icp_fields)) {
    add('ICP Profile', key, val)
  }

  data.hook_options.forEach((hook, i) => add('Hook Options', `Hook ${i + 1}`, hook))

  add('HALO Strategy', 'H — Hook', data.halo_strategy.hook)
  add('HALO Strategy', 'A — Agitate', data.halo_strategy.agitate)
  add('HALO Strategy', 'L — Lift', data.halo_strategy.lift)
  add('HALO Strategy', 'O — Offer', data.halo_strategy.offer)

  data.body_outline.forEach((block, i) => {
    add('Body Outline', `Section ${i + 1}: ${block.section}`, block.talking_points)
    if (block.duration_hint) {
      add('Body Outline', `  Duration ${i + 1}`, block.duration_hint)
    }
  })

  add('Competitor Positioning', 'Summary', data.competitor_positioning)
  data.differentiation_points.forEach((pt, i) =>
    add('Differentiation', `Point ${i + 1}`, pt)
  )

  return '\ufeff' + rows.map((row) => row.map(escCell).join(',')).join('\r\n')
}

export function downloadStrategyExcel(data: StrategyPreviewResult): void {
  const csv = strategyPreviewToCsv(data)
  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const safeName = (data.campaign_name || data.brand_name || 'strategy')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 40)
  const a = document.createElement('a')
  a.href = url
  a.download = `${safeName || 'creative-strategy'}.csv`
  a.click()
  URL.revokeObjectURL(url)
}
