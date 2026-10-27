import type { User } from '@/types'

export const PRODUCT_SCOPE_CS_SEEDANCE25 = 'creative_studio_seedance25'

export const CS25_DEFAULT_VIDEO_MODEL = 'ark-seedance-2-5'

export function isCsSeedance25Only(user?: User | null): boolean {
  return user?.product_scope === PRODUCT_SCOPE_CS_SEEDANCE25
}

/** Seedance 2.5–limited accounts only (never admin or full-studio users). */
export function isCsSeedance25WorkspaceUser(user?: User | null): boolean {
  if (!user) return false
  if (user.role === 'admin') return false
  return isCsSeedance25Only(user)
}

/** Disable browser right-click only inside the CS25 workspace for those accounts. */
export function shouldBlockContextMenuForUser(
  user?: User | null,
  pathname?: string | null,
): boolean {
  if (!isCsSeedance25WorkspaceUser(user)) return false
  const path = pathname ?? ''
  return isPathAllowedForCs25(path)
}

const CS25_ALLOWED_PREFIXES = ['/brand-kit', '/variants', '/briefs']

export function isPathAllowedForCs25(pathname: string): boolean {
  if (pathname === '/login' || pathname.startsWith('/login/')) return true
  return CS25_ALLOWED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
}

export function cs25DefaultRedirect(pathname: string): string {
  if (pathname === '/dashboard' || pathname === '/') return '/briefs/new'
  return '/briefs/new'
}
