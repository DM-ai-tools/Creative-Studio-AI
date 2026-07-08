/** Heuristic: creative-brief / writer directions (step 5), not HeyGen dialogue. */
export function looksLikeCreativeBrief(text: string): boolean {
  const t = text.trim()
  if (!t) return false
  return (
    /\b(Open with a direct hook|Establish credibility|Position this as a common|Provide actionable insights|Keep the tone consultative|what the ad should say|scriptwriters?|talking points)\b/i.test(
      t
    ) ||
    (/\b(Close with a professional call-to-action that invites)\b/i.test(t) &&
      !/\[\d{1,2}:\d{2}\s*[-–]/.test(t))
  )
}

export function hasTimedScriptLines(text: string): boolean {
  return /\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]/.test(text)
}

export function spokenTextFromTimedScript(text: string): string {
  return text
    .replace(/\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
}

/** Read "Duration: 60-75 seconds" (or similar) from a pasted writer script. */
export function inferTargetSecondsFromSourceScript(
  text: string,
  fallbackSeconds: number
): number {
  const range = text.match(/duration:\s*(\d+)\s*[-–]\s*(\d+)\s*seconds?/i)
  if (range) {
    const hi = Math.max(parseInt(range[1], 10), parseInt(range[2], 10))
    if (hi >= 5 && hi <= 240) return hi
  }
  const single = text.match(/duration:\s*(\d+)\s*seconds?/i)
  if (single) {
    const n = parseInt(single[1], 10)
    if (n >= 5 && n <= 240) return n
  }
  return fallbackSeconds
}

/** Video setting wins when user picked 1:30 but script says 60–75s, etc. */
export function resolveTargetSecondsForConversion(
  sourceScript: string,
  videoSettingSeconds: number
): number {
  const inferred = inferTargetSecondsFromSourceScript(sourceScript, videoSettingSeconds)
  return Math.max(inferred, videoSettingSeconds)
}

export function isPlaceholderScriptResult(result: {
  model_id?: string
  full_script?: string
  word_count?: number
  estimated_seconds?: number
}): boolean {
  if (result.model_id === 'mock') return true
  const text = (result.full_script || '').toLowerCase()
  if (/quick one about/.test(text) && (result.word_count ?? 0) < 80) return true
  return false
}
