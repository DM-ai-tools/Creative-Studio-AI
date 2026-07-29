import type { SelectOption, SelectOptionGroup } from '@/components/ui/Select'
import type { GenerationModelOption } from '@/types'

const PROVIDER_LABELS: Record<string, string> = {
  runway: 'Runway',
  heygen: 'HeyGen',
  higgsfield: 'Higgsfield',
  other: 'Other',
}

function modelOptionLabel(m: GenerationModelOption): string {
  if (typeof m.cost_usd !== 'number') return m.label
  if (m.cost_unit === 'second') return `${m.label} · $${m.cost_usd.toFixed(2)}/s`
  return `${m.label} · $${m.cost_usd.toFixed(2)}/img`
}

/** Group catalog models by provider for optgroup selects (Runway / HeyGen / Higgsfield). */
export function buildModelSelectGroups(
  models: GenerationModelOption[] | undefined,
  fallback: SelectOption[]
): { options: SelectOption[]; groups: SelectOptionGroup[] | undefined } {
  if (!models?.length) {
    return { options: fallback, groups: undefined }
  }
  const byProvider = new Map<string, SelectOption[]>()
  for (const m of models) {
    const key = m.provider || 'other'
    const list = byProvider.get(key) ?? []
    list.push({ value: m.id, label: modelOptionLabel(m) })
    byProvider.set(key, list)
  }
  if (byProvider.size <= 1) {
    return {
      options: models.map((m) => ({ value: m.id, label: modelOptionLabel(m) })),
      groups: undefined,
    }
  }
  const groups: SelectOptionGroup[] = Array.from(byProvider.entries()).map(([provider, options]) => ({
    label: PROVIDER_LABELS[provider] ?? provider,
    options,
  }))
  // Keep empty option from fallback if present (e.g. "Choose image model…")
  const empty = fallback.find((o) => o.value === '')
  return { options: empty ? [empty] : [], groups }
}
