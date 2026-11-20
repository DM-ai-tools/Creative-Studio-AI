/**
 * Creative Studio chat history: the server copy.
 *
 * Chats used to live only in the browser's localStorage (about 5 MB), so a busy account filled it and
 * new chats stopped being saved. Now every chat is also saved on the server (a file on its disk) and
 * stays there until the user deletes it. localStorage is just a fast cache in front of it.
 *
 * Rules that keep chats safe:
 * - A chat is only ever dropped from the browser cache after the server is confirmed to have it.
 * - Nothing is ever deleted on the server except by an explicit delete from the user.
 * - If the server cannot be reached, chats stay in the browser and are sent on the next load.
 */

import type { CsChatSession } from './csChatHistory'

export type CsHistoryBucket = { brandId?: string; briefId?: string }
export type CsServerChat = { bucket: CsHistoryBucket; session: CsChatSession }

export interface CsHistoryClient {
  put(sessionId: string, body: { session: CsChatSession; bucket: CsHistoryBucket }): Promise<{ saved: boolean; updatedAt: number }>
  list(bucket?: string): Promise<CsServerChat[]>
  remove(sessionId: string): Promise<void>
}

const SAVE_DELAY_MS = 1500
const RETRY_DELAY_MS = 15000
const MAX_RETRIES = 5

let clientOverride: CsHistoryClient | null = null

/** Tests only: replace the network client. */
export function setCsHistoryClientForTests(client: CsHistoryClient | null) {
  clientOverride = client
}

async function client(): Promise<CsHistoryClient> {
  if (clientOverride) return clientOverride
  const { default: api } = await import('./api')
  return {
    put: (id, body) => api.put(`/cs-history/sessions/${encodeURIComponent(id)}`, body).then((r) => r.data),
    list: (bucket) =>
      api
        .get<{ sessions: CsServerChat[] }>('/cs-history/sessions', { params: bucket ? { bucket } : undefined, timeout: 120_000 })
        .then((r) => (Array.isArray(r.data?.sessions) ? r.data.sessions : [])),
    remove: (id) => api.delete(`/cs-history/sessions/${encodeURIComponent(id)}`).then(() => undefined),
  }
}

// ── what the server is known to have ────────────────────────────────────────

// chat id -> the updatedAt the server is known to hold. In memory, mirrored to localStorage per user.
const synced = new Map<string, Map<string, number>>()
const SYNCED_KEY = (userId: string) => `cs-chat-synced-v1:${userId}`
const DELETES_KEY = (userId: string) => `cs-chat-pending-deletes-v1:${userId}`

function syncedFor(userId: string): Map<string, number> {
  let map = synced.get(userId)
  if (!map) {
    map = new Map()
    try {
      const raw = typeof localStorage !== 'undefined' ? localStorage.getItem(SYNCED_KEY(userId)) : null
      const parsed = raw ? JSON.parse(raw) : {}
      for (const [id, at] of Object.entries(parsed || {})) if (Number.isFinite(Number(at))) map.set(id, Number(at))
    } catch {
      /* start empty: everything is simply re-checked against the server */
    }
    synced.set(userId, map)
  }
  return map
}

function persistSynced(userId: string) {
  try {
    localStorage.setItem(SYNCED_KEY(userId), JSON.stringify(Object.fromEntries(syncedFor(userId))))
  } catch {
    /* the in-memory map still works for this page; the next load re-checks with the server */
  }
}

/** True when the server is known to hold this chat at (at least) this version. */
export function isConfirmedOnServer(userId: string, session: Pick<CsChatSession, 'id' | 'updatedAt'>): boolean {
  const known = syncedFor(userId).get(session.id)
  return known !== undefined && known >= Number(session.updatedAt || 0)
}

export function markConfirmedOnServer(userId: string, id: string, updatedAt: number) {
  syncedFor(userId).set(id, Number(updatedAt) || 0)
  persistSynced(userId)
}

/** The server is NOT known to have this chat (any more): never trim it from the browser. */
export function forgetConfirmedOnServer(userId: string, id: string) {
  syncedFor(userId).delete(id)
  persistSynced(userId)
}

const forget = forgetConfirmedOnServer

/** Tests only: start from a clean slate, as a freshly loaded page would. */
export function resetCsHistorySyncForTests() {
  synced.clear()
  Array.from(pending.values()).forEach((entry) => {
    if (entry.timer) clearTimeout(entry.timer)
  })
  pending.clear()
  serverReachable = null
}

// ── is the server reachable? ────────────────────────────────────────────────

let serverReachable: boolean | null = null // null until the first request finishes

