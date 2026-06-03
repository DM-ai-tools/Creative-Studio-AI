import type { SelectOption, SelectOptionGroup } from '@/components/ui/Select'
import type { GenerationModelOption } from '@/types'

const PROVIDER_LABELS: Record<string, string> = {
  runway: 'Runway',
  heygen: 'HeyGen',
  higgsfield: 'Higgsfield',
  other: 'Other',
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
    list.push({ value: m.id, label: m.label })
    byProvider.set(key, list)
  }
  if (byProvider.size <= 1) {
    return {
      options: models.map((m) => ({ value: m.id, label: m.label })),
      groups: undefined,
    }
  }
  const groups: SelectOptionGroup[] = [...byProvider.entries()].map(([provider, options]) => ({
    label: PROVIDER_LABELS[provider] ?? provider,
    options,
  }))
  return { options: [], groups }
}
