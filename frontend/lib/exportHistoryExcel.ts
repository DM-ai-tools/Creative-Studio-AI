import * as XLSX from 'xlsx'
import { labelForUseCase } from '@/lib/imageUseCases'
import { getVariantPreviewUrls, isMotionVariantFormat } from '@/lib/variantMedia'
import type { Brief, Variant } from '@/types'

export type HistoryMediaTab = 'image' | 'video'

export type HistoryRow = {
  variant: Variant
  brief?: Brief | null
  brandName?: string
}

function safeFileName(base: string): string {
  return (base || 'history')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 60)
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === 'object' && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {}
}

function str(value: unknown, fallback = '—'): string {
  if (value == null) return fallback
  if (typeof value === 'string') return value.trim() || fallback
  if (typeof value === 'number' || typeof value === 'boolean') return String(value)
  try {
    return JSON.stringify(value)
  } catch {
    return fallback
  }
}

function useCaseLabels(ids: unknown): string {
  if (!Array.isArray(ids) || ids.length === 0) return '—'
  return ids.map((id) => labelForUseCase(String(id))).join(', ')
}

/** Flatten one history row into A–Z generation fields for Excel. */
export function buildHistoryDetailFields(row: HistoryRow): Array<[string, string]> {
  const { variant, brief, brandName } = row
  const kb = asRecord(brief?.key_benefits)
  const params = asRecord(variant.generation_params)
  const models = asRecord(params.models)
  const imagePlan = asRecord(params.image_plan)
  const pipeline = asRecord(params.pipeline)
  const imageStep = asRecord(pipeline.image)
  const videoStep = asRecord(pipeline.video)
  const { imageUrl, videoUrl } = getVariantPreviewUrls(variant)
  const motion = isMotionVariantFormat(variant.format)

  const imageVariants = Array.isArray(kb.image_variants) ? kb.image_variants : []
  const slotIndex =
    typeof imagePlan.variant_index === 'number'
      ? imagePlan.variant_index
      : imageVariants.findIndex(
          (s) =>
            typeof s === 'object' &&
            s &&
            str((s as Record<string, unknown>).hook, '') === variant.hook
        )
  const slot =
    slotIndex >= 0 && typeof imageVariants[slotIndex] === 'object'
      ? asRecord(imageVariants[slotIndex])
      : {}

  const hookFrameworks = Array.isArray(kb.hook_frameworks)
    ? kb.hook_frameworks.map(String).join(', ')
    : '—'

  const rows: Array<[string, string]> = [
    ['Variant ID', variant.id],
    ['Created at', new Date(variant.created_at).toLocaleString()],
    ['Updated at', new Date(variant.updated_at).toLocaleString()],
    ['Status', variant.status],
    ['Compliance', variant.compliance_status],
    ['Format', variant.format],
    ['Media type', motion ? 'Video' : 'Image'],
    ['Campaign / brief', brief?.title || '—'],
    ['Brief ID', variant.brief_id],
    ['Brand', brandName || '—'],
    ['Brand ID', variant.brand_id],
    ['Objective', brief?.objective || str(kb.objective_id)],
    ['Target audience', brief?.target_audience || '—'],
    ['Tone', brief?.ad_copy_tone || str(params.tone)],
    ['Product name', brief?.product_name || '—'],
    ['Offer', str(kb.offer)],
    ['Hook frameworks / ad styles', hookFrameworks],
    ['Image aspect ratio', str(kb.image_aspect_ratio)],
    ['Hook', variant.hook || str(imagePlan.hook) || str(slot.hook)],
    ['Headline / message', variant.headline || str(imagePlan.message) || str(slot.message)],
    ['CTA', variant.cta || str(imagePlan.cta) || str(slot.cta)],
    ['Body copy', variant.body_copy || '—'],
    ['Hashtags', (variant.hashtags || []).join(' ') || '—'],
    ['Offer (caption / slot)', str(slot.offer)],
    ['Use case(s)', useCaseLabels(imagePlan.use_cases || slot.use_cases)],
    ['Ad angle', str(imagePlan.ad_angle || slot.ad_angle) || '—'],
    ['AI reasoning', str(imagePlan.reasoning || slot.reasoning)],
    ['Image generation prompt', str(imagePlan.prompt || slot.prompt)],
    ['Copy model', str(models.copy || variant.ai_model || kb.copy_model)],
    ['Image model', str(models.image || kb.image_model || imageStep.model)],
    ['Video model', str(models.video || kb.video_model)],
    ['Video duration (s)', str(models.video_duration_seconds || kb.video_duration_seconds)],
    ['HeyGen avatar ID', str(kb.heygen_avatar_id)],
    ['HeyGen voice ID', str(kb.heygen_voice_id)],
    ['Script source', str(kb.script_source)],
    ['Avatar / spoken script', str(kb.avatar_script)],
    ['Custom prompt', str(kb.custom_prompt)],
    ['Website URL', str(kb.website_url)],
    ['ICP text (brief)', str(kb.image_icp_text || kb.icp_text)],
    ['Image asset URL', imageUrl || str(imageStep.url)],
    ['Video asset URL', videoUrl || str(videoStep.url)],
    ['Image pipeline status', str(imageStep.status)],
    ['Video pipeline status', str(videoStep.status)],
    ['Image error', str(imageStep.error, '')],
    ['Video error', str(videoStep.error, '')],
  ]

  return rows.filter(([, value]) => value !== '')
}

