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
