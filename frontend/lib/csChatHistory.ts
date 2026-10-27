/** Creative Studio multi-chat history (ChatGPT-style) — localStorage memory. */

export type CsPipelineAction =
  | 'continue'
  | 'generate_image'
  | 'regenerate_image'
  | 'approve_next'
  | 'generate_video'
  | 'continue_video'
  | 'generate_storyboard'
  | 'generate_next_chapter_image'
  | 'generate_broll_image'
  | 'generate_all_broll'
  | 'regenerate_broll_image'
  | 'approve_broll'
  | 'approve_all_broll'

export interface CsStoryboardFrame {
  id: string
  index?: number
  title?: string
  url?: string
  /** BytePlus TOS URL — passed unchanged to Seedance when present. */
  byteplusUrl?: string
  imagePrompt?: string
  overlays?: string[]
  status?: string
  /** When false or discarded, frame is excluded from Seedance references. */
  selected?: boolean
  discarded?: boolean
}

export function storyboardFramesForVideo(frames: CsStoryboardFrame[] | undefined): string[] {
  return (frames || [])
    .filter((frame) => frame.url && frame.selected !== false && !frame.discarded)
    .map((frame) => frame.url as string)
}

export interface CsChatAttachment {
  id: string
  name: string
  url: string
  previewUrl?: string
  mime?: string
  role?: 'product' | 'logo' | 'scene' | 'character' | 'reference' | 'proof'
}

export interface CsChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  attachments?: CsChatAttachment[]
  jobId?: string
  mediaMode?: 'image' | 'video' | 'storyboard' | 'broll_board'
  mediaUrl?: string
  byteplusUrl?: string
  seedImageUrl?: string
  model?: string
  status?: 'idle' | 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
  progress?: string
  error?: string
  imagePrompt?: string
  videoPrompt?: string
  durationSeconds?: number
  variantId?: string
  suggestedActions?: CsPipelineAction[]
  phase?: string
  storyboard?: CsStoryboardFrame[]
  chapterIndex?: number
  filmTotalChapters?: number
  brollIndex?: number
  /** Saved when a staged Seedance part finishes — used to resume after server reload. */
  continuationMeta?: {
    completed_segments: number
    segment_count: number
    generated_duration_seconds?: number
    requested_duration_seconds?: number
    continuity_frame_count?: number
    production_id?: string
    continuity_video_reference_url?: string
    continuity_reference_url?: string
    staged_segment_paths?: string[]
    chapter_index?: number
    film_total_chapters?: number
  }
}

export interface CsChatSession {
  id: string
  title: string
  updatedAt: number
  createdAt: number
  /** localStorage bucket (set when loading merged workspace history). */
  historyBrandId?: string
  historyBriefId?: string
  messages: CsChatMessage[]
  imagePrompt: string
  videoPrompt: string
  approvedImageUrl: string
  productReferenceUrl: string
  logoReferenceUrl: string
  characterReferenceUrl: string
  additionalReferenceUrls: string[]
  phase: string
  videoModel?: string
  speechMode: 'native_presenter' | 'external_voiceover'
  promptOnlyVideo: boolean
  cloneMode: boolean
  cloneSceneId: string
  cloneCount: number
}

/** Per user + tenant workspace (never shared across logins). */
export type CsHistoryScope = {
  userId: string
  tenantId?: string
  briefId?: string
  brandId?: string
  /** Server has no briefs/variants yet — drop any leaked browser history once. */
  freshWorkspace?: boolean
}

export function csHistoryScope(
  userId: string | null | undefined,
  briefId?: string,
  brandId?: string,
  options?: { tenantId?: string | null; freshWorkspace?: boolean },
): CsHistoryScope {
  return {
    userId: (userId || '').trim() || 'anonymous',
    tenantId: (options?.tenantId || '').trim() || undefined,
    briefId: briefId || undefined,
    brandId: brandId || undefined,
    freshWorkspace: Boolean(options?.freshWorkspace),
  }
}

