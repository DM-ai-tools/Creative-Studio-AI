/** Section 2 display labels — UI copy only; routes and API names unchanged. */

export const UI = {
  projects: 'Projects',
  newProject: 'New project',
  createProject: 'New project',
  creativeLibrary: 'Creative library',
  generationHistory: 'Generation history',
  brandContentChecks: 'Brand & content checks',
  usageAndCosts: 'Usage & costs',
  imageAdFromPhoto: 'Image ad from photo',
  aiAssistant: 'AI assistant',
  numberOfCreatives: 'Number of creatives',
  productOrService: 'Product or service',
  draftScriptForAudience: 'Draft script for this audience',
  supportingScenes: 'Supporting scenes',
  suggestAdCopy: 'Suggest ad copy',
  saveToCreativeLibrary: 'Save to creative library',
  openCreativeLibrary: 'Open creative library',
  addTextToImage: 'Add text to your image',
  generating: 'Generating',
  partiallyCompleted: 'Partially completed',
  creatives: 'creatives',
  creative: 'creative',
} as const

export function partialStatusLabel(completed: number, total: number): string {
  if (total > 0) {
    return `${UI.partiallyCompleted} · ${completed} of ${total} ready`
  }
  return UI.partiallyCompleted
}

const _STATUS_LABELS: Record<string, string> = {
  READY: 'Ready',
  RUNNING: UI.generating,
  GENERATING: UI.generating,
  PENDING: 'Pending',
  PARTIAL: UI.partiallyCompleted,
  FAILED: 'Failed',
  EXPORTED: 'Exported',
  DRAFT: 'Draft',
}

export function briefStatusLabel(
  status: string,
  completed = 0,
  total = 0,
): string {
  if (status === 'PARTIAL') {
    return partialStatusLabel(completed, total)
  }
  return _STATUS_LABELS[status] ?? status
}
