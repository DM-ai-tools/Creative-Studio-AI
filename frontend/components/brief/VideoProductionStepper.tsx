'use client'

export type ProductionStepId = 'script' | 'broll' | 'avatar' | 'review'

const STEPS: { id: ProductionStepId; label: string; hint: string }[] = [
  {
    id: 'script',
    label: '1. Voice script',
    hint: 'Upload stats → generate spoken script with proof beats aligned to your numbers',
  },
  {
    id: 'broll',
    label: '2. B-roll scenes',
    hint: 'Scene map generated from your approved script — same timestamps',
  },
  {
    id: 'avatar',
    label: '3. Avatar & settings',
    hint: 'Presenter, voice, duration, captions, logo',
  },
  {
    id: 'review',
    label: '4. Review & generate',
    hint: 'Confirm script + scenes + settings, then generate video',
  },
]

function stepIndex(id: ProductionStepId): number {
  return STEPS.findIndex((s) => s.id === id)
}

export function productionStepFromState(opts: {
  scriptApproved: boolean
  brollReady: boolean
  avatarReady: boolean
}): ProductionStepId {
  if (!opts.scriptApproved) return 'script'
  if (!opts.brollReady) return 'broll'
  if (!opts.avatarReady) return 'avatar'
  return 'review'
}

export default function VideoProductionStepper({
  activeStep,
  scriptApproved,
  brollReady,
  avatarReady,
}: {
  activeStep: ProductionStepId
  scriptApproved: boolean
  brollReady: boolean
  avatarReady: boolean
}) {
  const activeIdx = stepIndex(activeStep)

  return (
    <div className="rounded-xl border border-sky-200 bg-gradient-to-r from-sky-50 to-white p-4 mb-4">
      <p className="text-xs font-bold text-sky-900 uppercase tracking-wide mb-3">
        Video production pipeline
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2">
        {STEPS.map((step, i) => {
          const done =
            (step.id === 'script' && scriptApproved) ||
            (step.id === 'broll' && brollReady) ||
            (step.id === 'avatar' && avatarReady) ||
            (step.id === 'review' && scriptApproved && brollReady && avatarReady)
          const current = i === activeIdx
          return (
            <div
              key={step.id}
              className={`rounded-lg border px-3 py-2 text-xs ${
                current
                  ? 'border-sky-500 bg-sky-100 ring-1 ring-sky-400'
                  : done
                    ? 'border-emerald-300 bg-emerald-50'
                    : 'border-border bg-white text-muted'
              }`}
            >
              <p className={`font-bold ${current ? 'text-sky-900' : done ? 'text-emerald-800' : 'text-charcoal'}`}>
                {done && !current ? '✓ ' : ''}
                {step.label}
              </p>
              <p className="mt-0.5 text-[10px] leading-snug opacity-90">{step.hint}</p>
            </div>
          )
        })}
      </div>
    </div>
  )
}
