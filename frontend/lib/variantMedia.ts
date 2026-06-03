import { assetUrl } from '@/lib/utils'
import type { Variant } from '@/types'

export type PipelineMedia = {
  status?: string
  url?: string
  error?: string
  model?: string
  production?: string
  subtitles_applied?: boolean
  subtitle_warning?: string
  logo_applied?: boolean
  logo_warning?: string
  voiceover?: {
    status?: string
    script?: string
    voice?: string
    error?: string
  }
}

export function getVariantPipeline(variant: Variant) {
  return variant.generation_params?.pipeline as
    | { image?: PipelineMedia; video?: PipelineMedia }
    | undefined
}

export function isMotionVariantFormat(format: string | undefined) {
  return format === 'video' || format === 'reel'
}

export function getVariantPreviewUrls(variant: Variant) {
  const pipeline = getVariantPipeline(variant)
  const image = pipeline?.image
  const video = pipeline?.video
  const cacheKey = variant.updated_at || variant.id
  const motionFormat = isMotionVariantFormat(variant.format)

  const imageReady =
    Boolean(image?.url) &&
    (!image?.status || image.status === 'done' || image.status === 'mock')
  const videoReady =
    Boolean(video?.url) &&
    (!video?.status || video.status === 'done' || video.status === 'mock')

  const videoFailed =
    video?.status === 'failed' ||
    Boolean(video?.error) ||
    (motionFormat && !videoReady && video?.status !== 'skipped')

  const isGenerating =
    variant.status === 'GENERATING' || variant.status === 'PENDING'

  /** Reel/video with no playable file — show failure UI (not a blank white tile). */
  const missingMotionMedia = motionFormat && !videoReady && !isGenerating

  const isMaster30 =
    video?.production === 'master_30s' ||
    (variant.generation_params?.models as { video_production?: string } | undefined)
      ?.video_production === 'master_30s'

  const hasVoiceover = video?.voiceover?.status === 'done'
  const subtitlesMissing =
    motionFormat && videoReady && video?.subtitles_applied === false
  const logoMissing = motionFormat && videoReady && video?.logo_applied === false

  // Reel/video: never use a static frame as the preview when the video step failed.
  const previewImageUrl =
    imageReady && (!motionFormat || !videoFailed)
      ? assetUrl(image?.url, cacheKey)
      : null
  const previewVideoUrl = videoReady ? assetUrl(video?.url, cacheKey) : null

  return {
    image,
    video,
    imageUrl: previewImageUrl,
    videoUrl: previewVideoUrl,
    imageFailed:
      image?.status === 'failed' &&
      !(motionFormat && videoReady) &&
      image?.status !== 'skipped',
    imageError: image?.error,
    imageSkipped: image?.status === 'skipped',
    videoFailed,
    missingMotionMedia,
    videoError: video?.error || video?.voiceover?.error,
    hasVoiceover,
    subtitlesMissing,
    subtitleWarning: video?.subtitle_warning,
    logoMissing,
    logoWarning: video?.logo_warning,
    isMaster30,
    isGenerating,
  }
}

/** Short, user-facing message when video generation failed (e.g. HeyGen credits). */
export function formatVideoErrorMessage(raw: string | undefined | null): string | null {
  if (!raw?.trim()) return null
  const text = raw.trim()
  try {
    const parsed = JSON.parse(text) as {
      error?: { message?: string; code?: string }
      message?: string
    }
    const msg = parsed?.error?.message || parsed?.message
    if (msg) return msg
  } catch {
    const inner = text.match(/"message"\s*:\s*"([^"]+)"/)
    if (inner?.[1]) return inner[1]
  }
  if (text.includes('Insufficient API credits') || text.includes('insufficient_credit')) {
    return 'HeyGen API credits are empty. Add API credits in HeyGen (Settings → API), not only web app credits.'
  }
  if (
    text.includes('timed out') ||
    text.includes('still rendering')
  ) {
    return (
      'HeyGen is still rendering (can take 15–35 min for a 30s Video Agent ad). ' +
      'Wait, then generate once more — avoid clicking Generate repeatedly.'
    )
  }
  if (
    text.includes('connection attempts failed') ||
    text.includes('Could not reach HeyGen') ||
    text.includes('network connection failed')
  ) {
    return (
      'Could not reach HeyGen (network). Check internet/VPN/firewall, ensure api.heygen.com is reachable, ' +
      'restart the backend, then regenerate — the server retries automatically.'
    )
  }
  if (text.includes('not enough credits') && text.toLowerCase().includes('runway')) {
    return 'Runway image credits are empty. Add Runway credits or switch Image model in generation settings, then regenerate.'
  }
  if (text.includes('ffmpeg') || text.includes('imageio-ffmpeg')) {
    return (
      'Logo and captions are added after HeyGen finishes, using ffmpeg. ' +
      'In the backend folder run: pip install imageio-ffmpeg — then restart the server and regenerate.'
    )
  }
  return text.length > 160 ? `${text.slice(0, 157)}…` : text
}