function appendSheet(
  wb: XLSX.WorkBook,
  name: string,
  rows: Array<Array<string | number>>,
  colWidths: Array<{ wch: number }>
) {
  const ws = XLSX.utils.aoa_to_sheet(rows)
  ws['!cols'] = colWidths
  XLSX.utils.book_append_sheet(wb, ws, name.slice(0, 31))
}

export function downloadHistoryExcel(
  rows: HistoryRow[],
  opts: { tab: HistoryMediaTab; periodLabel?: string }
): void {
  if (!rows.length) return

  const wb = XLSX.utils.book_new()
  const exportedAt = new Date().toLocaleString()

  appendSheet(
    wb,
    'Info',
    [
      ['Field', 'Value'],
      ['Export type', opts.tab === 'image' ? 'Image history' : 'Video history'],
      ['Period', opts.periodLabel || 'All time'],
      ['Variants exported', String(rows.length)],
      ['Exported at', exportedAt],
    ],
    [{ wch: 22 }, { wch: 80 }]
  )

  const overviewHeader = [
    'Created',
    'Campaign',
    'Brand',
    'Format',
    'Status',
    'Hook',
    'Headline',
    'CTA',
    'Image model',
    'Video model',
    'Prompt (preview)',
    'Image URL',
    'Video URL',
    'Variant ID',
    'Brief ID',
  ]

  const overviewRows: Array<Array<string | number>> = [
    overviewHeader,
    ...rows.map((row) => {
      const fields = Object.fromEntries(buildHistoryDetailFields(row))
      const prompt = fields['Image generation prompt'] || '—'
      return [
        new Date(row.variant.created_at).toLocaleString(),
        fields['Campaign / brief'] || '—',
        fields.Brand || '—',
        fields.Format || '—',
        fields.Status || '—',
        fields.Hook || '—',
        fields['Headline / message'] || '—',
        fields.CTA || '—',
        fields['Image model'] || '—',
        fields['Video model'] || '—',
        prompt.length > 180 ? `${prompt.slice(0, 177)}…` : prompt,
        fields['Image asset URL'] || '—',
        fields['Video asset URL'] || '—',
        row.variant.id,
        row.variant.brief_id,
      ]
    }),
  ]

  appendSheet(wb, 'Overview', overviewRows, [
    { wch: 20 },
    { wch: 28 },
    { wch: 18 },
    { wch: 10 },
    { wch: 10 },
    { wch: 36 },
    { wch: 36 },
    { wch: 18 },
    { wch: 18 },
    { wch: 18 },
    { wch: 50 },
    { wch: 40 },
    { wch: 40 },
    { wch: 36 },
    { wch: 36 },
  ])

  rows.forEach((row, index) => {
    const detail = buildHistoryDetailFields(row)
    appendSheet(
      wb,
      `V${index + 1}`,
      [['Field', 'Value'], ...detail],
      [{ wch: 28 }, { wch: 100 }]
    )
  })

  const base = safeFileName(
    `creativestudio-${opts.tab}-history-${rows.length}`
  )
  XLSX.writeFile(wb, `${base}.xlsx`)
}
