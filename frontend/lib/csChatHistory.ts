/** Creative Studio multi-chat history (ChatGPT-style) — localStorage memory. */

export type CsPipelineAction =
  | 'continue'
  | 'generate_image'
  | 'regenerate_image'
  | 'approve_next'
  | 'generate_video'
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
}

function scopeKey(briefId?: string, brandId?: string) {
  // Keep a brand's chat history stable when the user navigates between briefs.
  // Individual sessions remain isolated by their session id.
  return brandId || briefId || 'draft'
}

export function csHistoryStoreKey(briefId?: string, brandId?: string) {
  return `cs-chat-history-v1:${scopeKey(briefId, brandId)}`
}

export function csActiveChatKey(briefId?: string, brandId?: string) {
  return `cs-chat-active-v1:${scopeKey(briefId, brandId)}`
}

/** Legacy single-thread key from earlier Supercomputer build. */
export function csLegacyThreadKey(briefId?: string, brandId?: string) {
  return `cs-supercomputer-chat-v2:${scopeKey(briefId, brandId)}`
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

export function loadCsChatSessions(briefId?: string, brandId?: string): CsChatSession[] {
  try {
    const currentKey = csHistoryStoreKey(briefId, brandId)
    const fallbackKeys = [
      // Previous versions preferred briefId, and the first render can save
      // before brand selection resolves. Read those keys once for migration.
      briefId ? `cs-chat-history-v1:${briefId}` : '',
      briefId || brandId ? 'cs-chat-history-v1:draft' : '',
    ].filter((key) => key && key !== currentKey)
    const merged = new Map<string, CsChatSession>()
    const migratedKeys: string[] = []
    for (const key of [currentKey, ...fallbackKeys]) {
      const raw = localStorage.getItem(key)
      if (!raw) continue
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) {
        const sessions = parsed
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
        for (const session of sessions) {
          const existing = merged.get(session.id)
          if (!existing || session.updatedAt > existing.updatedAt) {
            merged.set(session.id, session)
          }
        }
        if (key !== currentKey && sessions.length) migratedKeys.push(key)
      }
    }
    const sessions = Array.from(merged.values())
      .sort((a, b) => b.updatedAt - a.updatedAt)
      .slice(0, 3)
    if (sessions.length) {
      saveCsChatSessions(briefId, brandId, sessions)
      for (const key of migratedKeys) localStorage.removeItem(key)
      return sessions
    }
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
    const trimmed = sessions
      .slice()
      .sort((a, b) => b.updatedAt - a.updatedAt)
      // Keep the three most recent complete chats, including generated media
      // message URLs, without overflowing browser localStorage on long briefs.
      .slice(0, 3)
      .map((s) => ({
        ...s,
        messages: (s.messages || []).slice(-40),
      }))
    localStorage.setItem(csHistoryStoreKey(briefId, brandId), JSON.stringify(trimmed))
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