function scopeSegment(scope: CsHistoryScope): string {
  const uid = scope.userId.trim() || 'anonymous'
  const tenant = scope.tenantId ? `:t:${scope.tenantId}` : ''
  if (scope.brandId) return `u:${uid}${tenant}:brand:${scope.brandId}`
  if (scope.briefId) return `u:${uid}${tenant}:brief:${scope.briefId}`
  return `u:${uid}${tenant}:draft`
}

export function csHistoryStoreKey(scope: CsHistoryScope) {
  return `cs-chat-history-v4:${scopeSegment(scope)}`
}

export function csActiveChatKey(scope: CsHistoryScope) {
  return `cs-chat-active-v4:${scopeSegment(scope)}`
}

/** Legacy single-thread key from earlier Supercomputer build. */
export function csLegacyThreadKey(scope: CsHistoryScope) {
  return `cs-supercomputer-chat-v4:${scopeSegment(scope)}`
}

/** Pre-tenant v3 key (same user id only — never import shared v2 buckets). */
function priorUserStoreKey(scope: CsHistoryScope): string {
  const uid = scope.userId.trim()
  if (scope.brandId) return `cs-chat-history-v3:u:${uid}:brand:${scope.brandId}`
  if (scope.briefId) return `cs-chat-history-v3:u:${uid}:brief:${scope.briefId}`
  return `cs-chat-history-v3:u:${uid}:draft`
}

function priorUserActiveKey(scope: CsHistoryScope): string {
  const uid = scope.userId.trim()
  if (scope.brandId) return `cs-chat-active-v3:u:${uid}:brand:${scope.brandId}`
  if (scope.briefId) return `cs-chat-active-v3:u:${uid}:brief:${scope.briefId}`
  return `cs-chat-active-v3:u:${uid}:draft`
}

function freshIsolationKey(scope: CsHistoryScope): string {
  return `cs-chat-isolated-v1:${scope.userId}:${scope.tenantId || 'tenant'}`
}

function purgeAllChatKeysForUser(userId: string) {
  if (typeof localStorage === 'undefined' || !userId) return
  try {
    const prefixes = [
      `cs-chat-history-v3:u:${userId}`,
      `cs-chat-history-v4:u:${userId}`,
      `cs-chat-active-v3:u:${userId}`,
      `cs-chat-active-v4:u:${userId}`,
    ]
    for (let i = localStorage.length - 1; i >= 0; i--) {
      const key = localStorage.key(i)
      if (!key) continue
      if (prefixes.some((p) => key.startsWith(p))) {
        localStorage.removeItem(key)
      }
    }
  } catch {
    /* ignore */
  }
}

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

export function emptyCsSession(title = 'New chat'): CsChatSession {
  const now = Date.now()
  return {
    id: uid(),
    title,
    createdAt: now,
    updatedAt: now,
    messages: [],
    imagePrompt: '',
    videoPrompt: '',
    approvedImageUrl: '',
    productReferenceUrl: '',
    logoReferenceUrl: '',
    characterReferenceUrl: '',
    additionalReferenceUrls: [],
    phase: '',
    speechMode: 'native_presenter',
    promptOnlyVideo: true,
    cloneMode: false,
    cloneSceneId: '',
    cloneCount: 4,
  }
}

export function titleFromMessages(messages: CsChatMessage[]): string {
  const first = messages.find((m) => m.role === 'user' && m.content.trim())
  if (!first) return 'New chat'
  const t = first.content.trim().replace(/\s+/g, ' ')
  return t.length > 42 ? `${t.slice(0, 42)}…` : t
}

