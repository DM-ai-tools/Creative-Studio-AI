import type { CatalogOption, GenerationCatalog } from '@/types'

/** Public HeyGen look id — Vespri (from app.heygen.com avatars/looks/public). */
export const HEYGEN_VESPRI_AVATAR_ID = '25777ee579284b9d9081bc95c49c5f00'

export const HEYGEN_VESPRI_AVATAR: CatalogOption = {
  id: HEYGEN_VESPRI_AVATAR_ID,
  label: 'Vespri (Female)',
  gender: 'female',
}

/** Standalone avatars (one id = one look). Pose libraries use "Parent — Pose" labels. */
export function splitHeyGenAvatarOptions(options: CatalogOption[]) {
  const featured = options.filter((o) => !o.label.includes(' — '))
  const poses = options.filter((o) => o.label.includes(' — '))
  return { featured, poses }
}

export function isVespriLabel(label: string): boolean {
  return label.toLowerCase().includes('vespri')
}

export function isVespriPoseOption(option: CatalogOption): boolean {
  const parent = option.label.split(' — ')[0]?.trim() || option.label
  return isVespriLabel(parent)
}

export function findVespriAvatar(options: CatalogOption[]): CatalogOption | undefined {
  const vespri = options.filter((o) => isVespriLabel(o.label))
  if (!vespri.length) return undefined
  const position1Portrait = vespri.find((o) =>
    /position\s*1.*portrait/i.test(o.label)
  )
  if (position1Portrait) return position1Portrait
  const anyPortrait = vespri.find((o) => /portrait/i.test(o.label))
  if (anyPortrait) return anyPortrait
  const byGroupId = vespri.find((o) => o.id === HEYGEN_VESPRI_AVATAR_ID)
  return byGroupId || vespri[0]
}

/** Fallback single Vespri group id when API expansion is unavailable. */
export function normalizeVespriInList(options: CatalogOption[]): CatalogOption[] {
  const withoutDupes = options.filter(
    (o) => !isVespriLabel(o.label) && o.id !== HEYGEN_VESPRI_AVATAR_ID
  )
  return [HEYGEN_VESPRI_AVATAR, ...withoutDupes]
}

/** Featured looks first (Vespri guaranteed), then pose library for dropdowns. */
export function resolveHeyGenAvatarCatalog(catalog?: Pick<
  GenerationCatalog,
  'heygen_avatar_options' | 'heygen_avatar_featured'
> | null): { featured: CatalogOption[]; poses: CatalogOption[]; all: CatalogOption[] } {
  const all = catalog?.heygen_avatar_options ?? []
  let featured =
    catalog?.heygen_avatar_featured?.length
      ? [...catalog.heygen_avatar_featured]
      : splitHeyGenAvatarOptions(all).featured

  const poses = all.filter((o) => o.label.includes(' — '))
  const vespriPoses = poses.filter(isVespriPoseOption)
  if (vespriPoses.length === 0) {
    featured = normalizeVespriInList(featured)
  } else {
    featured = featured.filter(
      (o) => !isVespriLabel(o.label) && o.id !== HEYGEN_VESPRI_AVATAR_ID
    )
  }
  const mergedAll = [
    ...featured,
    ...poses.filter((p) => !featured.some((f) => f.id === p.id)),
  ]
  return { featured, poses, all: mergedAll }
}

export type HeyGenAvatarSelectGroup = {
  label: string
  options: { value: string; label: string }[]
}

/** One dropdown: public looks, then Sofia / Florin pose libraries. */
export function buildHeyGenAvatarSelectGroups(
  catalog?: Pick<GenerationCatalog, 'heygen_avatar_options' | 'heygen_avatar_featured'> | null
): HeyGenAvatarSelectGroup[] {
  const { featured, poses } = resolveHeyGenAvatarCatalog(catalog)
  const vespriPoses = poses.filter(isVespriPoseOption)
  const libraryPoses = poses.filter((p) => !isVespriPoseOption(p))
  const groups: HeyGenAvatarSelectGroup[] = []

  if (vespriPoses.length > 0) {
    groups.push({
      label: 'Vespri — positions',
      options: vespriPoses.map((o) => ({ value: o.id, label: o.label })),
    })
  }

  if (featured.length > 0) {
    groups.push({
      label: 'Public looks & presenters',
      options: featured.map((o) => ({ value: o.id, label: o.label })),
    })
  }

  if (libraryPoses.length > 0) {
    groups.push({
      label: 'Sofia / Florin poses',
      options: libraryPoses.map((o) => ({ value: o.id, label: o.label })),
    })
  }

  return groups
}

export function flattenHeyGenAvatarSelectGroups(groups: HeyGenAvatarSelectGroup[]): {
  value: string
  label: string
}[] {
  return groups.flatMap((g) => g.options)
}
