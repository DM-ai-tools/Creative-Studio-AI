import * as XLSX from 'xlsx'
import { labelForUseCase, type ImageVariantSlot } from '@/lib/imageUseCases'

export interface ImageVariantExportContext {
  campaignName?: string
  brandName?: string
  objectiveId?: string
  aspectRatio?: string
  icpText?: string
}

function safeFileName(base: string): string {
  return (base || 'image-variant')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 48)
}

function useCaseLabels(slot: ImageVariantSlot): string {
  return slot.use_cases.map((id) => labelForUseCase(id)).join(', ') || '—'
}

function buildMetaRows(context?: ImageVariantExportContext): Array<[string, string]> {
  const rows: Array<[string, string]> = [['Field', 'Value']]
  if (context?.campaignName) rows.push(['Campaign name', context.campaignName])
  if (context?.brandName) rows.push(['Brand', context.brandName])
  if (context?.objectiveId) rows.push(['Objective', context.objectiveId])
  if (context?.aspectRatio) rows.push(['Aspect ratio', context.aspectRatio])
  rows.push(['Exported at', new Date().toLocaleString()])
  return rows
}

function buildVariantDetailRows(
  slot: ImageVariantSlot,
  variantIndex: number
): Array<[string, string]> {
  return [
    ['Field', 'Value'],
    ['Variant', String(variantIndex + 1)],
    ['Ad angle', slot.ad_angle || '—'],
    ['Hook (post)', slot.hook || '—'],
    ['Headline (post)', slot.message || '—'],
    ['On-image hook', slot.image_hook || '—'],
    ['On-image headline', slot.image_headline || '—'],
    ['Use case(s)', useCaseLabels(slot)],
    ['CTA on image', slot.cta || '—'],
    ['Offer (caption)', slot.offer || '—'],
    ['Image generation prompt', slot.prompt || '—'],
    ['AI reasoning', slot.reasoning || '—'],
    [
      'Generated at',
      slot.generated_at ? new Date(slot.generated_at).toLocaleString() : '—',
    ],
  ]
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

/** Download a single image variant as .xlsx for future reference. */
export function downloadImageVariantExcel(
  slot: ImageVariantSlot,
  variantIndex: number,
  context?: ImageVariantExportContext
): void {
  const wb = XLSX.utils.book_new()

  appendSheet(wb, 'Info', buildMetaRows(context), [{ wch: 22 }, { wch: 80 }])

  appendSheet(
    wb,
    `Variant ${variantIndex + 1}`,
    buildVariantDetailRows(slot, variantIndex),
    [{ wch: 28 }, { wch: 100 }]
  )

  if (context?.icpText?.trim()) {
    appendSheet(
      wb,
      'ICP Profile',
      [
        ['Field', 'Value'],
        ['ICP text', context.icpText.trim()],
      ],
      [{ wch: 14 }, { wch: 100 }]
    )
  }

  const base = safeFileName(
    `${context?.campaignName || context?.brandName || 'image'}-variant-${variantIndex + 1}`
  )
  XLSX.writeFile(wb, `${base}.xlsx`)
}

/** Download all image variants in one workbook. */
export function downloadAllImageVariantsExcel(
  slots: ImageVariantSlot[],
  context?: ImageVariantExportContext
): void {
  const wb = XLSX.utils.book_new()

  appendSheet(wb, 'Info', buildMetaRows(context), [{ wch: 22 }, { wch: 80 }])

  const overviewRows: Array<Array<string | number>> = [
    [
      'Variant',
      'Use case(s)',
      'Hook on image',
      'Message / headline',
      'CTA on image',
      'Offer (caption)',
      'Image generation prompt',
      'AI reasoning',
      'Generated at',
    ],
    ...slots.map((slot, i) => [
      i + 1,
      useCaseLabels(slot),
      slot.hook || '—',
      slot.message || '—',
      slot.cta || '—',
      slot.offer || '—',
      slot.prompt || '—',
      slot.reasoning || '—',
      slot.generated_at ? new Date(slot.generated_at).toLocaleString() : '—',
    ]),
  ]
  appendSheet(wb, 'All variants', overviewRows, [
    { wch: 8 },
    { wch: 28 },
    { wch: 36 },
    { wch: 36 },
    { wch: 22 },
    { wch: 28 },
    { wch: 70 },
    { wch: 40 },
    { wch: 22 },
  ])

  slots.forEach((slot, i) => {
    appendSheet(
      wb,
      `Variant ${i + 1}`,
      buildVariantDetailRows(slot, i),
      [{ wch: 28 }, { wch: 100 }]
    )
  })

  if (context?.icpText?.trim()) {
    appendSheet(
      wb,
      'ICP Profile',
      [
        ['Field', 'Value'],
        ['ICP text', context.icpText.trim()],
      ],
      [{ wch: 14 }, { wch: 100 }]
    )
  }

  const base = safeFileName(
    `${context?.campaignName || context?.brandName || 'image'}-variants`
  )
  XLSX.writeFile(wb, `${base}.xlsx`)
}