function parseStoredSessions(raw: string | null): CsChatSession[] {
  if (!raw) return []
  const parsed = JSON.parse(raw)
  if (!Array.isArray(parsed)) return []
  return parsed
    .filter((s) => s && typeof s.id === 'string')
    .map((s) => ({
      id: s.id,
      title: String(s.title || 'New chat'),
      createdAt: Number(s.createdAt || s.updatedAt || Date.now()),
      updatedAt: Number(s.updatedAt || Date.now()),
      messages: Array.isArray(s.messages) ? s.messages : [],
      imagePrompt: String(s.imagePrompt || ''),
      videoPrompt: String(s.videoPrompt || ''),
      approvedImageUrl: String(s.approvedImageUrl || ''),
      productReferenceUrl: String(s.productReferenceUrl || ''),
      logoReferenceUrl: String(s.logoReferenceUrl || ''),
      characterReferenceUrl: String(s.characterReferenceUrl || ''),
      additionalReferenceUrls: Array.isArray(s.additionalReferenceUrls)
        ? s.additionalReferenceUrls.map(String).filter(Boolean).slice(0, 7)
        : [],
      phase: String(s.phase || ''),
      speechMode:
        s.speechMode === 'external_voiceover' ? 'external_voiceover' : 'native_presenter',
      promptOnlyVideo: s.promptOnlyVideo !== false,
      cloneMode: Boolean(s.cloneMode),
      cloneSceneId: String(s.cloneSceneId || ''),
      cloneCount: Math.max(2, Math.min(6, Number(s.cloneCount || 4))),
    }))
}

function mergeSessionLists(...lists: CsChatSession[][]): CsChatSession[] {
  const merged = new Map<string, CsChatSession>()
  for (const list of lists) {
    for (const session of list) {
      const existing = merged.get(session.id)
      if (!existing || session.updatedAt > existing.updatedAt) {
        merged.set(session.id, session)
      }
    }
  }
  return Array.from(merged.values()).sort((a, b) => b.updatedAt - a.updatedAt)
}

function targetScopeFromLegacySuffix(
  base: CsHistoryScope,
  suffix: string,
): CsHistoryScope {
  const scope: CsHistoryScope = {
    ...base,
    brandId: undefined,
    briefId: undefined,
  }
  if (suffix === 'draft') return scope
  if (suffix.startsWith('brand:')) {
    scope.brandId = suffix.slice('brand:'.length)
    return scope
  }
  if (suffix.startsWith('brief:')) {
    scope.briefId = suffix.slice('brief:'.length)
    return scope
  }
  return scope
}

/** One-time: copy old shared v2/v1 browser buckets into this user's v4 (established accounts only). */
function importLegacySharedBucketsOnce(base: CsHistoryScope) {
  if (base.freshWorkspace || typeof localStorage === 'undefined') return
  const claimKey = `cs-chat-legacy-imported-v3:${base.userId}`
  if (localStorage.getItem(claimKey)) return

  try {
    const keys: string[] = []
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (
        key?.startsWith('cs-chat-history-v2:') ||
        key?.startsWith('cs-chat-history-v1:')
      ) {
        keys.push(key)
      }
    }
    for (const key of keys) {
      const prefix = key.startsWith('cs-chat-history-v2:')
        ? 'cs-chat-history-v2:'
        : 'cs-chat-history-v1:'
      const suffix = key.slice(prefix.length)
      const target = targetScopeFromLegacySuffix(base, suffix)
      const incoming = parseStoredSessions(localStorage.getItem(key))
      if (!incoming.length) continue
      const existing = parseStoredSessions(localStorage.getItem(csHistoryStoreKey(target)))
      saveCsChatSessions(target, mergeSessionLists(existing, incoming))
    }
    localStorage.setItem(claimKey, '1')
  } catch {
    /* ignore */
  }
}

/** Copy all v3 per-user keys (pre-tenant) into matching v4 scopes. */
function migrateAllPriorUserStores(base: CsHistoryScope) {
  if (base.freshWorkspace || typeof localStorage === 'undefined') return
  const prefix = `cs-chat-history-v3:u:${base.userId}:`
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (!key?.startsWith(prefix)) continue
      const suffix = key.slice(prefix.length)
      const target = targetScopeFromLegacySuffix(base, suffix)
      const incoming = parseStoredSessions(localStorage.getItem(key))
      if (!incoming.length) continue
      const existing = parseStoredSessions(localStorage.getItem(csHistoryStoreKey(target)))
      saveCsChatSessions(target, mergeSessionLists(existing, incoming))
    }
  } catch {
    /* ignore */
  }
}

