/** Creative Studio multi-chat history (ChatGPT-style) — localStorage memory. */

export type CsPipelineAction =
  | 'continue'
  | 'generate_image'
  | 'regenerate_image'
  | 'approve_next'
  | 'generate_video'
  | 'continue_video'
  | 'generate_storyboard'

export interface CsStoryboardFrame {
  id: string
  index?: number
  title?: string
  url?: string
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
  role?: 'product' | 'logo' | 'scene' | 'character' | 'reference'
}

export interface CsChatMessage {
  id: string
  role: 'user' | 'assistant' | 'system'
  content: string
  attachments?: CsChatAttachment[]
  jobId?: string
  mediaMode?: 'image' | 'video' | 'storyboard'
  mediaUrl?: string
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
  /** Saved when a staged Seedance part finishes — used to resume after server reload. */
  continuationMeta?: {
    completed_segments: number
    segment_count: number
    generated_duration_seconds?: number
    requested_duration_seconds?: number
    continuity_frame_count?: number
    production_id?: string
  }
}

export interface CsChatSession {
  id: string
  title: string
  updatedAt: number
  createdAt: number
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
}

function scopeKey(briefId?: string, brandId?: string) {
  // Explicit prefixes prevent a brief id, brand id, and draft workspace from
  // ever sharing the same browser-storage namespace.
  if (brandId) return `brand:${brandId}`
  if (briefId) return `brief:${briefId}`
  return 'draft'
}

export function csHistoryStoreKey(briefId?: string, brandId?: string) {
  return `cs-chat-history-v2:${scopeKey(briefId, brandId)}`
}

export function csActiveChatKey(briefId?: string, brandId?: string) {
  return `cs-chat-active-v2:${scopeKey(briefId, brandId)}`
}

/** Legacy single-thread key from earlier Supercomputer build. */
export function csLegacyThreadKey(briefId?: string, brandId?: string) {
  return `cs-supercomputer-chat-v3:${scopeKey(briefId, brandId)}`
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
    }))
}

function v1ScopeKey(briefId?: string, brandId?: string) {
  return brandId || briefId || 'draft'
}

export function loadCsChatSessions(briefId?: string, brandId?: string): CsChatSession[] {
  try {
    const currentKey = csHistoryStoreKey(briefId, brandId)
    const oldScope = v1ScopeKey(briefId, brandId)
    const legacyKey = `cs-chat-history-v1:${oldScope}`
    const current = parseStoredSessions(localStorage.getItem(currentKey))
    // Restore only this exact brand's old history. Never import the shared
    // draft bucket into a selected brand, which caused the cross-brand leak.
    const legacy = parseStoredSessions(localStorage.getItem(legacyKey))
    const merged = new Map<string, CsChatSession>()
    for (const session of [...current, ...legacy]) {
      const existing = merged.get(session.id)
      if (!existing || session.updatedAt > existing.updatedAt) merged.set(session.id, session)
    }
    const sessions = Array.from(merged.values()).sort((a, b) => b.updatedAt - a.updatedAt)
    if (legacy.length) {
      saveCsChatSessions(briefId, brandId, sessions)
      const savedIds = new Set(
        parseStoredSessions(localStorage.getItem(currentKey)).map((session) => session.id),
      )
      if (sessions.every((session) => savedIds.has(session.id))) {
        const legacyActive = localStorage.getItem(`cs-chat-active-v1:${oldScope}`)
        if (legacyActive && savedIds.has(legacyActive)) {
          localStorage.setItem(csActiveChatKey(briefId, brandId), legacyActive)
        }
        localStorage.removeItem(legacyKey)
        localStorage.removeItem(`cs-chat-active-v1:${oldScope}`)
      }
    }
    if (sessions.length) return sessions
  } catch {
    /* ignore */
  }

  // Migrate one-off sessionStorage thread if present
  try {
    const legacy = sessionStorage.getItem(csLegacyThreadKey(briefId, brandId))
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
        saveCsChatSessions(briefId, brandId, [session])
        setCsActiveChatId(briefId, brandId, session.id)
        return [session]
      }
    }
  } catch {
    /* ignore */
  }

  return []
}

export function saveCsChatSessions(
  briefId: string | undefined,
  brandId: string | undefined,
  sessions: CsChatSession[],
) {
  try {
    const complete = sessions
      .slice()
      .sort((a, b) => b.updatedAt - a.updatedAt)
    const key = csHistoryStoreKey(briefId, brandId)
    // Preserve every session and every message. There is no application-level
    // count cap and saving a new chat never deletes an older one.
    localStorage.setItem(key, JSON.stringify(complete))
  } catch {
    /* quota */
  }
}

export function getCsActiveChatId(briefId?: string, brandId?: string): string | null {
  try {
    return localStorage.getItem(csActiveChatKey(briefId, brandId))
  } catch {
    return null
  }
}

export function setCsActiveChatId(
  briefId: string | undefined,
  brandId: string | undefined,
  chatId: string,
) {
  try {
    localStorage.setItem(csActiveChatKey(briefId, brandId), chatId)
  } catch {
    /* ignore */
  }
}

export function upsertCsChatSession(
  briefId: string | undefined,
  brandId: string | undefined,
  session: CsChatSession,
  all: CsChatSession[],
): CsChatSession[] {
  const next = all.filter((s) => s.id !== session.id)
  next.unshift({ ...session, updatedAt: Date.now() })
  saveCsChatSessions(briefId, brandId, next)
  return next
}
