'use client'

import React, { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Card from '@/components/ui/Card'
import { adminApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import type { PricingConfig, PricingRates } from '@/types'

const RESOLUTIONS = ['480p', '720p', '1080p', '2160p'] as const

const FAMILY_LABELS: Record<string, string> = {
  '2.5': 'Seedance 2.5',
  '2.5-flash': 'Seedance 2.5 Flash',
  '2.0': 'Seedance 2.0',
  '2.0-fast': 'Seedance 2.0 Fast',
  '2.0-mini': 'Seedance 2.0 Mini',
  '1.0-pro': 'Seedance 1.0 Pro',
  '1.0-pro-fast': 'Seedance 1.0 Pro Fast',
}
const FAMILY_MODEL_IDS: Record<string, string> = {
  '2.5': 'dreamina-seedance-2-5-260628',
  '2.0': 'dreamina-seedance-2-0-260128',
}
const MAIN_FAMILIES = ['2.5', '2.0']
/** Resolutions BytePlus supports per model. 4K exists only on Seedance 2.0. */
const SUPPORTED: Record<string, readonly string[]> = {
  '2.5': ['480p', '720p', '1080p'],
  '2.0': ['480p', '720p', '1080p', '2160p'],
}
const DEFAULT_SUPPORTED = ['480p', '720p']
const RES_LABEL: Record<string, string> = {
  '480p': '480p',
  '720p': '720p',
  '1080p': '1080p (Full HD)',
  '2160p': '2160p (4K)',
}
/** Tokens per second of 16:9 video at 24 fps: width × height × 24 / 1024. */
const TOKENS_PER_SECOND: Record<string, number> = {
  '480p': (864 * 496 * 24) / 1024,
  '720p': (1280 * 720 * 24) / 1024,
  '1080p': (1920 * 1080 * 24) / 1024,
  '2160p': (3840 * 2160 * 24) / 1024,
}

/** Same matching rules as the backend (`seedance_family`). */
function familyOfModel(model: string): string {
  const t = model.toLowerCase()
  const markers: [string, string][] = [
    ['2-5-flash', '2.5-flash'], ['2.5-flash', '2.5-flash'],
    ['2-0-fast', '2.0-fast'], ['2.0-fast', '2.0-fast'],
    ['2-0-mini', '2.0-mini'], ['2.0-mini', '2.0-mini'],
    ['1-0-pro-fast', '1.0-pro-fast'], ['1.0-pro-fast', '1.0-pro-fast'],
    ['1-0-pro', '1.0-pro'], ['1.0-pro', '1.0-pro'],
    ['2-5', '2.5'], ['2.5', '2.5'], ['2-0', '2.0'], ['2.0', '2.0'],
  ]
  for (const [marker, family] of markers) if (t.includes(marker)) return family
  return '2.5'
}

const usd = (n: number) =>
  n >= 1 ? `$${n.toFixed(2)}` : `$${n.toFixed(4).replace(/0+$/, '').replace(/\.$/, '')}`
const tokenLabel = (n: number) =>
  n >= 1_000_000 ? `${(n / 1_000_000).toFixed(2)}M` : n >= 1_000 ? `${(n / 1_000).toFixed(1)}k` : String(n)

type SeedanceUsageRow = { model: string; clips: number; failed: number; tokens: number; cost_usd: number }

const inputClass =
  'w-24 rounded-md border border-border px-2 py-1 text-xs text-charcoal bg-white tabular-nums disabled:bg-light disabled:text-lt'
const thClass =
  'text-left px-3 py-2 text-[10px] font-bold text-mid uppercase tracking-wide border-b border-border'
const tdClass = 'px-3 py-2 text-mid'

type Props = {
  /** Called after a save so the spend figures on the page can be re-read. */
  onSaved?: () => void
  /** Seedance usage per model for the selected period, shown as each model's total. */
  seedanceUsage?: SeedanceUsageRow[]
  periodLabel?: string
}

/** Admin view of every price behind the estimated USD figures. */
export default function PricingEditor({ onSaved, seedanceUsage = [], periodLabel = '' }: Props) {
  const [config, setConfig] = useState<PricingConfig | null>(null)
  const [draft, setDraft] = useState<PricingRates | null>(null)
  const [saving, setSaving] = useState(false)
  const [newLlm, setNewLlm] = useState('')
  const [newImage, setNewImage] = useState('')

  const load = async () => {
    try {
      const data = await adminApi.getPricing()
      setConfig(data)
      setDraft(structuredClone(data.effective))
    } catch (err) {
      toast.error(extractApiError(err, 'Could not load pricing'))
    }
  }

  useEffect(() => {
    void load()
  }, [])

  if (!config || !draft) {
    return (
      <Card title="Pricing rates">
        <p className="text-xs text-muted">Loading prices…</p>
      </Card>
    )
  }

  // The previous API shape keyed Seedance prices by resolution ("480p", ...) instead of by model.
  const looksLikeOldBackend = Object.keys(draft.seedance_per_m_tokens).some((k) => /p$/.test(k))
  if (looksLikeOldBackend) {
    return (
      <Card title="Pricing rates">
        <p className="text-sm text-red-700">
          The backend is still running the previous version, so the Seedance prices cannot be shown.
          Restart the backend, then refresh this page.
        </p>
      </Card>
    )
  }

  const canEdit = config.can_edit
  const num = (value: string) => (value === '' ? 0 : Number(value))

  const setSeedance = (family: string, res: string, kind: 'no_video' | 'with_video', value: string) =>
    setDraft({
      ...draft,
      seedance_per_m_tokens: {
        ...draft.seedance_per_m_tokens,
        [family]: {
          ...draft.seedance_per_m_tokens[family],
          [res]: { ...draft.seedance_per_m_tokens[family][res], [kind]: num(value) },
        },
      },
    })

  const setLlm = (model: string, kind: 'input' | 'output', value: string) =>
    setDraft({
      ...draft,
      llm_per_m_tokens: {
        ...draft.llm_per_m_tokens,
        [model]: { ...draft.llm_per_m_tokens[model], [kind]: num(value) },
      },
    })

  const removeLlm = (model: string) => {
    const next = { ...draft.llm_per_m_tokens }
    delete next[model]
    setDraft({ ...draft, llm_per_m_tokens: next })
  }

  // Send only what differs from the defaults so future default updates still apply.
  const buildOverrides = (): Partial<PricingRates> => {
    const out: Partial<PricingRates> = {}
    const d = config.defaults
    const seedance: PricingRates['seedance_per_m_tokens'] = {}
    for (const family of Object.keys(draft.seedance_per_m_tokens)) {
      for (const res of RESOLUTIONS) {
        for (const kind of ['no_video', 'with_video'] as const) {
          const now = draft.seedance_per_m_tokens[family]?.[res]?.[kind]
          if (now !== d.seedance_per_m_tokens[family]?.[res]?.[kind]) {
            seedance[family] ??= {}
            seedance[family][res] = { ...(seedance[family][res] ?? ({} as never)), [kind]: now }
          }
        }
      }
    }
    if (Object.keys(seedance).length) out.seedance_per_m_tokens = seedance
    if (draft.seedance_fallback_usd_per_30s !== d.seedance_fallback_usd_per_30s) {
      out.seedance_fallback_usd_per_30s = draft.seedance_fallback_usd_per_30s
    }
    const llm: PricingRates['llm_per_m_tokens'] = {}
    for (const [model, rates] of Object.entries(draft.llm_per_m_tokens)) {
      const base = d.llm_per_m_tokens[model]
      if (!base || base.input !== rates.input || base.output !== rates.output) llm[model] = rates
    }
    if (Object.keys(llm).length) out.llm_per_m_tokens = llm
    if (
      draft.llm_default_per_m_tokens.input !== d.llm_default_per_m_tokens.input ||
      draft.llm_default_per_m_tokens.output !== d.llm_default_per_m_tokens.output
    ) {
      out.llm_default_per_m_tokens = draft.llm_default_per_m_tokens
    }
    if (Object.keys(draft.image_usd_each).length) out.image_usd_each = draft.image_usd_each
    return out
  }

  const save = async (overrides: Partial<PricingRates>, message: string) => {
    setSaving(true)
    try {
      const data = await adminApi.savePricing(overrides)
      setConfig(data)
      setDraft(structuredClone(data.effective))
      toast.success(message)
      onSaved?.()
    } catch (err) {
      toast.error(extractApiError(err, 'Could not save pricing'))
    } finally {
      setSaving(false)
    }
  }

  const customised = Object.keys(config.overrides ?? {}).length > 0

  const usageByFamily: Record<string, { clips: number; tokens: number; cost: number }> = {}
  for (const row of seedanceUsage) {
    const family = familyOfModel(row.model)
    const slot = (usageByFamily[family] ??= { clips: 0, tokens: 0, cost: 0 })
    slot.clips += row.clips
    slot.tokens += row.tokens
    slot.cost += row.cost_usd
  }
  const usageTotal = Object.values(usageByFamily).reduce((sum, v) => sum + v.cost, 0)
  const otherFamilies = Object.keys(draft.seedance_per_m_tokens).filter((f) => !MAIN_FAMILIES.includes(f))

  const modelPanel = (family: string) => {
    const rates = draft.seedance_per_m_tokens[family]
    if (!rates) return null
    const resolutions = SUPPORTED[family] ?? DEFAULT_SUPPORTED
    const used = usageByFamily[family]
    return (
      <div key={family} className="rounded-xl border border-border bg-white overflow-hidden">
        <div className="px-4 py-3 bg-light flex flex-wrap items-baseline justify-between gap-2">
          <div>
            <div className="text-sm font-extrabold text-navy">{FAMILY_LABELS[family] ?? family}</div>
            {FAMILY_MODEL_IDS[family] && (
              <div className="text-[11px] font-mono text-muted">{FAMILY_MODEL_IDS[family]}</div>
            )}
          </div>
          {!SUPPORTED[family] && <div className="text-[11px] text-muted">480p / 720p only</div>}
        </div>
        <table className="w-full text-xs">
          <thead>
            <tr>
              {['Resolution', '≈ per second of video', 'No reference video', 'With reference video'].map((h) => (
                <th key={h} className={thClass}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {resolutions.map((res) => (
              <tr key={res} className="border-b border-border">
                <td className={`${tdClass} font-semibold text-navy whitespace-nowrap`}>{RES_LABEL[res] ?? res}</td>
                <td className={`${tdClass} tabular-nums`}>
                  {usd((TOKENS_PER_SECOND[res] / 1_000_000) * (rates[res]?.no_video ?? 0))}/s
                </td>
                {(['no_video', 'with_video'] as const).map((kind) => (
                  <td key={kind} className={tdClass}>
                    $
                    <input
                      type="number" min={0} step="0.01" disabled={!canEdit}
                      className={`${inputClass} ml-1`}
                      value={rates[res]?.[kind] ?? 0}
                      onChange={(e) => setSeedance(family, res, kind, e.target.value)}
                    />
                    <span className="ml-1 text-muted">/ 1M</span>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-4 py-3 bg-light/60 text-xs text-mid">
          {used ? (
            <>
              <span className="font-semibold text-navy">Your total{periodLabel ? ` (${periodLabel})` : ''}:</span>{' '}
              {used.clips} clips · {tokenLabel(used.tokens)} tokens ·{' '}
              <span className="font-extrabold text-navy">~{usd(used.cost)}</span>
            </>
          ) : (
            <span className="text-muted">No clips with this model in this period.</span>
          )}
        </div>
      </div>
    )
  }

  return (
    <Card
      title="Pricing rates"
      subtitle="Every estimated USD figure is tokens × these rates. Changes apply to Seedance spend everywhere straight away, and to new LLM and image calls going forward."
      action={
        canEdit ? (
          <div className="flex gap-2">
            <Button size="sm" variant="secondary" disabled={saving || !customised} onClick={() => save({}, 'Restored default prices')}>
              Restore defaults
            </Button>
            <Button size="sm" disabled={saving} onClick={() => save(buildOverrides(), 'Pricing saved')}>
              {saving ? 'Saving…' : 'Save pricing'}
            </Button>
          </div>
        ) : undefined
      }
    >
      {!canEdit && (
        <p className="text-xs text-muted mb-3">Only the platform admin can change prices. You can view them here.</p>
      )}

      <div className="space-y-6">
        <section>
          <h4 className="text-xs font-bold text-navy mb-1">Seedance — USD per 1M completion tokens</h4>
          <p className="text-xs text-muted mb-2">
            Defaults are the official BytePlus online-inference prices. The price depends on the model, the resolution, and
            whether a reference <em>video</em> was an input (images do not count). BytePlus bills only successfully generated videos.
          </p>
          <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4">
            {MAIN_FAMILIES.map((family) => modelPanel(family))}
          </div>
          <div className="mt-3 rounded-xl bg-light/60 px-4 py-2.5 text-xs text-mid">
            <span className="font-semibold text-navy">All Seedance models{periodLabel ? ` (${periodLabel})` : ''}:</span>{' '}
            <span className="font-extrabold text-navy">~{usd(usageTotal)}</span>
            <span className="text-muted"> — the sum of the model totals above.</span>
          </div>
          {otherFamilies.length > 0 && (
            <details className="mt-3">
              <summary className="cursor-pointer text-xs font-semibold text-navy">
                Other Seedance models ({otherFamilies.length})
              </summary>
              <div className="grid grid-cols-1 2xl:grid-cols-2 gap-4 mt-3">
                {otherFamilies.map((family) => modelPanel(family))}
              </div>
            </details>
          )}
          <label className="flex items-center gap-2 text-xs text-mid mt-3">
            Fallback when a clip has no token count — USD per 30s:
            <input
              type="number" min={0} step="0.5" disabled={!canEdit} className={inputClass}
              value={draft.seedance_fallback_usd_per_30s}
              onChange={(e) => setDraft({ ...draft, seedance_fallback_usd_per_30s: num(e.target.value) })}
            />
          </label>
        </section>

        <section>
          <h4 className="text-xs font-bold text-navy mb-1">LLM models — USD per 1M tokens</h4>
          <p className="text-xs text-muted mb-2">
            Used only when OpenRouter does not return the real cost. Models not listed use the default row.
          </p>
          <table className="text-xs">
            <thead>
              <tr>
                {['Model', 'Input', 'Output', ''].map((h) => (
                  <th key={h || 'x'} className={thClass}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {Object.entries(draft.llm_per_m_tokens).map(([model, rates]) => (
                <tr key={model} className="border-b border-border">
                  <td className={`${tdClass} font-mono text-[11px] text-navy`}>{model}</td>
                  {(['input', 'output'] as const).map((kind) => (
                    <td key={kind} className={tdClass}>
                      $
                      <input
                        type="number" min={0} step="0.01" disabled={!canEdit}
                        className={`${inputClass} ml-1`}
                        value={rates[kind]}
                        onChange={(e) => setLlm(model, kind, e.target.value)}
                      />
                    </td>
                  ))}
                  <td className={tdClass}>
                    {canEdit && !config.defaults.llm_per_m_tokens[model] && (
                      <button type="button" className="text-red-600 underline" onClick={() => removeLlm(model)}>
                        Remove
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              <tr className="border-b border-border">
                <td className={`${tdClass} font-semibold text-navy`}>Default (unlisted models)</td>
                {(['input', 'output'] as const).map((kind) => (
                  <td key={kind} className={tdClass}>
                    $
                    <input
                      type="number" min={0} step="0.01" disabled={!canEdit}
                      className={`${inputClass} ml-1`}
                      value={draft.llm_default_per_m_tokens[kind]}
                      onChange={(e) =>
                        setDraft({
                          ...draft,
                          llm_default_per_m_tokens: { ...draft.llm_default_per_m_tokens, [kind]: num(e.target.value) },
                        })
                      }
                    />
                  </td>
                ))}
                <td />
              </tr>
            </tbody>
          </table>
          {canEdit && (
            <div className="flex items-center gap-2 mt-2">
              <input
                className="rounded-md border border-border px-2 py-1 text-xs w-72 bg-white"
                placeholder="provider/model-id, e.g. anthropic/claude-sonnet-4.6"
                value={newLlm}
                onChange={(e) => setNewLlm(e.target.value)}
              />
              <Button
                size="sm" variant="secondary" disabled={!newLlm.trim()}
                onClick={() => {
                  const key = newLlm.trim().toLowerCase()
                  setDraft({
                    ...draft,
                    llm_per_m_tokens: { ...draft.llm_per_m_tokens, [key]: draft.llm_per_m_tokens[key] ?? { input: 0, output: 0 } },
                  })
                  setNewLlm('')
                }}
              >
                Add model
              </Button>
            </div>
          )}
        </section>

        <section>
          <h4 className="text-xs font-bold text-navy mb-1">OpenAI images — USD per image (optional override)</h4>
          <p className="text-xs text-muted mb-2">
            Leave empty to use the built-in price for each image model.
          </p>
          {Object.keys(draft.image_usd_each).length > 0 && (
            <table className="text-xs mb-2">
              <tbody>
                {Object.entries(draft.image_usd_each).map(([model, price]) => (
                  <tr key={model} className="border-b border-border">
                    <td className={`${tdClass} font-mono text-[11px] text-navy`}>{model}</td>
                    <td className={tdClass}>
                      $
                      <input
                        type="number" min={0} step="0.001" disabled={!canEdit}
                        className={`${inputClass} ml-1`}
                        value={price}
                        onChange={(e) =>
                          setDraft({ ...draft, image_usd_each: { ...draft.image_usd_each, [model]: num(e.target.value) } })
                        }
                      />
                    </td>
                    <td className={tdClass}>
                      {canEdit && (
                        <button
                          type="button" className="text-red-600 underline"
                          onClick={() => {
                            const next = { ...draft.image_usd_each }
                            delete next[model]
                            setDraft({ ...draft, image_usd_each: next })
                          }}
                        >
                          Remove
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {canEdit && (
            <div className="flex items-center gap-2">
              <input
                className="rounded-md border border-border px-2 py-1 text-xs w-72 bg-white"
                placeholder="image model id, e.g. gpt-image-2"
                value={newImage}
                onChange={(e) => setNewImage(e.target.value)}
              />
              <Button
                size="sm" variant="secondary" disabled={!newImage.trim()}
                onClick={() => {
                  const key = newImage.trim().toLowerCase()
                  setDraft({ ...draft, image_usd_each: { ...draft.image_usd_each, [key]: draft.image_usd_each[key] ?? 0 } })
                  setNewImage('')
                }}
              >
                Add image price
              </Button>
            </div>
          )}
        </section>
      </div>
    </Card>
  )
}