/** False while the server is failing, so the "could not save" warning is shown only when it matters. */
export function serverLooksHealthy(): boolean {
  return serverReachable === true
}

// ── saving ──────────────────────────────────────────────────────────────────

type Pending = { userId: string; session: CsChatSession; bucket: CsHistoryBucket; timer: ReturnType<typeof setTimeout> | null; tries: number }
const pending = new Map<string, Pending>()

async function sendNow(entry: Pending): Promise<boolean> {
  const { userId, session, bucket } = entry
  try {
    const result = await (await client()).put(session.id, { session, bucket })
    serverReachable = true
    // saved:false means another device already holds a newer copy; either way the server has it.
    markConfirmedOnServer(userId, session.id, Number(result.updatedAt) || Number(session.updatedAt) || 0)
    if (pending.get(session.id) === entry) pending.delete(session.id)
    return true
  } catch {
    serverReachable = false
    return false
  }
}

function schedule(entry: Pending, delay: number) {
  if (entry.timer) clearTimeout(entry.timer)
  entry.timer = setTimeout(async () => {
    entry.timer = null
    if (pending.get(entry.session.id) !== entry) return // superseded by a newer save
    const ok = await sendNow(entry)
    if (!ok && pending.get(entry.session.id) === entry && ++entry.tries <= MAX_RETRIES) schedule(entry, RETRY_DELAY_MS)
  }, delay)
}

/** Save a chat to the server soon (many quick edits are sent as one). */
export function queueServerSave(userId: string, session: CsChatSession, bucket: CsHistoryBucket) {
  if (!userId || userId === 'anonymous' || !session?.id) return
  const previous = pending.get(session.id)
  if (previous?.timer) clearTimeout(previous.timer)
  const entry: Pending = { userId, session, bucket, timer: null, tries: 0 }
  pending.set(session.id, entry)
  schedule(entry, SAVE_DELAY_MS)
}

/** Send one chat to the server right now and wait for the answer. Used when catching the server up. */
export async function saveChatToServerNow(userId: string, session: CsChatSession, bucket: CsHistoryBucket): Promise<boolean> {
  if (!userId || userId === 'anonymous' || !session?.id) return false
  return sendNow({ userId, session, bucket, timer: null, tries: 0 })
}

/** Send everything waiting right now (the tab is being hidden or closed). */
export function flushServerSaves() {
  for (const entry of Array.from(pending.values())) {
    if (entry.timer) clearTimeout(entry.timer)
    entry.timer = null
    void sendNow(entry)
  }
}

if (typeof document !== 'undefined') {
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'hidden') flushServerSaves()
  })
  window.addEventListener('pagehide', flushServerSaves)
}

// ── deleting (only ever because the user asked) ─────────────────────────────

function pendingDeletes(userId: string): Set<string> {
  try {
    const raw = localStorage.getItem(DELETES_KEY(userId))
    const parsed = raw ? JSON.parse(raw) : []
    return new Set(Array.isArray(parsed) ? parsed.map(String) : [])
  } catch {
    return new Set()
  }
}

function savePendingDeletes(userId: string, ids: Set<string>) {
  try {
    if (ids.size) localStorage.setItem(DELETES_KEY(userId), JSON.stringify(Array.from(ids)))
    else localStorage.removeItem(DELETES_KEY(userId))
  } catch {
    /* ignore */
  }
}

/** The user deleted a chat: remove it from the server too. If that fails it is retried next load. */
export async function queueServerDelete(userId: string, id: string) {
  if (!userId || userId === 'anonymous' || !id) return
  const entry = pending.get(id)
  if (entry?.timer) clearTimeout(entry.timer)
  pending.delete(id)
  forget(userId, id)
  const ids = pendingDeletes(userId)
  ids.add(id)
  savePendingDeletes(userId, ids)
  try {
    await (await client()).remove(id)
    serverReachable = true
    ids.delete(id)
    savePendingDeletes(userId, ids)
  } catch {
    serverReachable = false
  }
}

export async function retryPendingDeletes(userId: string) {
  const ids = pendingDeletes(userId)
  for (const id of Array.from(ids)) {
    try {
      await (await client()).remove(id)
      ids.delete(id)
    } catch {
      /* try again next load */
    }
  }
  savePendingDeletes(userId, ids)
  return ids
}

// ── reading ─────────────────────────────────────────────────────────────────

export async function fetchServerChats(bucketKey?: string): Promise<CsServerChat[]> {
  const items = await (await client()).list(bucketKey)
  serverReachable = true
  return items.filter((item) => item?.session && typeof item.session.id === 'string')
}