export function sessionStorageScope(
  base: CsHistoryScope,
  session: Pick<CsChatSession, 'historyBrandId' | 'historyBriefId'>,
): CsHistoryScope {
  return csHistoryScope(
    base.userId,
    session.historyBriefId ?? base.briefId,
    session.historyBrandId ?? base.brandId,
    { tenantId: base.tenantId, freshWorkspace: base.freshWorkspace },
  )
}

function listV4HistoryStoreKeys(scope: CsHistoryScope): string[] {
  if (typeof localStorage === 'undefined') return []
  const uid = scope.userId.trim()
  const prefix = scope.tenantId
    ? `cs-chat-history-v4:u:${uid}:t:${scope.tenantId}:`
    : `cs-chat-history-v4:u:${uid}:`
  const keys: string[] = []
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i)
      if (key?.startsWith(prefix)) keys.push(key)
    }
  } catch {
    /* ignore */
  }
  return keys
}

function scopeFromV4StoreKey(storeKey: string, base: CsHistoryScope): CsHistoryScope {
  const segment = storeKey.replace('cs-chat-history-v4:', '')
  const draftMatch = segment.match(/^u:[^:]+(?::t:[^:]+)?:draft$/)
  if (draftMatch) {
    return csHistoryScope(base.userId, undefined, undefined, {
      tenantId: base.tenantId,
      freshWorkspace: base.freshWorkspace,
    })
  }
  const brandMatch = segment.match(/^u:[^:]+(?::t:[^:]+)?:brand:(.+)$/)
  if (brandMatch) {
    return csHistoryScope(base.userId, undefined, brandMatch[1], {
      tenantId: base.tenantId,
      freshWorkspace: base.freshWorkspace,
    })
  }
  const briefMatch = segment.match(/^u:[^:]+(?::t:[^:]+)?:brief:(.+)$/)
  if (briefMatch) {
    return csHistoryScope(base.userId, briefMatch[1], undefined, {
      tenantId: base.tenantId,
      freshWorkspace: base.freshWorkspace,
    })
  }
  return base
}

function tagSessionsWithStoreScope(
  storeKey: string,
  sessions: CsChatSession[],
  base: CsHistoryScope,
): CsChatSession[] {
  const bucket = scopeFromV4StoreKey(storeKey, base)
  return sessions.map((s) => ({
    ...s,
    historyBrandId: bucket.brandId,
    historyBriefId: bucket.briefId,
  }))
}

function prepareCsChatStorage(scope: CsHistoryScope) {
  if (!scope.userId || scope.userId === 'anonymous') return

  if (scope.freshWorkspace) {
    try {
      if (!localStorage.getItem(freshIsolationKey(scope))) {
        purgeAllChatKeysForUser(scope.userId)
        localStorage.setItem(freshIsolationKey(scope), '1')
      }
    } catch {
      /* ignore */
    }
    return
  }

  importLegacySharedBucketsOnce(scope)
  migrateAllPriorUserStores(scope)
}

/** All chats for this user + tenant (every brand / draft bucket). */
export function loadCsChatSessionsWorkspace(scope: CsHistoryScope): CsChatSession[] {
  if (!scope.userId || scope.userId === 'anonymous') return []

  prepareCsChatStorage(scope)

  const keys = listV4HistoryStoreKeys(scope)
  if (keys.length) {
    const lists = keys.map((key) =>
      tagSessionsWithStoreScope(
        key,
        parseStoredSessions(localStorage.getItem(key)),
        scope,
      ),
    )
    return mergeSessionLists(...lists)
  }

  return loadCsChatSessions(scope)
}

export function persistCsChatSession(scope: CsHistoryScope, session: CsChatSession) {
  if (!scope.userId || scope.userId === 'anonymous') return
  const storeScope = sessionStorageScope(scope, session)
  const bucket = parseStoredSessions(localStorage.getItem(csHistoryStoreKey(storeScope)))
  saveCsChatSessions(storeScope, upsertCsChatSession(storeScope, session, bucket))
}

