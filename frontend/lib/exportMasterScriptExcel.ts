import * as XLSX from 'xlsx'
import type { MasterBeat } from '@/components/brief/MasterScriptPreview'

export interface MasterScriptExportOptions {
  fileName?: string
  warnings?: string[]
  targetSeconds?: number
  /** When editing inline, pass the current draft voice lines. */
  spokenOverrides?: string[]
}

export function downloadMasterScriptExcel(
  beats: MasterBeat[],
  options?: MasterScriptExportOptions
): void {
  if (!beats.length) return

  const wb = XLSX.utils.book_new()

  const timelineRows: Array<Array<string | number>> = [
    [
      'Beat',
      'Start',
      'End',
      'Voice (what avatar says)',
      'Visual (B-roll / camera)',
      'Stats image',
      'Notes',
    ],
    ...beats.map((beat, i) => {
      const spoken = (options?.spokenOverrides?.[i] ?? beat.spoken).trim()
      const stats =
        beat.stat_headline?.trim() ||
        beat.stat_image?.trim() ||
        '—'
      const notes = beat.stat_warning?.trim() || ''
      return [i + 1, beat.start, beat.end, spoken, beat.visual, stats, notes]
    }),
  ]

  const wsTimeline = XLSX.utils.aoa_to_sheet(timelineRows)
  wsTimeline['!cols'] = [
    { wch: 6 },
    { wch: 8 },
    { wch: 8 },
    { wch: 55 },
    { wch: 55 },
    { wch: 22 },
    { wch: 30 },
  ]
  XLSX.utils.book_append_sheet(wb, wsTimeline, 'Master script')

  const metaRows: Array<[string, string]> = [
    ['Field', 'Value'],
    ['Exported at', new Date().toLocaleString()],
    ['Total beats', String(beats.length)],
  ]
  if (options?.targetSeconds) {
    metaRows.push(['Target duration (seconds)', String(options.targetSeconds)])
  }
  const wsMeta = XLSX.utils.aoa_to_sheet(metaRows)
  wsMeta['!cols'] = [{ wch: 28 }, { wch: 40 }]
  XLSX.utils.book_append_sheet(wb, wsMeta, 'Info')

  const warnings = (options?.warnings ?? []).filter(Boolean)
  if (warnings.length > 0) {
    const wsWarnings = XLSX.utils.aoa_to_sheet([
      ['Warning'],
      ...warnings.map((w) => [w]),
    ])
    wsWarnings['!cols'] = [{ wch: 90 }]
    XLSX.utils.book_append_sheet(wb, wsWarnings, 'Warnings')
  }

  const safeName = (options?.fileName || 'master-script')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 48)

  XLSX.writeFile(wb, `${safeName || 'master-script-timeline'}.xlsx`)
}
