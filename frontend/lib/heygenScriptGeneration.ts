import { generationApi } from '@/lib/api'
import { heygenSettingsForApi, type HeyGenVideoSettings } from '@/lib/heygenOptions'
import type { PerformanceStatsContext } from '@/types'

export type HeyGenCampaignContext = {
  productName: string
  offer: string
  brandName: string
  targetAudience: string
  adCopyTone: string
  cta: string
  notes: string
  avatarScript?: string
  forbiddenWords?: string[]
}

export async function generateSceneBrollDirections(opts: {
  campaign: HeyGenCampaignContext
  settings: HeyGenVideoSettings
  durationSeconds: number
  avatarLabel: string
  voiceLabel: string
  performanceStats?: PerformanceStatsContext
  statsImageCount?: number
}): Promise<string> {
  const apiSettings = heygenSettingsForApi(opts.settings)
  const approved = (opts.campaign.avatarScript || '').trim()
  if (!approved) {
    throw new Error('Approve the voice script first (step 1)')
  }
  const presenterEnv =
    apiSettings.scene_custom?.trim() ||
    apiSettings.scene_label?.trim() ||
    'Professional digital marketing / IT agency office'
  const result = await generationApi.generateAvatarScript({
    purpose: 'scene_broll',
    approved_script: approved,
    script_prompt: opts.settings.sceneBrollDirections || undefined,
    product_name: opts.campaign.productName,
    offer: opts.campaign.offer,
    brand_name: opts.campaign.brandName,
    target_audience: opts.campaign.targetAudience,
    ad_copy_tone: opts.campaign.adCopyTone,
    cta: opts.campaign.cta,
    notes: [
      opts.campaign.notes,
      `Presenter environment (mandatory for on-camera shots): ${presenterEnv}`,
      `Delivery: ${apiSettings.delivery_style_label}`,
    ]
      .filter(Boolean)
      .join('\n'),
    scene_label: apiSettings.scene_label,
    scene_custom: apiSettings.scene_custom,
    target_seconds: opts.durationSeconds,
    avatar_label: opts.avatarLabel,
    voice_label: opts.voiceLabel,
    forbidden_words: opts.campaign.forbiddenWords,
    performance_stats: opts.performanceStats,
    stats_image_count: opts.statsImageCount,
  })
  return result.full_script.trim()
}

export async function generateVisualCues(opts: {
  campaign: HeyGenCampaignContext
  settings: HeyGenVideoSettings
  durationSeconds: number
  avatarLabel: string
  voiceLabel: string
}): Promise<string> {
  const apiSettings = heygenSettingsForApi(opts.settings)
  const approved = (opts.campaign.avatarScript || '').trim()
  if (!approved) {
    throw new Error('Approve the voice script first (step 1)')
  }
  const result = await generationApi.generateAvatarScript({
    purpose: 'visual_cues',
    approved_script: approved,
    script_prompt: opts.settings.visualCues || undefined,
    product_name: opts.campaign.productName,
    offer: opts.campaign.offer,
    brand_name: opts.campaign.brandName,
    target_audience: opts.campaign.targetAudience,
    ad_copy_tone: opts.campaign.adCopyTone,
    cta: opts.campaign.cta,
    notes: [
      opts.campaign.notes,
      `Scene: ${apiSettings.scene_label}`,
      `Style: ${apiSettings.delivery_style_label}`,
    ]
      .filter(Boolean)
      .join('\n'),
    target_seconds: opts.durationSeconds,
    avatar_label: opts.avatarLabel,
    voice_label: opts.voiceLabel,
    forbidden_words: opts.campaign.forbiddenWords,
  })
  return result.full_script.trim()
}