export function removeCsChatSession(scope: CsHistoryScope, session: CsChatSession) {
  if (!scope.userId || scope.userId === 'anonymous') return
  const storeScope = sessionStorageScope(scope, session)
  const bucket = parseStoredSessions(localStorage.getItem(csHistoryStoreKey(storeScope)))
  saveCsChatSessions(
    storeScope,
    bucket.filter((s) => s.id !== session.id),
  )
}

export function findWorkspaceActiveChatId(scope: CsHistoryScope): string | null {
  const direct = getCsActiveChatId(scope)
  if (direct) return direct
  for (const key of listV4HistoryStoreKeys(scope)) {
    const bucketScope = scopeFromV4StoreKey(key, scope)
    const active = getCsActiveChatId(bucketScope)
    if (active) return active
  }
  return null
}

function migratePriorUserStore(scope: CsHistoryScope): CsChatSession[] {
  try {
    const prior = parseStoredSessions(localStorage.getItem(priorUserStoreKey(scope)))
    if (!prior.length) return []
    saveCsChatSessions(scope, prior)
    const active = localStorage.getItem(priorUserActiveKey(scope))
    if (active && prior.some((s) => s.id === active)) {
      setCsActiveChatId(scope, active)
    }
    return prior
  } catch {
    return []
  }
}

export function loadCsChatSessions(scope: CsHistoryScope): CsChatSession[] {
  if (!scope.userId || scope.userId === 'anonymous') return []

  prepareCsChatStorage(scope)

  try {
    const current = parseStoredSessions(localStorage.getItem(csHistoryStoreKey(scope)))
    if (current.length) {
      return current.sort((a, b) => b.updatedAt - a.updatedAt)
    }
  } catch {
    /* ignore */
  }

  if (!scope.freshWorkspace) {
    const migrated = migratePriorUserStore(scope)
    if (migrated.length) {
      return migrated.sort((a, b) => b.updatedAt - a.updatedAt)
    }
  }

  try {
    const legacy = sessionStorage.getItem(csLegacyThreadKey(scope))
    if (legacy) {
      const parsed = JSON.parse(legacy)
      const messages = Array.isArray(parsed)
        ? parsed
        : Array.isArray(parsed?.messages)
          ? parsed.messages
          : []
      if (messages.length) {
        const session = emptyCsSession(titleFromMessages(messages))
        session.messages = messages
        session.imagePrompt = String(parsed?.imagePrompt || '')
        session.videoPrompt = String(parsed?.videoPrompt || '')
        session.approvedImageUrl = String(parsed?.approvedImageUrl || '')
        session.characterReferenceUrl = String(parsed?.characterReferenceUrl || '')
        session.phase = String(parsed?.phase || '')
        saveCsChatSessions(scope, [session])
        setCsActiveChatId(scope, session.id)
        return [session]
      }
    }
  } catch {
    /* ignore */
  }

  return []
}

export function saveCsChatSessions(scope: CsHistoryScope, sessions: CsChatSession[]) {
  if (!scope.userId || scope.userId === 'anonymous') return
  try {
    const complete = sessions.slice().sort((a, b) => b.updatedAt - a.updatedAt)
    localStorage.setItem(csHistoryStoreKey(scope), JSON.stringify(complete))
  } catch {
    /* quota */
  }
}

export function getCsActiveChatId(scope: CsHistoryScope): string | null {
  if (!scope.userId || scope.userId === 'anonymous') return null
  try {
    return localStorage.getItem(csActiveChatKey(scope))
  } catch {
    return null
  }
}

export function setCsActiveChatId(scope: CsHistoryScope, chatId: string) {
  if (!scope.userId || scope.userId === 'anonymous') return
  try {
    localStorage.setItem(csActiveChatKey(scope), chatId)
  } catch {
    /* ignore */
  }
}

export function upsertCsChatSession(
  scope: CsHistoryScope,
  session: CsChatSession,
  all: CsChatSession[],
): CsChatSession[] {
  const next = all.filter((s) => s.id !== session.id)
  next.unshift({ ...session, updatedAt: Date.now() })
  saveCsChatSessions(scope, next)
  return next
}
