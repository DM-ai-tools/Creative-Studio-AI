import type { BriefStatus, GenerationCatalog, Variant } from '@/types'

type NodeState = 'done' | 'run' | 'pend' | 'fail'

function pipelineStatus(status?: string): boolean {
  return status === 'done' || status === 'mock'
}

export function getPipelineNodeStates(
  briefStatus: BriefStatus,
  steps: string[],
  variants: Variant[],
  total: number
): NodeState[] {
  if (!steps.length) return []

  const imageDone = variants.filter((variant) => {
    const pipeline = variant.generation_params?.pipeline as { image?: { status?: string } } | undefined
    return pipelineStatus(pipeline?.image?.status)
  }).length

  const videoDone = variants.filter((variant) => {
    const pipeline = variant.generation_params?.pipeline as { video?: { status?: string } } | undefined
    return pipelineStatus(pipeline?.video?.status)
  }).length

  const copyDone = variants.filter((variant) => {
    const pipeline = variant.generation_params?.pipeline as { copy?: { status?: string } } | undefined
    return pipelineStatus(pipeline?.copy?.status) || Boolean(variant.hook)
  }).length

  const complianceDone = variants.filter((variant) => variant.compliance_status === 'PASSED').length
  const readyCount = variants.filter((variant) => variant.status === 'READY' || variant.status === 'APPROVED').length
  const target = total || variants.length || 1

  if (briefStatus === 'FAILED') {
    const failedIndex = Math.max(0, steps.findIndex((step) => step.toLowerCase().includes('compliance')))
    return steps.map((_, index) => {
      if (index < failedIndex) return 'done'
      if (index === failedIndex) return 'fail'
      return 'pend'
    })
  }

  if (briefStatus === 'DRAFT' || briefStatus === 'PENDING') {
    return steps.map((_, index) => (index === 0 && briefStatus === 'PENDING' ? 'run' : 'pend'))
  }

  if (briefStatus === 'READY' || briefStatus === 'EXPORTED') {
    return steps.map(() => 'done')
  }

  return steps.map((step) => {
    const key = step.toLowerCase()
    if (key.includes('plan')) return briefStatus === 'RUNNING' ? 'done' : 'pend'
    if (key.includes('hook')) return copyDone > 0 ? 'done' : briefStatus === 'RUNNING' ? 'run' : 'pend'
    if (key.includes('copy')) return copyDone >= target ? 'done' : copyDone > 0 ? 'run' : 'pend'
    if (key.includes('image')) {
      if (imageDone >= target) return 'done'
      if (imageDone > 0 || briefStatus === 'RUNNING') return 'run'
      return 'pend'
    }
    if (key.includes('video')) {
      if (videoDone >= target) return 'done'
      if (videoDone > 0 || briefStatus === 'RUNNING') return 'run'
      return 'pend'
    }
    if (key.includes('caption') || key.includes('compose')) {
      if (readyCount >= target) return 'done'
      if (readyCount > 0) return 'run'
      return 'pend'
    }
    if (key.includes('compliance')) {
      if (complianceDone >= target) return 'done'
      if (complianceDone > 0) return 'run'
      return 'pend'
    }
    if (key.includes('persist')) return readyCount >= target ? 'done' : 'pend'
    return 'pend'
  })
}

export function buildPipelineTasks(
  catalog: GenerationCatalog | undefined,
  variants: Variant[],
  total: number
) {
  const copyModel = catalog?.copy_models[0]
  const imageModel = catalog?.image_models[0]
  const videoModel = catalog?.video_models[0]
  const target = total || variants.length || 0
  const imageDone = variants.filter((variant) => {
    const pipeline = variant.generation_params?.pipeline as { image?: { status?: string } } | undefined
    return pipelineStatus(pipeline?.image?.status)
  }).length
  const videoDone = variants.filter((variant) => {
    const pipeline = variant.generation_params?.pipeline as { video?: { status?: string } } | undefined
    return pipelineStatus(pipeline?.video?.status)
  }).length
  const complianceDone = variants.filter((variant) => variant.compliance_status === 'PASSED').length

  return [
    { task: 'Plan', provider: copyModel?.label ?? 'Copy model', status: target ? 'Done' : 'Pending', progress: target ? '1/1' : '0/1', cost: '—', latency: '—' },
    { task: 'Hook Gen', provider: copyModel?.label ?? 'Copy model', status: variants.length ? 'Done' : 'Pending', progress: `${Math.min(variants.length, target)}/${target || '—'}`, cost: '—', latency: '—' },
    { task: 'Copy Gen', provider: copyModel?.label ?? 'Copy model', status: variants.length ? 'Done' : 'Pending', progress: `${Math.min(variants.length, target)}/${target || '—'}`, cost: '—', latency: '—' },
    { task: 'Image Gen', provider: imageModel?.label ?? 'Image model', status: imageDone >= target && target ? 'Done' : imageDone ? 'Running' : 'Pending', progress: `${imageDone}/${target || '—'}`, cost: '—', latency: '—' },
    { task: 'Video Gen', provider: videoModel?.label ?? 'Video model', status: videoDone >= target && target ? 'Done' : videoDone ? 'Running' : 'Pending', progress: `${videoDone}/${target || '—'}`, cost: '—', latency: '—' },
    { task: 'Compliance', provider: 'compliance-svc', status: complianceDone >= target && target ? 'Done' : complianceDone ? 'Running' : 'Pending', progress: `${complianceDone}/${target || '—'}`, cost: '—', latency: '—' },
  ]
}

export function buildHookRows(variants: Variant[]) {
  return variants.map((variant, index) => {
    const params = variant.generation_params as { hook_framework?: string } | undefined
    return {
      index: index + 1,
      hook: variant.hook,
      framework: params?.hook_framework ?? '—',
      score: variant.performance_score ?? null,
      selected: variant.status !== 'REJECTED',
    }
  })
}
