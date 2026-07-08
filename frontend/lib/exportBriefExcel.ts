import * as XLSX from 'xlsx'
import type { StrategyPreviewResult } from '@/types'
import type { BriefGenerationSettings } from '@/components/brief/BriefGenerationPanel'
import type { HeyGenVideoSettings } from '@/lib/heygenOptions'

export interface BriefExportPayload {
  /** Steps 1–9 form + settings */
  step1: {
    campaign_name: string
    brand_name: string
    objective: string
    target_variants: number
  }
  step2: {
    creative_formats: string
    aspect_ratio_hint: string
    video_duration_seconds: number
    script_source: string
    website_url?: string
    custom_prompt?: string
    pdf_filename?: string
    reference_image?: string
  }
  step3: {
    target_audience: string
    geography: string
    age_range: string
    languages: string
    tone_of_voice: string
  }
  step4: {
    placements: string
    hook_frameworks: string
  }
  step5: {
    hero_product: string
    offer_key_message: string
    creative_brief_notes: string
  }
  step6?: {
    heygen_avatar: string
    heygen_voice: string
    aspect_ratio: string
    scene: string
    delivery_style: string
    visual_cues: string
  }
  step7: {
    cta_text: string
  }
  step8: {
    approved_script: string
    generated_full_script: string
    spoken_script_for_heygen: string
    script_source_detail: string
  }
  step9: {
    copy_model: string
    image_model: string
    video_provider: string
    video_duration_seconds: number
    higgsfield_voice?: string
  }
  icp_text: string
  icp_fields: Record<string, string>
  strategy_preview?: StrategyPreviewResult | null
  exported_at: string
}

interface ScriptLineRow {
  line_number: number
  start: string
  end: string
  dialogue: string
}

function parseScriptLines(script: string): ScriptLineRow[] {
  const lineRe = /^\[(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\]\s*(.+)$/
  const rows: ScriptLineRow[] = []
  for (const raw of script.split(/\r?\n/)) {
    const trimmed = raw.trim()
    if (!trimmed) continue
    const match = trimmed.match(lineRe)
    if (match) {
      rows.push({
        line_number: rows.length + 1,
        start: match[1],
        end: match[2],
        dialogue: match[3].trim(),
      })
    }
  }
  if (rows.length === 0 && script.trim()) {
    rows.push({
      line_number: 1,
      start: '00:00',
      end: '',
      dialogue: script.trim(),
    })
  }
  return rows
}

function parseIcpFields(icpText: string): Record<string, string> {
  const fields: Record<string, string> = {}
  if (!icpText.trim()) return fields
  let currentKey: string | null = null
  const buf: string[] = []
  for (const line of icpText.split(/\r?\n/)) {
    const colon = line.indexOf(':')
    if (colon > 0 && line.slice(0, colon).trim() === line.slice(0, colon).trim().toUpperCase()) {
      if (currentKey) fields[currentKey] = buf.join(' ').trim()
      currentKey = line.slice(0, colon).trim()
      buf.length = 0
      const rest = line.slice(colon + 1).trim()
      if (rest) buf.push(rest)
    } else if (currentKey && line.trim()) {
      buf.push(line.trim())
    }
  }
  if (currentKey) fields[currentKey] = buf.join(' ').trim()
  return fields
}

function buildIcpSheet(icpText: string, icpFields: Record<string, string>): Array<[string, string, string]> {
  const rows: Array<[string, string, string]> = [['Section', 'Field', 'Value']]
  rows.push(['ICP Profile', 'Full Text', icpText])
  for (const [key, val] of Object.entries(icpFields)) {
    rows.push(['ICP Profile', key, val])
  }
  return rows
}

function kvRows(
  rows: Array<{ step: string; field: string; value: string }>
): Array<[string, string, string]> {
  return [['Step', 'Field', 'Value'], ...rows.map((r) => [r.step, r.field, r.value])]
}

function buildBriefOverviewSheet(payload: BriefExportPayload): Array<[string, string, string]> {
  const rows: Array<{ step: string; field: string; value: string }> = []

  const add = (step: string, field: string, value: string | number | undefined) => {
    rows.push({ step, field, value: value === undefined || value === '' ? '—' : String(value) })
  }

  add('Step 1 — Campaign & Brand', 'Campaign Name', payload.step1.campaign_name)
  add('Step 1 — Campaign & Brand', 'Brand', payload.step1.brand_name)
  add('Step 1 — Campaign & Brand', 'Objective', payload.step1.objective)
  add('Step 1 — Campaign & Brand', 'Target Variants', payload.step1.target_variants)

  add('Step 2 — Creative Formats', 'Creative Formats', payload.step2.creative_formats)
  add('Step 2 — Creative Formats', 'Aspect Ratio', payload.step2.aspect_ratio_hint)
  add('Step 2 — Creative Formats', 'Video Duration (seconds)', payload.step2.video_duration_seconds)
  add('Step 2 — Script Source', 'Mode', payload.step2.script_source)
  if (payload.step2.website_url) add('Step 2 — Script Source', 'Website URL', payload.step2.website_url)
  if (payload.step2.custom_prompt) add('Step 2 — Script Source', 'Custom Prompt', payload.step2.custom_prompt)
  if (payload.step2.pdf_filename) add('Step 2 — Script Source', 'PDF File', payload.step2.pdf_filename)
  if (payload.step2.reference_image)
    add('Step 2 — Script Source', 'Reference Image', payload.step2.reference_image)

  add('Step 3 — Audience & Tone', 'Target Audience', payload.step3.target_audience)
  add('Step 3 — Audience & Tone', 'Geography', payload.step3.geography)
  add('Step 3 — Audience & Tone', 'Age Range', payload.step3.age_range)
  add('Step 3 — Audience & Tone', 'Languages', payload.step3.languages)
  add('Step 3 — Audience & Tone', 'Tone of Voice', payload.step3.tone_of_voice)

  add('Step 4 — Platform & Placement', 'Placements', payload.step4.placements)
  add('Step 4 — Platform & Placement', 'Hook Frameworks', payload.step4.hook_frameworks)

  add('Step 5 — Script & Content', 'Hero Product', payload.step5.hero_product)
  add('Step 5 — Script & Content', 'Offer / Key Message', payload.step5.offer_key_message)
  add('Step 5 — Script & Content', 'Creative Brief Notes', payload.step5.creative_brief_notes)

  if (payload.step6) {
    add('Step 6 — HeyGen Video', 'Avatar', payload.step6.heygen_avatar)
    add('Step 6 — HeyGen Video', 'Voice', payload.step6.heygen_voice)
    add('Step 6 — HeyGen Video', 'Aspect Ratio', payload.step6.aspect_ratio)
    add('Step 6 — HeyGen Video', 'Scene', payload.step6.scene)
    add('Step 6 — HeyGen Video', 'Delivery Style', payload.step6.delivery_style)
    add('Step 6 — HeyGen Video', 'Visual Cues', payload.step6.visual_cues)
  }

  add('Step 7 — Call to Action', 'CTA Text', payload.step7.cta_text)

  add('Step 8 — Avatar Script', 'Status', payload.step8.generated_full_script ? 'Generated' : 'Not generated')
  add('Step 8 — Avatar Script', 'Source', payload.step8.script_source_detail)
  add('Step 8 — Avatar Script', 'Generated Voice Script (timed)', payload.step8.generated_full_script)
  add('Step 8 — Avatar Script', 'Spoken Script for HeyGen', payload.step8.spoken_script_for_heygen)
  add(
    'Step 8 — Avatar Script',
    'Word Count',
    payload.step8.generated_full_script.split(/\s+/).filter(Boolean).length ||
      payload.step8.spoken_script_for_heygen.split(/\s+/).filter(Boolean).length
  )

  if (payload.icp_text) {
    add('ICP Profile', 'Full Text', payload.icp_text)
    for (const [key, val] of Object.entries(payload.icp_fields)) {
      add('ICP Profile', key, val)
    }
  }

  add('Step 9 — AI Models', 'Copy Model', payload.step9.copy_model)
  add('Step 9 — AI Models', 'Image Model', payload.step9.image_model)
  add('Step 9 — AI Models', 'Video Provider', payload.step9.video_provider)
  add('Step 9 — AI Models', 'Video Duration (seconds)', payload.step9.video_duration_seconds)
  if (payload.step9.higgsfield_voice)
    add('Step 9 — AI Models', 'Higgsfield Voice', payload.step9.higgsfield_voice)

  add('Export', 'Exported At', payload.exported_at)

  return kvRows(rows)
}

function buildStrategySheet(preview: StrategyPreviewResult): Array<[string, string, string]> {
  const rows: Array<[string, string, string]> = [['Section', 'Field', 'Value']]

  const add = (section: string, field: string, value: string) => {
    rows.push([section, field, value])
  }

  add('Framework', 'Name', preview.framework_name)
  add('Framework', 'Description', preview.framework_description)
  add('Framework', 'Structure', preview.framework_structure.join(' → '))

  add('ICP', 'Full Profile', preview.icp_text)
  for (const [key, val] of Object.entries(preview.icp_fields)) {
    add('ICP', key, val)
  }

  preview.hook_options.forEach((hook, i) => add('Hooks', `Hook ${i + 1}`, hook))

  add('HALO', 'H — Hook', preview.halo_strategy.hook)
  add('HALO', 'A — Agitate', preview.halo_strategy.agitate)
  add('HALO', 'L — Lift', preview.halo_strategy.lift)
  add('HALO', 'O — Offer', preview.halo_strategy.offer)

  preview.body_outline.forEach((block, i) => {
    add('Body', `${i + 1}. ${block.section}`, block.talking_points)
    if (block.duration_hint) add('Body', `Duration ${i + 1}`, block.duration_hint)
  })

  add('Competitors', 'Positioning', preview.competitor_positioning)
  preview.differentiation_points.forEach((pt, i) => add('Competitors', `Differentiator ${i + 1}`, pt))

  return rows
}

export function downloadBriefExcel(payload: BriefExportPayload): void {
  const wb = XLSX.utils.book_new()

  const overview = buildBriefOverviewSheet(payload)
  const wsOverview = XLSX.utils.aoa_to_sheet(overview)
  wsOverview['!cols'] = [{ wch: 28 }, { wch: 32 }, { wch: 80 }]
  XLSX.utils.book_append_sheet(wb, wsOverview, 'Brief Steps 1-9')

  if (payload.icp_text.trim()) {
    const wsIcp = XLSX.utils.aoa_to_sheet(buildIcpSheet(payload.icp_text, payload.icp_fields))
    wsIcp['!cols'] = [{ wch: 16 }, { wch: 28 }, { wch: 90 }]
    XLSX.utils.book_append_sheet(wb, wsIcp, 'ICP Profile')
  }

  const script =
    payload.step8.generated_full_script.trim() || payload.step8.spoken_script_for_heygen.trim()
  if (script) {
    const lines = parseScriptLines(payload.step8.generated_full_script || script)
    const wsScript = XLSX.utils.aoa_to_sheet([
      ['Line #', 'Start', 'End', 'Dialogue'],
      ...lines.map((l) => [l.line_number, l.start, l.end, l.dialogue]),
      [],
      ['Generated Voice Script (with timestamps)'],
      [payload.step8.generated_full_script || script],
      [],
      ['Spoken script for HeyGen (no timestamps)'],
      [payload.step8.spoken_script_for_heygen || '—'],
    ])
    wsScript['!cols'] = [{ wch: 8 }, { wch: 10 }, { wch: 10 }, { wch: 90 }]
    XLSX.utils.book_append_sheet(wb, wsScript, 'Voice Script')
  }

  if (payload.strategy_preview) {
    const wsStrategy = XLSX.utils.aoa_to_sheet(buildStrategySheet(payload.strategy_preview))
    wsStrategy['!cols'] = [{ wch: 20 }, { wch: 28 }, { wch: 80 }]
    XLSX.utils.book_append_sheet(wb, wsStrategy, 'Creative Strategy')
  }

  const safeName = (payload.step1.campaign_name || payload.step1.brand_name || 'brief')
    .replace(/[^\w\s-]/g, '')
    .trim()
    .replace(/\s+/g, '-')
    .slice(0, 40)

  XLSX.writeFile(wb, `${safeName || 'approved-brief'}.xlsx`)
}

/** Build export payload from BriefComposer state. */
export function buildBriefExportPayload(args: {
  formValues: {
    title?: string
    objective_id?: string
    target_variant_count?: number
    offer?: string
    product_name?: string
    cta?: string
    audience_type?: string
    geography?: string
    age_range?: string
    languages?: string
    ad_copy_tone?: string
    notes?: string
    placements?: string[]
    formats?: string[]
    hook_frameworks?: string[]
  }
  catalog?: {
    objectives?: { id: string; label: string }[]
    hook_frameworks?: { id: string; label: string }[]
    placements?: { id: string; label: string }[]
    creative_formats?: { id: string; label: string }[]
    copy_models?: { id: string; label: string }[]
    image_models?: { id: string; label: string }[]
    video_models?: { id: string; label: string }[]
    heygen_voice_options?: { id: string; label: string }[]
    higgsfield_voice_options?: { id: string; label: string }[]
  }
  brandName: string
  aspectHint: string
  genSettings: BriefGenerationSettings
  heygenSettings?: HeyGenVideoSettings
  avatarLabel: string
  voiceLabel: string
  scriptBuildMode: 'manual' | 'pdf' | 'custom' | 'website'
  websiteUrl: string
  customPrompt: string
  pdfFileName?: string
  referenceImageName?: string
  approvedScript: string | null
  generatedFullScript?: string | null
  icpText?: string | null
  customScriptText?: string
  strategyPreview: StrategyPreviewResult | null
  labelForIds: (options: { id: string; label: string }[], ids: string[]) => string
}): BriefExportPayload {
  const {
    formValues: d,
    catalog,
    brandName,
    aspectHint,
    genSettings,
    heygenSettings,
    avatarLabel,
    voiceLabel,
    scriptBuildMode,
    websiteUrl,
    customPrompt,
    pdfFileName,
    referenceImageName,
    approvedScript,
    generatedFullScript,
    icpText: icpTextArg,
    customScriptText,
    strategyPreview,
    labelForIds,
  } = args

  const objective =
    catalog?.objectives?.find((o) => o.id === d.objective_id)?.label ?? d.objective_id ?? ''

  const scriptSourceLabels: Record<string, string> = {
    manual: 'Manual campaign & AI',
    pdf: 'Upload PDF script',
    custom: 'Paste prompt & image',
    website: 'Website URL → AI script',
  }

  const spoken =
    approvedScript?.trim() ||
    (scriptBuildMode === 'custom' ? customScriptText?.trim() : '') ||
    ''

  const generatedFull =
    generatedFullScript?.trim() ||
    spoken ||
    ''

  const icp_text =
    icpTextArg?.trim() ||
    strategyPreview?.icp_text?.trim() ||
    ''

  const icp_fields =
    Object.keys(strategyPreview?.icp_fields ?? {}).length > 0
      ? (strategyPreview?.icp_fields ?? {})
      : parseIcpFields(icp_text)

  const copyLabel =
    catalog?.copy_models?.find((m) => m.id === genSettings.copyModel)?.label ??
    genSettings.copyModel
  const imageLabel =
    catalog?.image_models?.find((m) => m.id === genSettings.imageModel)?.label ??
    genSettings.imageModel
  const videoLabel =
    catalog?.video_models?.find((m) => m.id === genSettings.videoModel)?.label ??
    genSettings.videoModel

  return {
    step1: {
      campaign_name: d.title ?? '',
      brand_name: brandName,
      objective,
      target_variants: Number(d.target_variant_count) || 0,
    },
    step2: {
      creative_formats: labelForIds(catalog?.creative_formats ?? [], d.formats ?? []),
      aspect_ratio_hint: aspectHint,
      video_duration_seconds: genSettings.videoDurationSeconds,
      script_source: scriptSourceLabels[scriptBuildMode] ?? scriptBuildMode,
      website_url: scriptBuildMode === 'website' ? websiteUrl : undefined,
      custom_prompt: scriptBuildMode === 'custom' ? customPrompt : undefined,
      pdf_filename: scriptBuildMode === 'pdf' ? pdfFileName : undefined,
      reference_image: scriptBuildMode === 'custom' ? referenceImageName : undefined,
    },
    step3: {
      target_audience: d.audience_type ?? '',
      geography: d.geography ?? '',
      age_range: d.age_range ?? '',
      languages: d.languages ?? '',
      tone_of_voice: d.ad_copy_tone ?? '',
    },
    step4: {
      placements: labelForIds(catalog?.placements ?? [], d.placements ?? []),
      hook_frameworks: labelForIds(catalog?.hook_frameworks ?? [], d.hook_frameworks ?? []),
    },
    step5: {
      hero_product: d.product_name ?? '',
      offer_key_message: d.offer ?? '',
      creative_brief_notes: d.notes ?? '',
    },
    step6: heygenSettings
      ? {
          heygen_avatar: avatarLabel,
          heygen_voice: voiceLabel,
          aspect_ratio: heygenSettings.aspectRatioCustom || heygenSettings.aspectRatio,
          scene: heygenSettings.sceneCustom || heygenSettings.scene,
          delivery_style: heygenSettings.deliveryStyleCustom || heygenSettings.deliveryStyle,
          visual_cues: heygenSettings.visualCues,
        }
      : undefined,
    step7: {
      cta_text: d.cta ?? '',
    },
    step8: {
      approved_script: generatedFull,
      generated_full_script: generatedFull,
      spoken_script_for_heygen: spoken,
      script_source_detail: scriptSourceLabels[scriptBuildMode] ?? '',
    },
    step9: {
      copy_model: copyLabel,
      image_model: imageLabel,
      video_provider: videoLabel,
      video_duration_seconds: genSettings.videoDurationSeconds,
      higgsfield_voice: genSettings.higgsfieldVoicePreset || undefined,
    },
    icp_text,
    icp_fields,
    strategy_preview: strategyPreview,
    exported_at: new Date().toLocaleString(),
  }
}
