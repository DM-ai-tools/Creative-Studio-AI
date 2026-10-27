'use client'

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Link from 'next/link'
import { useApi } from '@/hooks/useApi'
import { generationApi, variantsApi, brandsApi, assetsApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { assetUrl } from '@/lib/utils'
import type { Asset, GenerationModelOption } from '@/types'
import {
  emptyCsSession,
  csHistoryScope,
  getCsActiveChatId,
  loadCsChatSessions,
  persistCsChatSession,
  removeCsChatSession,
  sessionStorageScope,
  setCsActiveChatId,
  titleFromMessages,
  type CsChatMessage,
  type CsChatSession,
  type CsPipelineAction,
  storyboardFramesForVideo,
} from '@/lib/csChatHistory'
import CsMessageContent from '@/components/brief/CsMessageContent'
import { UI } from '@/lib/uiLabels'
import { useAuth } from '@/hooks/useAuth'
import { CS25_DEFAULT_VIDEO_MODEL, isCsSeedance25Only } from '@/lib/productScope'

type ChatMode = 'auto' | 'ask' | 'generate'
type DurationId = 'auto' | '5' | '10' | '15' | '30' | '60' | '120'
type AspectId = '9/16' | '1/1' | '16/9' | '4/3' | '4/5'
type ResolutionId = '480p' | '720p' | '1080p'
type SpeechMode = 'native_presenter' | 'external_voiceover'
type ContinuationReferenceMode = 'continuity' | 'first_frame'
type PipelineAction = CsPipelineAction
type MediaLibrarySection = 'uploads' | 'generations' | 'characters' | 'liked'
type MediaLibraryFilter = 'recent' | 'all' | 'images' | 'videos' | 'audio'
type MediaLibrarySort = 'newest' | 'oldest' | 'name'

type ChatAttachment = NonNullable<CsChatMessage['attachments']>[number]
type ChatMessage = CsChatMessage

interface Props {
  briefId?: string
  brandId?: string
  briefTitle?: string
  brandName?: string
  productName?: string
  initialPrompt?: string
  /** When true, video output is locked to Seedance 2.5 (account policy). */
  seedance25Only?: boolean
}

const DURATIONS: { id: DurationId; label: string }[] = [
  { id: 'auto', label: 'Auto · script length' },
  { id: '5', label: '5s' },
  { id: '10', label: '10s' },
  { id: '15', label: '15s' },
  { id: '30', label: '30s' },
  { id: '60', label: '1m' },
  { id: '120', label: '2m' },
]

const ASPECTS: { id: AspectId; label: string }[] = [
  { id: '9/16', label: '9:16' },
  { id: '1/1', label: '1:1' },
  { id: '16/9', label: '16:9' },
  { id: '4/3', label: '4:3' },
  { id: '4/5', label: '4:5' },
]

const RESOLUTIONS: { id: ResolutionId; label: string }[] = [
  { id: '480p', label: '480p' },
  { id: '720p', label: '720p' },
  { id: '1080p', label: '1080p · Full HD' },
]

const MODES: { id: ChatMode; label: string; hint: string }[] = [
  { id: 'auto', label: 'Auto', hint: 'Plan → image → video' },
  { id: 'ask', label: 'Ask', hint: 'Chat only' },
  { id: 'generate', label: 'Generate', hint: 'Start production plan' },
]

function isChapterHandoffReady(
  m: ChatMessage,
  projectDurationSeconds: number,
  clipCap: number,
): boolean {
  if (m.mediaMode !== 'video' || m.status !== 'done' || !m.mediaUrl) return false
  if (projectDurationSeconds <= clipCap) return false
  const clipSeconds = m.durationSeconds ?? 0
  if (clipSeconds > clipCap) return false
  const content = String(m.content || '')
  if (/All \d+ chapters are stitched|stitched into one/i.test(content)) return false
  if (
    m.continuationMeta?.completed_segments &&
    m.continuationMeta?.segment_count &&
    m.continuationMeta.completed_segments < m.continuationMeta.segment_count
  ) {
    return true
  }
  if (m.phase === 'awaiting_chapter_image') return true
  if (/Partial video ready|Chapter \d+\/\d+ is ready|Part \d+\/\d+ is ready/i.test(content)) {
    return true
  }
  return clipSeconds > 0 && clipSeconds <= clipCap && projectDurationSeconds > clipCap
}

const ACTION_LABELS: Record<string, string> = {
  generate_image: 'Generate image (GPT Image 2)',
  regenerate_image: 'Regenerate image',
  approve_next: 'Approve & Next → Seedance video',
  generate_video: 'Generate video',
  continue_video: 'Generate next part',
  generate_next_chapter_image: 'Generate next chapter still',
  generate_broll_image: 'Generate B-roll still (one at a time)',
  generate_all_broll: 'Generate remaining B-roll stills',
  regenerate_broll_image: 'Regenerate B-roll still',
  approve_broll: 'Approve B-roll → lock for Seedance',
  approve_all_broll: 'Approve all B-roll → lock for Seedance',
}

function chapterHandoffLabel(m: ChatMessage, clipCap: number, projectDurationSeconds: number) {
  const nextChapter =
    m.continuationMeta?.chapter_index ??
    (isChapterHandoffReady(m, projectDurationSeconds, clipCap) ? 1 : 0)
  return nextChapter >= 1
    ? `Start chapter ${nextChapter + 1} → Seedance`
    : ACTION_LABELS.approve_next
}

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function mergeStoryboardFrames(
  current: NonNullable<ChatMessage['storyboard']> | undefined,
  incoming: NonNullable<ChatMessage['storyboard']>,
): NonNullable<ChatMessage['storyboard']> {
  if (!incoming.length) return current || []
  const byKey = new Map<string, NonNullable<ChatMessage['storyboard']>[number]>()
  for (const frame of current || []) {
    byKey.set(String(frame.index ?? frame.id), frame)
  }
  for (const frame of incoming) {
    const key = String(frame.index ?? frame.id)
    const prev = byKey.get(key)
    byKey.set(
      key,
      prev
        ? {
            ...prev,
            ...frame,
            url: frame.url || prev.url,
            imagePrompt: frame.imagePrompt || prev.imagePrompt,
          }
        : frame,
    )
  }
  return Array.from(byKey.values()).sort(
    (a, b) => Number(a.index || 0) - Number(b.index || 0),
  )
}

function isProductionSetupMessage(text: string): boolean {
  const low = text.toLowerCase()
  if (low.includes('production lock only')) return true
  if (low.includes('do not start seedance') || low.includes("don't start seedance")) return true
  if (low.includes('do not start video') || low.includes('no seedance yet')) return true
  if (low.includes('b-roll stills first') || low.includes('broll stills first')) return true
  if (low.includes('generate b-roll stills first') || low.includes('generate broll stills first')) {
    return true
  }
  if (low.includes('production lock') && (
    low.includes('do not start') ||
    low.includes("don't start") ||
    low.includes('b-roll first') ||
    low.includes('broll first') ||
    low.includes('reply:')
  )) {
    return true
  }
  return false
}

/**
 * Parse inline chapter timestamps like "0:00–0:23" or "0:23–0:53" from a prompt
 * and return the total chapter duration in seconds.
 * Finds the LAST end-time in the prompt (e.g. 0:23 → 23s, 0:53 → 53-23=30s for window).
 * Actually returns (lastEndSeconds - firstStartSeconds) as the chapter window duration.
 */
function extractChapterDurationFromPrompt(text: string): number | undefined {
  // Match patterns: 0:00–0:23, 0:23-0:53, 00:10–00:23 etc.
  const timeRe = /(\d{1,2}):(\d{2})\s*[–—\-]\s*(\d{1,2}):(\d{2})/g
  let firstStart: number | undefined
  let lastEnd: number | undefined
  let m: RegExpExecArray | null
  while ((m = timeRe.exec(text)) !== null) {
    const startSec = parseInt(m[1]) * 60 + parseInt(m[2])
    const endSec = parseInt(m[3]) * 60 + parseInt(m[4])
    if (firstStart === undefined) firstStart = startSec
    lastEnd = endSec
  }
  if (firstStart === undefined || lastEnd === undefined) return undefined
  const duration = lastEnd - firstStart
  return duration > 0 ? duration : undefined
}

/** Count how many IMAGE N - blocks are in the text */
function countBrollImageBlocks(text: string): number {
  const matches = text.match(/(?:^|\n)\s*IMAGE\s+\d+\s*[-–—:]/gi)
  return matches ? matches.length : 0
}

/** Detect IMAGE 1–9 B-roll block pastes — should generate stills, never a video */
function isBrollImageBlock(text: string): boolean {
  return /(?:^|\n)\s*IMAGE\s+\d+\s*[-–—:]/im.test(text) &&
    /scene\s*timing|image\s+generation\s+prompt/i.test(text)
}

/**
 * Detect a full master production brief:
 * has IMAGE blocks + SCENE timeline + DIALOGUE — one paste orchestrates everything.
 */
function isMasterProductionBrief(text: string): boolean {
  if (text.length < 800) return false
  const hasImages = /(?:^|\n)\s*IMAGE\s+\d+\s*[-–—]/im.test(text)
  const hasScenes = /(?:^|\n)\s*SCENE\s+\d+\s*[-–—]/im.test(text)
  const hasTimeline = /\d{2}:\d{2}[–—\-]\d{2}:\d{2}/.test(text)
  const hasDialogue = /DIALOGUE|SPEAK EXACTLY|narration/i.test(text)
  return hasImages && hasScenes && hasTimeline && hasDialogue
}

function seedanceClipCap(modelId: string) {
  return /2-5|2\.5/i.test(modelId) ? 30 : 15
}

function seedanceModelLabel(modelId: string) {
  return seedanceClipCap(modelId) >= 30 ? 'Seedance 2.5' : 'Seedance 2.0'
}

function imageModelLabel(modelId: string) {
  if (/seedream.*flash/i.test(modelId)) return 'Seedream 5.0 Flash'
  if (/seedream.*pro/i.test(modelId)) return 'Seedream 5.0 Pro'
  if (/seedream/i.test(modelId)) return 'Seedream 5.0 Lite'
  return 'GPT Image 2'
}

function buildContinuationRecoveryPayload(args: {
  sessionId: string
  videoModel: string
  videoPrompt: string
  duration: DurationId
  aspect: AspectId
  resolution: ResolutionId
  soundOn: boolean
  speechMode: SpeechMode
  promptOnlyVideo: boolean
  productName: string
  brandName: string
  productReferenceUrl: string
  logoReferenceUrl: string
  additionalReferenceUrls: string[]
  referenceAssets: ChatAttachment[]
  requestedDurationSeconds?: number
}) {
  const clipCap = seedanceClipCap(args.videoModel)
  const durationSeconds =
    args.requestedDurationSeconds ??
    (args.duration === 'auto'
      ? (extractChapterDurationFromPrompt(args.videoPrompt) ?? 90)
      : Number(args.duration))
  return {
    creative_studio_session_id: args.sessionId,
    media_mode: 'video',
    model: args.videoModel,
    prompt: args.videoPrompt,
    duration_seconds: durationSeconds,
    aspect: args.aspect,
    resolution: args.resolution,
    sound_on: args.soundOn,
    speech_mode: args.speechMode,
    product_name: args.productName || '',
    brand_name: args.brandName || '',
    negative_prompt: 'watermark, random unreadable text, UI chrome',
    seed_image_url: null,
    seed_image_role: 'first_frame',
    product_reference_url: args.productReferenceUrl || null,
    logo_reference_url: args.logoReferenceUrl || null,
    additional_reference_urls: args.additionalReferenceUrls,
    reference_assets: args.referenceAssets.map((asset) => ({
      url: asset.url,
      role: asset.role || 'reference',
    })),
    source_brief: args.videoPrompt,
    storyboard_scenes: [],
    storyboard_image_urls: [],
    prompt_only_video: args.promptOnlyVideo,
    interactive_staging: durationSeconds > clipCap,
  }
}

function formatChatTime(ts: number) {
  try {
    const date = new Date(ts)
    const now = new Date()
    const time = date.toLocaleString(undefined, {
      hour: '2-digit',
      minute: '2-digit',
    })
    const yesterday = new Date(now)
    yesterday.setDate(yesterday.getDate() - 1)
    if (date.toDateString() === now.toDateString()) return `Today · ${time}`
    if (date.toDateString() === yesterday.toDateString()) return `Yesterday · ${time}`
    return date.toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      ...(date.getFullYear() !== now.getFullYear() ? { year: 'numeric' as const } : {}),
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

function chatDateGroupLabel(ts: number) {
  const date = new Date(ts)
  const now = new Date()
  const yesterday = new Date(now)
  yesterday.setDate(yesterday.getDate() - 1)
  if (date.toDateString() === now.toDateString()) return 'Today'
  if (date.toDateString() === yesterday.toDateString()) return 'Yesterday'
  return date.toLocaleString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    ...(date.getFullYear() !== now.getFullYear() ? { year: 'numeric' as const } : {}),
  })
}

function groupSessionsByDate(sessions: CsChatSession[]) {
  const sorted = [...sessions].sort((a, b) => b.updatedAt - a.updatedAt)
  const groups: { label: string; sessions: CsChatSession[] }[] = []
  for (const session of sorted) {
    const label = chatDateGroupLabel(session.updatedAt)
    const last = groups[groups.length - 1]
    if (last?.label === label) last.sessions.push(session)
    else groups.push({ label, sessions: [session] })
  }
  return groups
}

function csSessionFieldsEqual(a: CsChatSession, b: CsChatSession): boolean {
  return (
    a.title === b.title &&
    a.imagePrompt === b.imagePrompt &&
    a.videoPrompt === b.videoPrompt &&
    a.approvedImageUrl === b.approvedImageUrl &&
    a.productReferenceUrl === b.productReferenceUrl &&
    a.logoReferenceUrl === b.logoReferenceUrl &&
    a.characterReferenceUrl === b.characterReferenceUrl &&
    JSON.stringify(a.additionalReferenceUrls) === JSON.stringify(b.additionalReferenceUrls) &&
    a.phase === b.phase &&
    (a.videoModel || '') === (b.videoModel || '') &&
    a.speechMode === b.speechMode &&
    a.promptOnlyVideo === b.promptOnlyVideo &&
    a.cloneMode === b.cloneMode &&
    a.cloneSceneId === b.cloneSceneId &&
    a.cloneCount === b.cloneCount &&
    JSON.stringify(a.messages) === JSON.stringify(b.messages)
  )
}

/** Only real usage (messages, approvals, refs) bumps last-used date — not opening a chat. */
function csSessionActivityChanged(before: CsChatSession, after: CsChatSession): boolean {
  return (
    JSON.stringify(before.messages) !== JSON.stringify(after.messages) ||
    before.phase !== after.phase ||
    before.approvedImageUrl !== after.approvedImageUrl ||
    before.imagePrompt !== after.imagePrompt ||
    before.videoPrompt !== after.videoPrompt ||
    before.productReferenceUrl !== after.productReferenceUrl ||
    before.logoReferenceUrl !== after.logoReferenceUrl ||
    before.characterReferenceUrl !== after.characterReferenceUrl ||
    JSON.stringify(before.additionalReferenceUrls) !== JSON.stringify(after.additionalReferenceUrls)
  )
}

export default function CreativeStudioTab({
  briefId,
  brandId: brandIdProp,
  briefTitle,
  brandName,
  productName,
  initialPrompt,
  seedance25Only: seedance25OnlyProp,
}: Props) {
  const { user } = useAuth()
  const seedance25Only = seedance25OnlyProp ?? isCsSeedance25Only(user)
  const {
    data: csModels,
    isLoading: catalogLoading,
    error: catalogError,
    refetch: refetchModels,
  } = useApi(
    () => generationApi.creativeStudioModels(),
    [],
    { cacheKey: 'generation/cs-models-v4-seedance25', ttlMs: 60_000 },
  )
  const { data: brands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands/list-cs',
    ttlMs: API_CACHE_TTL.catalog,
  })
  const { data: cloneCatalog } = useApi(
    () => generationApi.creativeStudioCloneScenes(),
    [],
    { cacheKey: 'generation/cs-clone-scenes-v1', ttlMs: API_CACHE_TTL.catalog },
  )

  const [pickedBrandId, setPickedBrandId] = useState(brandIdProp || '')
  const brandId = (brandIdProp || pickedBrandId || '').trim() || undefined
  const freshWorkspace = useMemo(() => {
    const bc = user?.brief_count
    const vc = user?.variant_count
    if (bc == null || vc == null) return false
    return bc === 0 && vc === 0
  }, [user?.brief_count, user?.variant_count])
  const historyScope = useMemo(
    () =>
      csHistoryScope(user?.id, briefId, brandId, {
        tenantId: user?.tenant_id,
        freshWorkspace,
      }),
    [user?.id, user?.tenant_id, freshWorkspace, briefId, brandId],
  )
  const selectedBrand = (brands || []).find((brand) => brand.id === brandId)
  const effectiveBrandName = brandName || selectedBrand?.name || ''

  const [sessions, setSessions] = useState<CsChatSession[]>([])
  const [activeChatId, setActiveChatId] = useState<string>('')
  const [sidebarOpen, setSidebarOpen] = useState(true)
  const [composerSettingsOpen, setComposerSettingsOpen] = useState(true)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [composer, setComposer] = useState(initialPrompt || '')
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const [chatModel, setChatModel] = useState('auto')
  const [mode, setMode] = useState<ChatMode>('auto')
  const [duration, setDuration] = useState<DurationId>('auto')
  const [aspect, setAspect] = useState<AspectId>('9/16')
  const [resolution, setResolution] = useState<ResolutionId>('720p')
  const [videoModel, setVideoModel] = useState('ark-seedance-2-0')
  const [soundOn, setSoundOn] = useState(true)
  const [speechMode, setSpeechMode] = useState<SpeechMode>('native_presenter')
  const [continuationReferenceMode, setContinuationReferenceMode] =
    useState<ContinuationReferenceMode>('continuity')
  const [useStoryboardReferences, setUseStoryboardReferences] = useState(false)
  // Direct Seedance remains the default. Image-first is opt-in so existing
  // chats keep their current cost and generation behaviour.
  const [promptOnlyVideo, setPromptOnlyVideo] = useState(true)
  const [cloneMode, setCloneMode] = useState(false)
  const [cloneSceneId, setCloneSceneId] = useState('')
  const [cloneCount, setCloneCount] = useState(4)
  const [busy, setBusy] = useState(false)
  const [modelMenuOpen, setModelMenuOpen] = useState(false)
  const [modeMenuOpen, setModeMenuOpen] = useState(false)
  const [hydrated, setHydrated] = useState(false)

  // Pipeline memory (Supercomputer stages)
  const [imagePrompt, setImagePrompt] = useState('')
  const [videoPrompt, setVideoPrompt] = useState('')
  const [approvedImageUrl, setApprovedImageUrl] = useState('')
  const [productReferenceUrl, setProductReferenceUrl] = useState('')
  const [logoReferenceUrl, setLogoReferenceUrl] = useState('')
  const [characterReferenceUrl, setCharacterReferenceUrl] = useState('')
  const [additionalReferenceUrls, setAdditionalReferenceUrls] = useState<string[]>([])
  const [imageLibraryOpen, setImageLibraryOpen] = useState(false)
  const [imageLibrary, setImageLibrary] = useState<Asset[]>([])
  const [imageLibraryLoading, setImageLibraryLoading] = useState(false)
  const [mediaLibrarySection, setMediaLibrarySection] = useState<MediaLibrarySection>('uploads')
  const [mediaLibraryFilter, setMediaLibraryFilter] = useState<MediaLibraryFilter>('recent')
  const [mediaLibrarySort, setMediaLibrarySort] = useState<MediaLibrarySort>('newest')
  const [likedAssetIds, setLikedAssetIds] = useState<string[]>([])
  const [phase, setPhase] = useState('')
  const [imageModel, setImageModel] = useState('openai-gpt-image-2')
  const [previewFrame, setPreviewFrame] = useState<{ src: string; title: string } | null>(
    null,
  )

  const threadRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const activeChatIdRef = useRef('')
  const stoppedJobsRef = useRef<Set<string>>(new Set())
  const pollingJobsRef = useRef<Set<string>>(new Set())
  const savingLibraryUrlsRef = useRef<Set<string>>(new Set())
  const skipNextHistorySaveRef = useRef(false)
  const viewOnlyChatIdRef = useRef<string | null>(null)
  const defaultVideoModelRef = useRef('dreamina-seedance-2-0-280128')
  const resumeCheckedSessionRef = useRef('')

  const chatModels = useMemo(
    () => (csModels?.chat_models || []) as GenerationModelOption[],
    [csModels],
  )
  const defaultChatModel = csModels?.default_chat_model || 'anthropic/claude-sonnet-4.6'
  const videoModels = useMemo(() => {
    const all = (csModels?.video_models || []) as GenerationModelOption[]
    if (!seedance25Only) return all
    return all.filter((m) => /2-5|2\.5/i.test(m.id))
  }, [csModels, seedance25Only])
  const imageModels = useMemo(
    () => (csModels?.image_models || []) as GenerationModelOption[],
    [csModels],
  )
  const clipCap = seedanceClipCap(videoModel)
  const imageModelLabelText = imageModelLabel(imageModel)
  const projectDurationSeconds = duration === 'auto' ? 90 : Number(duration)
  const videoModelLabel = seedanceModelLabel(videoModel)
  const pendingContinuationMessage = useMemo(
    () =>
      [...messages]
        .reverse()
        .find(
          (message) =>
            Boolean(message.jobId) &&
            (message.suggestedActions?.includes('continue_video') ||
              isChapterHandoffReady(
                message,
                message.continuationMeta?.requested_duration_seconds ??
                  projectDurationSeconds,
                clipCap,
              )),
        ),
    [messages, projectDurationSeconds, clipCap],
  )
  const selectedChatLabel = useMemo(() => {
    if (chatModel === 'auto') return 'Auto'
    return chatModels.find((m) => m.id === chatModel)?.label || chatModel
  }, [chatModel, chatModels])

  useEffect(() => {
    if (!seedance25Only) return
    const preferred =
      csModels?.video_model_default && /2-5|2\.5/i.test(csModels.video_model_default)
        ? csModels.video_model_default
        : CS25_DEFAULT_VIDEO_MODEL
    setVideoModel(preferred)
  }, [seedance25Only, csModels?.video_model_default])

  const applySession = useCallback((session: CsChatSession) => {
    const storedMessages = session.messages || []
    const recoveredNarrationFailure = storedMessages.some(
      (message) =>
        message.status === 'failed' &&
        /narration at .*exceeds .*shorter deliveries/i.test(message.error || ''),
    )
    const restoredMessages = storedMessages.map((message) => {
      if (
        message.status !== 'failed' ||
        !/narration at .*exceeds .*shorter deliveries/i.test(message.error || '')
      ) {
        return message
      }
      return {
        ...message,
        content:
          'The previous narration timing issue has been fixed. Your approved still is preserved; retry Seedance to continue.',
        status: 'idle' as const,
        error: undefined,
        mediaMode: 'video' as const,
        suggestedActions: ['generate_video' as const],
        phase: 'awaiting_video',
      }
    })
    activeChatIdRef.current = session.id
    setActiveChatId(session.id)
    setMessages(restoredMessages)
    setImagePrompt(session.imagePrompt || '')
    setVideoPrompt(session.videoPrompt || '')
    setApprovedImageUrl(session.approvedImageUrl || '')
    setProductReferenceUrl(session.productReferenceUrl || '')
    setLogoReferenceUrl(session.logoReferenceUrl || '')
    setCharacterReferenceUrl(session.characterReferenceUrl || '')
    setAdditionalReferenceUrls(session.additionalReferenceUrls || [])
    setPhase(
      recoveredNarrationFailure && session.approvedImageUrl
        ? 'awaiting_video'
        : session.phase || '',
    )
    if (session.videoModel) setVideoModel(session.videoModel)
    setSpeechMode(session.speechMode || 'native_presenter')
    setPromptOnlyVideo(session.promptOnlyVideo !== false)
    setCloneMode(Boolean(session.cloneMode))
    setCloneSceneId(session.cloneSceneId || '')
    setCloneCount(Math.max(2, Math.min(6, session.cloneCount || 4)))
    setAttachments([])
    setComposer('')
  }, [])

  useEffect(() => {
    if (brandIdProp) setPickedBrandId(brandIdProp)
  }, [brandIdProp])

  useEffect(() => {
    if (csModels?.image_model_default) setImageModel(csModels.image_model_default)
  }, [csModels?.image_model_default])

  useEffect(() => {
    if (csModels?.video_model_default) {
      defaultVideoModelRef.current = csModels.video_model_default
      setVideoModel((current) => current || csModels.video_model_default!)
    }
  }, [csModels?.video_model_default])

  useEffect(() => {
    if (!user?.id) {
      setSessions([])
      setHydrated(false)
      return
    }
    if (user.brief_count == null || user.variant_count == null) {
      return
    }
    skipNextHistorySaveRef.current = true
    setHydrated(false)
    const loaded = loadCsChatSessions(historyScope)
    let list = loaded
    let activeId = getCsActiveChatId(historyScope)
    let current = list.find((s) => s.id === activeId)
    if (!current) {
      if (list.length === 0) {
        current = {
          ...emptyCsSession(),
          historyBrandId: brandId,
          historyBriefId: briefId,
        }
        list = [current]
        persistCsChatSession(historyScope, current)
      } else {
        current = list[0]
      }
      activeId = current.id
      const activeScope = sessionStorageScope(historyScope, {
        ...current,
        historyBrandId: current.historyBrandId ?? brandId,
        historyBriefId: current.historyBriefId ?? briefId,
      })
      setCsActiveChatId(activeScope, activeId)
    }
    setSessions(list)
    applySession(current)
    setHydrated(true)
  }, [
    historyScope,
    user?.id,
    user?.brief_count,
    user?.variant_count,
    applySession,
    briefId,
    brandId,
  ])

  useEffect(() => {
    if (!hydrated || !activeChatId) return
    if (skipNextHistorySaveRef.current) {
      skipNextHistorySaveRef.current = false
      return
    }
    setSessions((prev) => {
      const existing = prev.find((s) => s.id === activeChatId)
      const messagesUnchanged =
        existing && JSON.stringify(existing.messages) === JSON.stringify(messages)
      const title =
        messagesUnchanged && existing?.title
          ? existing.title
          : messages.length > 0
          ? titleFromMessages(messages)
          : existing?.title && existing.title !== 'New chat'
            ? existing.title
            : 'New chat'
      const nextSession: CsChatSession = {
        id: activeChatId,
        title,
        createdAt: existing?.createdAt || Date.now(),
        updatedAt: existing?.updatedAt || Date.now(),
        messages,
        imagePrompt,
        videoPrompt,
        approvedImageUrl,
        productReferenceUrl,
        logoReferenceUrl,
        characterReferenceUrl,
        additionalReferenceUrls,
        phase,
        videoModel,
        speechMode,
        promptOnlyVideo,
        cloneMode,
        cloneSceneId,
        cloneCount,
      }
      if (existing && csSessionFieldsEqual(existing, nextSession)) {
        viewOnlyChatIdRef.current = null
        return prev
      }
      const openedForViewOnly = viewOnlyChatIdRef.current === activeChatId
      if (openedForViewOnly) viewOnlyChatIdRef.current = null
      const activityChanged =
        Boolean(existing) &&
        csSessionActivityChanged(existing!, nextSession) &&
        !openedForViewOnly
      const savedSession: CsChatSession = {
        ...nextSession,
        updatedAt: activityChanged ? Date.now() : existing?.updatedAt || Date.now(),
      }
      const tagged: CsChatSession = {
        ...savedSession,
        historyBrandId: existing?.historyBrandId ?? brandId,
        historyBriefId: existing?.historyBriefId ?? briefId,
      }
      persistCsChatSession(historyScope, tagged)
      const activeScope = sessionStorageScope(historyScope, tagged)
      setCsActiveChatId(activeScope, activeChatId)
      const next = activityChanged
        ? [{ ...tagged, updatedAt: tagged.updatedAt }, ...prev.filter((s) => s.id !== activeChatId)]
        : [...prev.map((s) => (s.id === activeChatId ? { ...tagged } : s))].sort(
            (a, b) => b.updatedAt - a.updatedAt,
          )
      return next
    })
  }, [
    messages,
    imagePrompt,
    videoPrompt,
    approvedImageUrl,
    productReferenceUrl,
    logoReferenceUrl,
    characterReferenceUrl,
    additionalReferenceUrls,
    phase,
    videoModel,
    speechMode,
    promptOnlyVideo,
    cloneMode,
    cloneSceneId,
    cloneCount,
    activeChatId,
    historyScope,
    hydrated,
    brandId,
    briefId,
  ])

  useEffect(() => {
    if (!threadRef.current) return
    threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [messages, busy])

  const startNewChat = () => {
    const session: CsChatSession = {
      ...emptyCsSession(),
      historyBrandId: brandId,
      historyBriefId: briefId,
    }
    setSessions((prev) => {
      persistCsChatSession(historyScope, session)
      return [session, ...prev]
    })
    setCsActiveChatId(sessionStorageScope(historyScope, session), session.id)
    applySession(session)
  }

  const switchChat = (id: string) => {
    if (id === activeChatId) return
    const session = sessions.find((s) => s.id === id)
    if (!session) return
    viewOnlyChatIdRef.current = id
    setCsActiveChatId(sessionStorageScope(historyScope, session), id)
    applySession(session)
  }

  const sessionGroups = useMemo(() => groupSessionsByDate(sessions), [sessions])

  const deleteChat = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation()
    const target = sessions.find((s) => s.id === id)
    if (target) removeCsChatSession(historyScope, target)
    const remaining = sessions.filter((s) => s.id !== id)
    if (remaining.length === 0) {
      const fresh: CsChatSession = {
        ...emptyCsSession(),
        historyBrandId: brandId,
        historyBriefId: briefId,
      }
      persistCsChatSession(historyScope, fresh)
      setSessions([fresh])
      setCsActiveChatId(sessionStorageScope(historyScope, fresh), fresh.id)
      applySession(fresh)
      return
    }
    setSessions(remaining)
    if (id === activeChatId) {
      setCsActiveChatId(sessionStorageScope(historyScope, remaining[0]), remaining[0].id)
      applySession(remaining[0])
    }
  }

  const updateMessage = useCallback((id: string, patch: Partial<ChatMessage>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)))
  }, [])

  const loadImageLibrary = useCallback(async () => {
    setImageLibraryLoading(true)
    try {
      const assets = await assetsApi.list({
        asset_type: 'creative_studio_reference',
      })
      setImageLibrary(assets)
    } catch (err) {
      toast.error(extractApiError(err, 'Could not load saved images'))
    } finally {
      setImageLibraryLoading(false)
    }
  }, [])

  useEffect(() => {
    if (imageLibraryOpen) void loadImageLibrary()
  }, [imageLibraryOpen, loadImageLibrary])

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(
        'creative-studio-liked-media',
      )
      setLikedAssetIds(stored ? JSON.parse(stored) : [])
    } catch {
      setLikedAssetIds([])
    }
  }, [])

  useEffect(() => {
    if (!imageLibraryOpen) return
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setImageLibraryOpen(false)
    }
    window.addEventListener('keydown', closeOnEscape)
    return () => window.removeEventListener('keydown', closeOnEscape)
  }, [imageLibraryOpen])

  const visibleLibraryAssets = useMemo(() => {
    const isGenerated = (asset: Asset) =>
      asset.metadata?.source === 'creative_studio_generated'
    let assets = imageLibrary.filter((asset) => {
      if (mediaLibrarySection === 'generations') return isGenerated(asset)
      if (mediaLibrarySection === 'characters') return asset.metadata?.role === 'character'
      if (mediaLibrarySection === 'liked') return likedAssetIds.includes(asset.id)
      return mediaLibraryFilter === 'recent' ? true : !isGenerated(asset)
    })
    if (mediaLibraryFilter === 'images') {
      assets = assets.filter((asset) => asset.file_type.startsWith('image/'))
    } else if (mediaLibraryFilter === 'videos') {
      assets = assets.filter((asset) => asset.file_type.startsWith('video/'))
    } else if (mediaLibraryFilter === 'audio') {
      assets = assets.filter((asset) => asset.file_type.startsWith('audio/'))
    }
    assets = [...assets].sort((a, b) => {
      if (mediaLibrarySort === 'name') return a.file_name.localeCompare(b.file_name)
      const direction = mediaLibrarySort === 'oldest' ? 1 : -1
      return direction * String(a.created_at).localeCompare(String(b.created_at))
    })
    return mediaLibraryFilter === 'recent' ? assets.slice(0, 30) : assets
  }, [imageLibrary, likedAssetIds, mediaLibraryFilter, mediaLibrarySection, mediaLibrarySort])

  const storeGeneratedImages = useCallback(
    async (
      images: Array<{ url: string; title: string; role: 'still' | 'storyboard' | 'character' }>,
      jobId: string,
    ) => {
      const fresh = images.filter(
        (image) => image.url && !savingLibraryUrlsRef.current.has(image.url),
      )
      if (!fresh.length) return
      fresh.forEach((image) => savingLibraryUrlsRef.current.add(image.url))
      try {
        const saved = await Promise.all(
          fresh.map((image) =>
            assetsApi.registerGenerated({
              file_url: image.url,
              brand_id: brandId,
              file_name: image.title,
              metadata: {
                role: image.role,
                title: image.title,
                creative_studio_job_id: jobId,
              },
            }),
          ),
        )
        setImageLibrary((current) => {
          const byId = new Map(current.map((asset) => [asset.id, asset]))
          saved.forEach((asset) => byId.set(asset.id, asset))
          return Array.from(byId.values()).sort((a, b) =>
            String(b.created_at).localeCompare(String(a.created_at)),
          )
        })
      } catch (err) {
        console.warn('Could not save generated Creative Studio image', err)
      } finally {
        fresh.forEach((image) => savingLibraryUrlsRef.current.delete(image.url))
      }
    },
    [brandId],
  )

  const patchStoryboardFrame = useCallback(
    (messageId: string, frameId: string, patch: Partial<NonNullable<ChatMessage['storyboard']>[number]>) => {
      setMessages((prev) =>
        prev.map((message) => {
          if (message.id !== messageId || !message.storyboard) return message
          return {
            ...message,
            storyboard: message.storyboard.map((frame) =>
              frame.id === frameId ? { ...frame, ...patch } : frame,
            ),
          }
        }),
      )
    },
    [],
  )

  const regenerateBrollFrame = useCallback(
    async (
      boardMessage: ChatMessage,
      frame: NonNullable<ChatMessage['storyboard']>[number],
    ) => {
      if (!frame.index || busy) return
      patchStoryboardFrame(boardMessage.id, frame.id, { url: undefined, status: 'running' })
      setBusy(true)
      try {
        const historyForApi = messages
          .filter((m) => m.role === 'user' || m.role === 'assistant')
          .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))
        const res = await generationApi.creativeStudioChat({
          session_id: activeChatId,
          messages: historyForApi,
          mode,
          chat_model: chatModel,
          duration_seconds: duration === 'auto' ? undefined : Number(duration),
          aspect,
          resolution,
          sound_on: soundOn,
          speech_mode: speechMode,
          brand_name: effectiveBrandName,
          product_name: productName || '',
          action: 'regenerate_broll_image',
          image_model: imageModel,
          video_model: videoModel,
          broll_index: frame.index,
          logo_reference_url: logoReferenceUrl || selectedBrand?.logo_url || '',
          reference_assets: messages
            .flatMap((m) => m.attachments || [])
            .filter((a) => a.role)
            .map((a) => ({ url: a.url, role: a.role || 'reference' }))
            .slice(0, 9),
        })
        const jobId = res.job_id
        if (!jobId) {
          toast.error(res.error || 'Could not start B-roll regeneration')
          patchStoryboardFrame(boardMessage.id, frame.id, { status: 'failed' })
          return
        }
        const deadline = Date.now() + 20 * 60 * 1000
        while (Date.now() < deadline) {
          await new Promise((r) => setTimeout(r, 4000))
          const poll = await generationApi.creativeStudioJob(jobId)
          if (poll.status === 'done' || poll.status === 'mock') {
            const url = poll.url || ''
            patchStoryboardFrame(boardMessage.id, frame.id, {
              url: url || undefined,
              status: 'done',
            })
            if (url) {
              void storeGeneratedImages(
                [{ url, title: frame.title || `IMAGE ${frame.index}`, role: 'still' }],
                jobId,
              )
            }
            toast.success(`IMAGE ${frame.index} regenerated — review text, then approve`)
            return
          }
          if (poll.status === 'failed' || poll.status === 'cancelled') {
            patchStoryboardFrame(boardMessage.id, frame.id, {
              status: 'failed',
              url: undefined,
            })
            toast.error(poll.error || 'B-roll regeneration failed')
            return
          }
        }
        toast.error('B-roll regeneration timed out')
      } catch (err) {
        patchStoryboardFrame(boardMessage.id, frame.id, { status: 'failed' })
        toast.error(extractApiError(err, 'B-roll regeneration failed'))
      } finally {
        setBusy(false)
      }
    },
    [
      activeChatId,
      aspect,
      busy,
      chatModel,
      duration,
      effectiveBrandName,
      imageModel,
      logoReferenceUrl,
      messages,
      mode,
      patchStoryboardFrame,
      productName,
      resolution,
      selectedBrand?.logo_url,
      soundOn,
      speechMode,
      storeGeneratedImages,
      videoModel,
    ],
  )

  const pollJobIntoMessage = useCallback(
    async (
      jobId: string,
      assistantMsgId: string,
      mediaMode: 'image' | 'video' | 'storyboard' | 'broll_board',
      sessionId = activeChatId,
    ) => {
      if (pollingJobsRef.current.has(jobId)) return
      pollingJobsRef.current.add(jobId)
      const patchMessage = (
        patch:
          | Partial<ChatMessage>
          | ((current: ChatMessage | undefined) => Partial<ChatMessage>),
      ) => {
        const applyPatch = (
          message: ChatMessage,
          resolved: Partial<ChatMessage>,
        ): ChatMessage => ({ ...message, ...resolved })

        if (!sessionId || sessionId === activeChatIdRef.current) {
          setMessages((prev) =>
            prev.map((message) => {
              if (message.id !== assistantMsgId) return message
              const resolved =
                typeof patch === 'function' ? patch(message) : patch
              return applyPatch(message, resolved)
            }),
          )
          return
        }
        setSessions((previous) => {
          const next = previous.map((session) =>
            session.id === sessionId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map((message) => {
                    if (message.id !== assistantMsgId) return message
                    const resolved =
                      typeof patch === 'function' ? patch(message) : patch
                    return applyPatch(message, resolved)
                  }),
                }
              : session,
          )
          const touched = next.find((s) => s.id === sessionId)
          if (touched) persistCsChatSession(historyScope, touched)
          return next
        })
      }
      const deadline =
        Date.now() +
        Math.max(90 * 60 * 1000, (duration === 'auto' ? 600 : Number(duration)) * 90 * 1000)
      while (Date.now() < deadline) {
        if (stoppedJobsRef.current.has(jobId)) {
          patchMessage({
            status: 'cancelled',
            progress: 'Stopped',
            error: 'Cancelled by user',
            suggestedActions: mediaMode === 'video' ? ['generate_video'] : ['generate_image'],
          })
          return
        }
        await new Promise((r) => setTimeout(r, 4000))
        if (stoppedJobsRef.current.has(jobId)) {
          patchMessage({
            status: 'cancelled',
            progress: 'Stopped',
            error: 'Cancelled by user',
          })
          return
        }
        try {
          const res = await generationApi.creativeStudioJob(jobId)
          const done = res.status === 'done' || res.status === 'mock'
          const failed = res.status === 'failed'
          const cancelled = res.status === 'cancelled'
          if (failed && res.clone_mode && res.character_reference_url) {
            void storeGeneratedImages(
              [{
                url: res.character_reference_url,
                title: 'Reusable character identity',
                role: 'character',
              }],
              jobId,
            )
            setCharacterReferenceUrl(res.character_reference_url)
          }
          const board = (res.storyboard || [])
            .filter((f) => f && (f.url || f.title))
            .map((f, i) => ({
              id: String(f.id || `scene-${i + 1}`),
              index: f.index || i + 1,
              title: f.title || `Scene ${i + 1}`,
              url: f.url || undefined,
              byteplusUrl: (f as { byteplus_url?: string }).byteplus_url || undefined,
              imagePrompt: f.image_prompt || undefined,
              overlays: f.overlays || [],
              status: f.status || undefined,
              selected: f.url ? true : undefined,
              discarded: false,
            }))

          patchMessage((current) => {
            const brollIndex =
              typeof res.broll_index === 'number' ? res.broll_index : current?.brollIndex
            const imageDone =
              done &&
              (mediaMode === 'image' || mediaMode === 'storyboard' || mediaMode === 'broll_board') &&
              Boolean(res.url || board.some((b) => b.url))
            const brollBoardReady =
              done && mediaMode === 'broll_board' && board.some((b) => b.url)
            const suggestedActions: PipelineAction[] =
              (done || failed) && mediaMode === 'video' && res.continuation_available
                ? ['continue_video']
                : done && mediaMode === 'video' && res.retry_chapter_available
                ? ['generate_video']
                : done && mediaMode === 'video' && res.next_chapter_image_available
                  ? ['approve_next']
                  : done && mediaMode === 'video' && res.continuation_available
                    ? ['continue_video']
                    : brollBoardReady
                      ? ['approve_all_broll']
                      : imageDone
                        ? brollIndex
                          ? ['regenerate_image', 'approve_broll']
                          : ['regenerate_image', 'approve_next']
                        : failed || cancelled
                          ? mediaMode === 'video'
                            ? ['generate_video']
                            : mediaMode === 'broll_board'
                              ? ['generate_all_broll']
                              : ['generate_image']
                          : []
            return {
            status: (res.status as ChatMessage['status']) || 'running',
            progress: res.progress || undefined,
            mediaUrl: res.url || undefined,
              byteplusUrl: res.byteplus_url || undefined,
            seedImageUrl: res.seed_image_url || undefined,
            model: res.model || undefined,
            error: res.error || undefined,
            durationSeconds: res.duration_seconds || undefined,
            ...(done && mediaMode === 'video' && res.note
              ? {
                    content: `${
                      res.next_chapter_image_available
                        ? 'Chapter ready for review.'
                        : res.audio_warning
                          ? 'Video ready with audio issues.'
                          : res.continuation_available
                            ? 'Video part ready for review.'
                            : res.partial
                              ? 'Partial video ready.'
                              : 'Video ready.'
                    } ${res.note}`,
                }
              : {}),
              storyboard:
                mediaMode === 'broll_board' || mediaMode === 'storyboard'
                  ? mergeStoryboardFrames(current?.storyboard, board)
                  : board.length
                    ? board
                    : current?.storyboard,
            mediaMode:
                mediaMode === 'broll_board' || res.media_mode === 'broll_board'
                  ? 'broll_board'
                  : mediaMode === 'storyboard' || res.media_mode === 'storyboard'
                ? 'storyboard'
                : mediaMode,
              suggestedActions,
              phase: failed && mediaMode === 'video' && res.continuation_available
                ? 'awaiting_video_continuation'
                : done
              ? mediaMode === 'video'
                  ? res.next_chapter_image_available
                    ? 'awaiting_chapter_image'
                    : res.continuation_available
                      ? 'awaiting_video_continuation'
                      : 'done'
                  : mediaMode === 'broll_board' || brollIndex
                    ? 'awaiting_broll'
                : 'awaiting_video'
              : failed || cancelled
                ? cancelled
                  ? 'cancelled'
                  : 'failed'
                  : mediaMode === 'broll_board'
                    ? 'broll_board_running'
                : mediaMode === 'storyboard'
                  ? 'storyboard_running'
                  : mediaMode === 'image'
                    ? 'image_running'
                    : 'video_running',
              ...(brollIndex ? { brollIndex } : {}),
              ...((done || failed) &&
              (res.continuation_available || res.next_chapter_image_available) &&
              res.completed_segments &&
              res.segment_count
                ? {
                    continuationMeta: {
                      completed_segments: res.completed_segments,
                      segment_count: res.segment_count,
                      generated_duration_seconds: res.duration_seconds || undefined,
                      requested_duration_seconds: res.requested_duration_seconds || undefined,
                      continuity_frame_count: res.continuity_frame_count || undefined,
                      production_id: res.production_id || undefined,
                      continuity_video_reference_url: res.continuity_video_reference_url || undefined,
                      continuity_reference_url: res.continuity_reference_url || undefined,
                      staged_segment_paths: res.staged_segment_paths || undefined,
                      chapter_index:
                        typeof res.chapter_index === 'number'
                          ? res.chapter_index
                          : res.completed_segments,
                      film_total_chapters: res.film_total_chapters || res.segment_count,
                    },
                  }
                : {}),
            }
          })
          if (cancelled) {
            toast('Generation stopped', { id: 'cs-stop' })
            setBusy(false)
            return
          }
          if (done && (res.url || board.some((b) => b.url)) && mediaMode !== 'video') {
            const imagesToStore =
              mediaMode === 'storyboard' || mediaMode === 'broll_board'
                ? board
                    .filter((frame) => frame.url)
                    .map((frame) => ({
                      url: frame.url as string,
                      title: frame.title || `Scene ${frame.index}`,
                      role: mediaMode === 'broll_board' ? ('still' as const) : ('storyboard' as const),
                    }))
                : res.clone_mode && res.url
                  ? [
                      ...(res.character_reference_url && res.character_reference_url !== res.url
                        ? [{
                            url: res.character_reference_url,
                            title: 'Reusable character identity',
                            role: 'character' as const,
                          }]
                        : []),
                      {
                        url: res.url,
                        title: 'Reusable character clone',
                        role: 'character' as const,
                      },
                    ]
                : res.url
                  ? [
                      {
                        url: res.url,
                        title: 'Creative Studio still',
                        role: 'still' as const,
                      },
                    ]
                  : []
            void storeGeneratedImages(imagesToStore, jobId)
            if (res.clone_mode && res.url) {
              setCharacterReferenceUrl(res.character_reference_url || res.url)
              setMediaLibrarySection('characters')
            }
            if (mediaMode === 'broll_board') {
              setPhase('awaiting_broll')
              toast.success(
                `B-roll board ready — ${board.filter((b) => b.url).length} still(s). Regenerate any wrong dashboard, then Approve all.`,
              )
              return
            }
            const hero =
              board.find((b) => /reveal|feature|close|product/i.test(b.title || ''))?.url ||
              board.find((b) => b.url)?.url ||
              res.url
            if (hero) setApprovedImageUrl(hero)
            setPhase('awaiting_video')
            toast.success(
              mediaMode === 'storyboard'
                ? `Storyboard ready — ${board.filter((b) => b.url).length} scenes. Approve & Next for video.`
                : res.clone_mode
                  ? 'Clone image ready and saved under Characters for reuse.'
                : 'Still ready — Approve & Next, or Regenerate',
            )
            return
          }
          if (done && res.url && mediaMode === 'video') {
            if (res.retry_chapter_available) {
              setPhase('awaiting_video_retry')
              toast.error('This chapter failed continuity QA. Regenerate retries only this chapter.', {
                duration: 9000,
              })
              return
            }
            setPhase(res.continuation_available ? 'awaiting_video_continuation' : 'done')
            const warn = res.duration_warning || res.note || ''
            if (res.audio_warning) {
              toast.error(res.audio_warning, { duration: 9000 })
              return
            }
            if (res.continuation_available) {
              toast.success('Video part ready — review it, then generate the next part', {
                duration: 7000,
              })
              return
            }
            if (res.partial) {
              toast.error('Partial video saved — one or more segments failed', { duration: 7000 })
              return
            }
            if (warn && /text-to-video|product identity is prompt-guided/i.test(warn)) {
              patchMessage({
                content:
                  'Video ready. Note: BytePlus blocked attaching the still (privacy filter on photoreal faces) — ' +
                  'continued as text-to-video. Not a content violation.',
              })
              toast.success('Video ready (text-to-video fallback)', { duration: 5000 })
            } else {
              toast.success('Video ready')
            }
            return
          }
          if (failed) {
            const err = res.error || 'Generation failed'
            toast.error(err, { duration: 7000 })
            return
          }
        } catch (pollErr) {
          const pollMessage = extractApiError(pollErr, 'Connection error')
          const pollStatus = (
            pollErr as { response?: { status?: number } }
          )?.response?.status
          if (pollStatus === 404 || /job not found|server may have restarted|\b404\b|not found/i.test(pollMessage)) {
            patchMessage({
              status: 'failed',
              progress: 'Generation interrupted',
              error:
                'This generation stopped when the backend restarted. Start a new generation; no further segments are being submitted.',
              suggestedActions: mediaMode === 'video' ? ['generate_video'] : ['generate_image'],
            })
            setBusy(false)
            toast.error('Generation was interrupted by a backend restart')
            return
          }
          // Transient DB/auth glitches — keep waiting; show soft status
          patchMessage({
            progress: 'Still working… (connection blip, retrying poll)',
          })
          console.warn('Creative Studio job poll failed', pollErr)
        }
      }
      patchMessage({
        status: 'failed',
        error: 'Timed out waiting for generation.',
        suggestedActions: mediaMode === 'video' ? ['generate_video'] : ['generate_image'],
      })
    },
    [activeChatId, brandId, briefId, storeGeneratedImages, updateMessage],
  )

  useEffect(() => {
    if (!hydrated || !activeChatId) return
    const resumeKey = `${brandId || briefId || 'draft'}:${activeChatId}`
    if (resumeCheckedSessionRef.current === resumeKey) return
    resumeCheckedSessionRef.current = resumeKey
    for (const message of messages) {
      if (
        message.jobId &&
        (message.status === 'queued' || message.status === 'running')
      ) {
        void pollJobIntoMessage(
          message.jobId,
          message.id,
          message.mediaMode || 'video',
        )
      }
    }
  }, [
    activeChatId,
    brandId,
    briefId,
    hydrated,
    messages,
    pollJobIntoMessage,
  ])

  const stopGeneration = async (msg: ChatMessage) => {
    const jobId = msg.jobId
    if (!jobId) return
    stoppedJobsRef.current.add(jobId)
    updateMessage(msg.id, {
      status: 'cancelled',
      progress: 'Stopping…',
      error: 'Cancelled by user',
      suggestedActions: [],
    })
    try {
      await generationApi.creativeStudioCancelJob(jobId)
      toast.success('Stopped', { id: 'cs-stop' })
    } catch (err) {
      toast.error(extractApiError(err, 'Could not stop job'), { id: 'cs-stop' })
    } finally {
      setBusy(false)
    }
  }

  const handleAttach = async (files: FileList | null) => {
    if (!files?.length) return
    const remaining = Math.max(0, 9 - attachments.length)
    let productAssigned = Boolean(productReferenceUrl)
    for (const file of Array.from(files).slice(0, remaining)) {
      try {
        // Creative Studio attachments are persisted for generation, but must
        // never appear in the image-brief Brand Kit reference library.
        const asset = await assetsApi.upload(
          file,
          undefined,
          'creative_studio_reference',
          brandId,
        )
        const url = asset.file_url || ''
        if (!url) throw new Error('Upload returned no URL')
        const role: ChatAttachment['role'] = cloneMode
          ? 'character'
          : /logo|wordmark|brandmark/i.test(file.name)
            ? 'logo'
            : pendingContinuationMessage
              ? 'reference'
            : !productAssigned
              ? 'product'
              : 'reference'
        setImageLibrary((current) => [
          asset,
          ...current.filter((item) => item.id !== asset.id),
        ])
        setAttachments((prev) => [
          ...prev,
          {
            id: asset.id || uid(),
            name: file.name,
            url,
            previewUrl: assetUrl(url) || undefined,
            mime: file.type,
            role,
          },
        ])
        if (role === 'product') {
          setProductReferenceUrl(url)
          productAssigned = true
        }
        if (role === 'logo') setLogoReferenceUrl(url)
        if (role === 'character') {
          setCharacterReferenceUrl(url)
          void assetsApi.updateMetadata(asset.id, { role: 'character', reusable: true }).then(
            (saved) => setImageLibrary((current) => [
              saved,
              ...current.filter((item) => item.id !== saved.id),
            ]),
          ).catch(() => undefined)
        }
        if (role === 'reference') {
          setAdditionalReferenceUrls((prev) =>
            Array.from(new Set([...prev, url])).slice(0, 7),
          )
        }
        toast.success(`${role === 'logo' ? 'Logo' : role === 'product' ? 'Product' : role === 'character' ? 'Character' : 'Reference'} image attached`)
      } catch (err) {
        toast.error(extractApiError(err, `Could not upload ${file.name}`))
      }
    }
    if (fileInputRef.current) fileInputRef.current.value = ''
  }

  const setAttachmentRole = (attachment: ChatAttachment, role: ChatAttachment['role']) => {
    setAttachments((prev) => {
      const demoted = prev.filter(
        (item) =>
          item.id !== attachment.id &&
          (role === 'product' || role === 'logo') &&
          item.role === role,
      )
      if (demoted.length) {
        setAdditionalReferenceUrls((urls) =>
          Array.from(new Set([...urls, ...demoted.map((item) => item.url)])).slice(0, 7),
        )
      }
      return prev.map((item) => {
        if (item.id === attachment.id) return { ...item, role }
        if ((role === 'product' || role === 'logo') && item.role === role) {
          return { ...item, role: 'reference' as const }
        }
        return item
      })
    })
    if (productReferenceUrl === attachment.url) setProductReferenceUrl('')
    if (logoReferenceUrl === attachment.url) setLogoReferenceUrl('')
    if (characterReferenceUrl === attachment.url) setCharacterReferenceUrl('')
    setAdditionalReferenceUrls((prev) => prev.filter((url) => url !== attachment.url))
    if (role === 'product') setProductReferenceUrl(attachment.url)
    if (role === 'logo') setLogoReferenceUrl(attachment.url)
    if (role === 'character') setCharacterReferenceUrl(attachment.url)
    void assetsApi.updateMetadata(attachment.id, { role, reusable: true }).then(
      (saved) => setImageLibrary((current) => [
        saved,
        ...current.filter((item) => item.id !== saved.id),
      ]),
    ).catch(() => undefined)
    if (role === 'reference') {
      setAdditionalReferenceUrls((prev) =>
        Array.from(new Set([...prev, attachment.url])).slice(0, 7),
      )
    }
  }

  const removeAttachment = (attachment: ChatAttachment) => {
    setAttachments((prev) => {
      const next = prev.filter((item) => item.id !== attachment.id)
      if (characterReferenceUrl === attachment.url) {
        setCharacterReferenceUrl(next.find((item) => item.role === 'character')?.url || '')
      }
      return next
    })
    if (productReferenceUrl === attachment.url) setProductReferenceUrl('')
    if (logoReferenceUrl === attachment.url) setLogoReferenceUrl('')
    setAdditionalReferenceUrls((prev) => prev.filter((url) => url !== attachment.url))
  }

  const attachLibraryAsset = (asset: Asset, preferredRole?: ChatAttachment['role']) => {
    const url = asset.file_url || ''
    if (!url) return
    const allowedRoles: ChatAttachment['role'][] = [
      'product',
      'logo',
      'scene',
      'character',
      'reference',
    ]
    const metadataRole = String(asset.metadata?.role || '') as ChatAttachment['role']
    const role = preferredRole || (allowedRoles.includes(metadataRole) ? metadataRole : 'reference')
    const attachment: ChatAttachment = {
      id: asset.id,
      name: asset.file_name || 'Saved image',
      url,
      previewUrl: assetUrl(url) || undefined,
      mime: asset.file_type,
      role,
    }
    setAttachments((current) => {
      const withoutUrl = current.filter((item) => item.url !== url)
      const withoutDuplicateRole = withoutUrl.map((item) =>
        (role === 'product' || role === 'logo') && item.role === role
          ? { ...item, role: 'reference' as const }
          : item,
      )
      return [...withoutDuplicateRole, attachment].slice(-9)
    })
    if (role === 'product') setProductReferenceUrl(url)
    if (role === 'logo') setLogoReferenceUrl(url)
    if (role === 'character') setCharacterReferenceUrl(url)
    void assetsApi.updateMetadata(asset.id, { role, reusable: true }).then(
      (saved) => setImageLibrary((current) => [
        saved,
        ...current.filter((item) => item.id !== saved.id),
      ]),
    ).catch(() => undefined)
    if (role === 'reference') {
      setAdditionalReferenceUrls((current) =>
        Array.from(new Set([...current, url])).slice(-7),
      )
    }
  }

  const toggleLikedAsset = (assetId: string) => {
    setLikedAssetIds((current) => {
      const next = current.includes(assetId)
        ? current.filter((id) => id !== assetId)
        : [...current, assetId]
      try {
        window.localStorage.setItem(
          'creative-studio-liked-media',
          JSON.stringify(next),
        )
      } catch {
        // The picker still works when browser storage is unavailable.
      }
      return next
    })
  }

  const toggleLibraryAttachment = (asset: Asset) => {
    const existing = attachments.find((attachment) => attachment.url === asset.file_url)
    if (existing) {
      removeAttachment(existing)
      return
    }
    if (!asset.file_type.startsWith('image/')) {
      toast.error('Seedance reference selection currently supports images')
      return
    }
    attachLibraryAsset(asset)
  }

  const saveToVariants = async (msg: ChatMessage) => {
    if (!msg.mediaUrl) return
    try {
      const variant = await variantsApi.createFromMedia({
        media_url: msg.mediaUrl,
        media_mode: msg.mediaMode === 'broll_board' ? 'storyboard' : (msg.mediaMode || 'video'),
        aspect,
        model: msg.model || (msg.mediaMode === 'image' ? imageModel : videoModel),
        prompt: msg.videoPrompt || msg.imagePrompt || msg.content,
        duration_seconds: msg.durationSeconds,
        seed_image_url: msg.seedImageUrl || approvedImageUrl || null,
        brief_id: briefId || undefined,
        brand_id: brandId || undefined,
        brief_title: briefTitle || brandName || UI.aiAssistant,
        product_name: productName || '',
      })
      updateMessage(msg.id, { variantId: variant.id })
      toast.success(
        brandId || briefId
          ? `Saved to ${UI.creativeLibrary.toLowerCase()}`
          : `Saved to ${UI.creativeLibrary.toLowerCase()} (No brand)`,
      )
    } catch (err) {
      toast.error(extractApiError(err, `Could not save to ${UI.creativeLibrary.toLowerCase()}`))
    }
  }

  const runTurn = async (opts: {
    userText?: string
    userAttachments?: ChatAttachment[]
    action?: Exclude<PipelineAction, 'continue_video'>
    revisionNotes?: string
    appendUser?: boolean
    imagePromptOverride?: string
    videoPromptOverride?: string
    approvedImageOverride?: string
    storyboardImageUrls?: string[]
    useStoredReferences?: boolean
    chapterIndex?: number
    continuityStyleUrl?: string
    accumulatedSegmentPaths?: string[]
    brollIndex?: number
    approvedBrollOverride?: string
    approvedBrollByteplusOverride?: string
    brollBoardApprovals?: { index: number; url: string; byteplus_url?: string }[]
    existingBoardMessageId?: string
    modeOverride?: ChatMode
  }) => {
    if (busy) return
    const action = opts.action || 'continue'
    const isVideoAction = action === 'approve_next' || action === 'generate_video'
    const userText = (opts.userText || '').trim()
    const userAttachments = opts.userAttachments || []
    const imgP = opts.imagePromptOverride ?? imagePrompt
    const vidP = opts.videoPromptOverride ?? videoPrompt
    const approved = opts.approvedImageOverride ?? approvedImageUrl
    // Persist product photo across Approve / Regenerate even after composer clears
    const attachedProduct = userAttachments.find((a) => a.role === 'product')?.url
    const attachedLogo = userAttachments.find((a) => a.role === 'logo')?.url
    const attachedReferences = userAttachments
      .filter((a) => a.role === 'reference')
      .map((a) => a.url)
    const useStoredReferences = opts.useStoredReferences !== false
    const turnLogoRef = attachedLogo || (
      useStoredReferences ? logoReferenceUrl || selectedBrand?.logo_url || '' : ''
    )
    // A previous API fallback could persist the first attachment (including a
    // logo) as the product. Never send one URL with two conflicting roles.
    const turnProductRef = attachedProduct || (
      useStoredReferences && productReferenceUrl && productReferenceUrl !== turnLogoRef
        ? productReferenceUrl
        : ''
    )
    const turnAdditionalRefs = Array.from(
      new Set([...(useStoredReferences ? additionalReferenceUrls : []), ...attachedReferences]),
    ).filter((url) => url !== turnProductRef && url !== turnLogoRef).slice(0, 7)
    if (attachedProduct) setProductReferenceUrl(attachedProduct)
    if (attachedLogo) setLogoReferenceUrl(attachedLogo)
    if (attachedReferences.length) setAdditionalReferenceUrls(turnAdditionalRefs)
    // Stored message attachments retain roles after approval and browser reload.
    const referenceByUrl = new Map<string, ChatAttachment>()
    const referenceSource = useStoredReferences
      ? [...messages.flatMap((message) => message.attachments || []), ...userAttachments]
      : userAttachments
    for (const asset of referenceSource) {
      referenceByUrl.set(asset.url, asset)
    }
    if (useStoredReferences && characterReferenceUrl) {
      referenceByUrl.set(characterReferenceUrl, {
        id: `character-${characterReferenceUrl}`,
        name: 'Character anchor',
        url: characterReferenceUrl,
        previewUrl: assetUrl(characterReferenceUrl) || undefined,
        mime: 'image/*',
        role: 'character',
      })
    }
    const referenceAssets = Array.from(referenceByUrl.values())
      .filter((asset) => asset.role === 'scene' || asset.role === 'character' ||
        asset.role === 'reference' || asset.role === 'proof' ||
        asset.url === turnProductRef || asset.url === turnLogoRef || turnAdditionalRefs.includes(asset.url))
      .map((asset) => ({ url: asset.url, role: asset.role || 'reference' as const }))
        .slice(0, 9)
    const cloneHasCharacterReference = referenceAssets.some((asset) => asset.role === 'character')
    const boardUrls = (
      opts.storyboardImageUrls ||
      storyboardFramesForVideo(messages.flatMap((m) => m.storyboard || []))
    ).slice(0, 9)

    if (action === 'continue' && !userText && userAttachments.length === 0) {
      toast.error('Type a message or attach a file')
      return
    }

    let historyForApi = messages
      .filter((m) => m.role === 'user' || m.role === 'assistant')
      .map((m) => ({ role: m.role as 'user' | 'assistant', content: m.content }))

    if (opts.appendUser !== false && (userText || userAttachments.length)) {
      const userMsg: ChatMessage = {
        id: uid(),
        role: 'user',
        content: (userText || `(${action.replace(/_/g, ' ')})`) +
          (isVideoAction && promptOnlyVideo
            ? '\nGenerate directly from this timed prompt. Use every uploaded reference according to its assigned role and preserve the authored scene order. Exclude GPT-generated storyboard images.'
            : isVideoAction && !promptOnlyVideo && !useStoryboardReferences
              ? '\nUse the approved GPT Image 2 still as the Seedance opening frame. Keep original uploads as supplemental identity, product, scene and logo references.'
              : ''),
        attachments: userAttachments,
      }
      setMessages((prev) => [...prev, userMsg])
      historyForApi = [
        ...historyForApi,
        { role: 'user', content: userMsg.content },
      ]
    }

    setBusy(true)
    setModelMenuOpen(false)
    setModeMenuOpen(false)

    const pendingId = opts.existingBoardMessageId || uid()
    if (opts.existingBoardMessageId) {
      updateMessage(opts.existingBoardMessageId, {
        status: 'running',
        progress:
          action === 'generate_all_broll'
            ? 'Generating remaining B-roll stills…'
            : 'Working…',
        suggestedActions: [],
        error: undefined,
      })
    } else {
    setMessages((prev) => [
      ...prev,
      {
        id: pendingId,
        role: 'assistant',
        content:
            action === 'generate_image' ||
            action === 'regenerate_image' ||
            action === 'generate_next_chapter_image' ||
            action === 'generate_broll_image' ||
            action === 'regenerate_broll_image'
              ? cloneMode
                ? cloneHasCharacterReference
                  ? `Generating a ${cloneCount}-copy character scene with GPT Image 2…`
                  : `Creating a reusable character first, then generating the ${cloneCount}-copy scene…`
                : 'Generating GPT Image 2 still…'
              : action === 'generate_all_broll'
                ? 'Generating all B-roll stills…'
            : action === 'approve_next' || action === 'generate_video'
                  ? `Starting ${videoModelLabel}…`
              : 'Thinking…',
        status: 'running',
      },
    ])
    }

    try {
      const res = await generationApi.creativeStudioChat({
        session_id: activeChatId,
        messages: historyForApi,
        mode: opts.modeOverride ?? mode,
        chat_model: chatModel,
        duration_seconds: duration === 'auto'
          ? (extractChapterDurationFromPrompt(vidP || userText) ?? undefined)
          : Number(duration),
        aspect,
        resolution,
        sound_on: soundOn,
        speech_mode: speechMode,
        attachment_urls: turnProductRef
          ? [turnProductRef, ...userAttachments.map((a) => a.url).filter((u) => u !== turnProductRef)]
          : userAttachments.map((a) => a.url),
        brand_name: effectiveBrandName,
        product_name: productName || '',
        action,
        image_prompt: imgP,
        video_prompt: vidP,
        approved_image_url: promptOnlyVideo ? '' : approved,
        product_reference_url: turnProductRef,
        logo_reference_url: turnLogoRef,
        additional_reference_urls: turnAdditionalRefs,
        reference_assets: referenceAssets,
        storyboard_image_urls: !promptOnlyVideo && useStoryboardReferences ? boardUrls : [],
        prompt_only_video: promptOnlyVideo,
        preserve_image_text: !promptOnlyVideo,
        image_model: imageModel,
        video_model: videoModel,
        revision_notes: opts.revisionNotes || '',
        phase,
        chapter_index: opts.chapterIndex,
        continuity_style_url: opts.continuityStyleUrl || '',
        accumulated_segment_paths: opts.accumulatedSegmentPaths || [],
        broll_index: opts.brollIndex,
        approved_broll_url: opts.approvedBrollOverride || '',
        approved_broll_byteplus_url: opts.approvedBrollByteplusOverride || '',
        broll_board_approvals: opts.brollBoardApprovals,
        clone_mode: cloneMode,
        clone_scene_id: cloneSceneId,
        clone_count: cloneCount,
      })

      if (res.image_prompt) setImagePrompt(res.image_prompt)
      if (res.video_prompt) setVideoPrompt(res.video_prompt)
      if (res.approved_image_url) setApprovedImageUrl(res.approved_image_url)
      if (res.product_reference_url) setProductReferenceUrl(res.product_reference_url)
      if (res.phase) setPhase(res.phase)
      if (res.image_model) setImageModel(res.image_model)
      if (res.video_model) setVideoModel(res.video_model)

      const mediaMode =
        res.media_mode === 'image' ||
        res.media_mode === 'video' ||
        res.media_mode === 'storyboard' ||
        res.media_mode === 'broll_board'
          ? res.media_mode
          : undefined

      const suggested = (res.suggested_actions || []).filter(Boolean) as PipelineAction[]

      const incomingBoard = Array.isArray(
        (res as { storyboard_scenes?: unknown }).storyboard_scenes,
      )
        ? (
            (res as { storyboard_scenes: Record<string, unknown>[] }).storyboard_scenes || []
          ).map((s, i) => ({
            id: String(s.id || `scene-${i + 1}`),
            index: Number(s.index || i + 1),
            title: String(s.title || `Scene ${i + 1}`),
            imagePrompt: String(s.image_prompt || ''),
            overlays: Array.isArray(s.overlays) ? (s.overlays as string[]) : [],
          }))
        : undefined
      const existingBoard = opts.existingBoardMessageId
        ? messages.find((m) => m.id === opts.existingBoardMessageId)?.storyboard
        : undefined

      updateMessage(pendingId, {
        content: res.assistant_message || 'Done.',
        jobId: res.job_id || undefined,
        mediaMode,
        model: res.model || undefined,
        imagePrompt: res.image_prompt || undefined,
        videoPrompt: res.video_prompt || undefined,
        durationSeconds: res.duration_seconds || undefined,
        status: res.job_id ? 'queued' : 'idle',
        progress: res.job_id ? 'Queued…' : undefined,
        error: res.error || undefined,
        suggestedActions: suggested,
        phase: res.phase || undefined,
        chapterIndex:
          typeof res.chapter_index === 'number'
            ? res.chapter_index
          : undefined,
        filmTotalChapters:
          typeof res.film_total_chapters === 'number'
            ? res.film_total_chapters
            : undefined,
        brollIndex:
          typeof res.broll_index === 'number'
            ? res.broll_index
            : undefined,
        storyboard:
          incomingBoard && existingBoard
            ? mergeStoryboardFrames(existingBoard, incomingBoard)
            : incomingBoard,
      })

      if (
        action === 'generate_all_broll' &&
        !res.job_id &&
        res.status !== 'queued'
      ) {
        toast.error(res.error || res.assistant_message || 'Could not start B-roll generation')
      }

      if (res.job_id && mediaMode) {
        if (opts.existingBoardMessageId && res.assistant_message) {
          updateMessage(opts.existingBoardMessageId, {
            content: res.assistant_message,
          })
        }
        void pollJobIntoMessage(
          res.job_id,
          pendingId,
          mediaMode as 'image' | 'video' | 'storyboard' | 'broll_board',
        )
      } else if (
        !res.job_id &&
        (action === 'approve_all_broll' || action === 'approve_broll')
      ) {
        toast.success(res.assistant_message || 'B-roll approved')
      }
    } catch (err) {
      const msg = extractApiError(err, 'Chat failed')
      updateMessage(pendingId, {
        content: msg,
        status: 'failed',
        error: msg,
        suggestedActions: isVideoAction ? ['generate_video'] : ['generate_image'],
      })
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const startContinuation = async (
    fromMsg: ChatMessage,
    draftPrompt = '',
    draftAttachments: ChatAttachment[] = [],
  ) => {
    if (!fromMsg.jobId) {
      toast.error('The reviewed video part is missing its continuation job')
      return
    }
    const firstImage = draftAttachments.find(
      (asset) =>
        (asset.mime || '').startsWith('image') ||
        Boolean(asset.previewUrl) ||
        /\.(?:png|jpe?g|webp|gif|avif)$/i.test(asset.name || asset.url),
    )
    if (continuationReferenceMode === 'first_frame' && !firstImage) {
      toast.error('Attach one image before choosing Exact first frame')
      return
    }
    setComposer('')
    setAttachments([])

    const nextChapter =
      fromMsg.continuationMeta?.chapter_index ??
      (fromMsg.continuationMeta?.completed_segments || 1)
    const userText = draftPrompt.trim() ||
      `Generate chapter ${nextChapter + 1} from the reviewed previous chapter`
    const userMsg: ChatMessage = {
      id: uid(),
      role: 'user',
      content: userText,
      attachments: draftAttachments,
    }
    const pendingId = uid()
    const assistantMsg: ChatMessage = {
      id: pendingId,
      role: 'assistant',
      content:
        continuationReferenceMode === 'first_frame'
          ? 'Starting the next Seedance chapter from the newly attached exact first frame…'
          : 'Starting the next Seedance chapter with the previous approved video and new references…',
      mediaMode: 'video',
      status: 'queued',
      progress: 'Queued…',
      videoPrompt: draftPrompt.trim() || fromMsg.videoPrompt || videoPrompt,
    }
    setMessages((previous) => [...previous, userMsg, assistantMsg])
    setBusy(true)
    try {
      const lockedReferenceAssets = Array.from(
        new Map(
          [...messages.flatMap((message) => message.attachments || []), ...draftAttachments]
            .filter((asset) => asset.url)
            .map((asset) => [asset.url, asset]),
        ).values(),
      )
      if (
        characterReferenceUrl &&
        !lockedReferenceAssets.some((asset) => asset.url === characterReferenceUrl)
      ) {
        lockedReferenceAssets.push({
          id: `character-${characterReferenceUrl}`,
          name: 'Character anchor',
          url: characterReferenceUrl,
          role: 'character',
        })
      }
      const requestedTotal =
        fromMsg.continuationMeta?.requested_duration_seconds ??
        (duration === 'auto' ? 90 : Number(duration))
      const recovery = fromMsg.mediaUrl
        ? {
            part_video_url: fromMsg.mediaUrl,
            completed_segments: fromMsg.continuationMeta?.completed_segments ?? 1,
            segment_count:
              fromMsg.continuationMeta?.segment_count ??
              Math.max(2, Math.ceil(requestedTotal / seedanceClipCap(videoModel))),
            generated_duration_seconds: fromMsg.continuationMeta?.generated_duration_seconds,
            continuity_frame_count: fromMsg.continuationMeta?.continuity_frame_count,
            production_id: fromMsg.continuationMeta?.production_id,
            continuity_video_reference_url:
              fromMsg.continuationMeta?.continuity_video_reference_url,
            payload: buildContinuationRecoveryPayload({
              sessionId: activeChatId,
              videoModel,
              videoPrompt: fromMsg.videoPrompt || videoPrompt,
              duration,
              aspect,
              resolution,
              soundOn,
              speechMode,
              promptOnlyVideo,
              productName: productName || '',
              brandName: effectiveBrandName,
              productReferenceUrl,
              logoReferenceUrl,
              additionalReferenceUrls,
              referenceAssets: lockedReferenceAssets,
              requestedDurationSeconds: requestedTotal,
            }),
          }
        : {}
      const next = await generationApi.creativeStudioContinueJob(fromMsg.jobId, {
        ...recovery,
        next_prompt: draftPrompt.trim(),
        next_reference_assets: draftAttachments
          .filter((asset) => asset.url)
          .map((asset) => ({
            url: asset.url,
            role: asset.role || 'reference',
          })),
        next_reference_mode: continuationReferenceMode,
        next_seed_image_url:
          continuationReferenceMode === 'first_frame' ? firstImage?.url || '' : '',
      })
      if (!next.job_id) throw new Error(next.error || 'Next video part was not queued')
      updateMessage(fromMsg.id, {
        suggestedActions: [],
        continuationMeta: undefined,
      })
      updateMessage(pendingId, {
        jobId: next.job_id,
        status: 'queued',
        progress: next.progress || 'Queued…',
      })
      setContinuationReferenceMode('continuity')
      void pollJobIntoMessage(next.job_id, pendingId, 'video')
    } catch (err) {
      const message = extractApiError(err, 'Could not start the next video part')
      updateMessage(pendingId, {
        status: 'failed',
        error: message,
        content: message,
        suggestedActions: ['continue_video'],
      })
      toast.error(message)
    } finally {
      setBusy(false)
    }
  }

  const handleSend = async () => {
    const text = composer.trim()
    const atts = [...attachments]
    if (pendingContinuationMessage && (text || atts.length)) {
      await startContinuation(pendingContinuationMessage, text, atts)
      return
    }
    setComposer('')
    setAttachments([])
    const masterBrief = !cloneMode && isMasterProductionBrief(text)
    const productionLock = !masterBrief && isProductionSetupMessage(text)
    const brollBlock = !masterBrief && !productionLock && isBrollImageBlock(text)
    const brollCount = brollBlock ? countBrollImageBlocks(text) : 0

    const derivedAction: PipelineAction = cloneMode
      ? 'generate_image'
      : masterBrief
        ? 'generate_all_broll'           // full brief → generate all B-roll images first
        : productionLock
          ? 'continue'                   // lock only → save memory, no generation
          : brollBlock
            ? (brollCount > 1 ? 'generate_all_broll' : 'generate_broll_image')
            : promptOnlyVideo
              ? 'generate_video'
              : 'generate_image'

    const notVideo = masterBrief || productionLock || brollBlock
    await runTurn({
      userText: text,
      userAttachments: atts,
      action: derivedAction,
      appendUser: true,
      modeOverride: productionLock ? 'ask' : undefined,
      imagePromptOverride: notVideo || !promptOnlyVideo ? text : undefined,
      videoPromptOverride: notVideo ? undefined : promptOnlyVideo ? text : undefined,
      approvedImageOverride: promptOnlyVideo && !notVideo ? '' : undefined,
      useStoredReferences: cloneMode,
    })
  }

  const selectSavedStill = (asset: Asset) => {
    if (!asset.file_url) return
    setApprovedImageUrl(asset.file_url)
    setPhase('awaiting_video')
    attachLibraryAsset(asset, 'scene')
    toast.success('Saved image selected — you can use it with uploads or send it to Seedance')
  }

  const startVideoFromSavedStill = async (asset: Asset) => {
    if (!asset.file_url) return
    selectSavedStill(asset)
    setImageLibraryOpen(false)
    const text = composer.trim()
    await runTurn({
      userText: text,
      userAttachments: [...attachments],
      action: 'generate_video',
      appendUser: Boolean(text || attachments.length),
      approvedImageOverride: asset.file_url,
      videoPromptOverride: (videoPrompt || text || imagePrompt).trim(),
    })
  }

  const handlePipelineAction = async (action: PipelineAction, fromMsg?: ChatMessage) => {
    if (action === 'generate_all_broll') {
      const boardMsg =
        fromMsg?.mediaMode === 'broll_board'
          ? fromMsg
          : [...messages].reverse().find((m) => m.mediaMode === 'broll_board')
      await runTurn({
        userText: boardMsg
          ? 'Generate remaining B-roll stills on the board'
          : 'Generate all B-roll stills (dashboard / scene images)',
        action: 'generate_all_broll',
        appendUser: true,
        userAttachments: [],
        existingBoardMessageId: boardMsg?.id,
      })
      return
    }
    if (action === 'generate_broll_image') {
      await runTurn({
        userText: fromMsg?.brollIndex
          ? `Generate B-roll IMAGE ${fromMsg.brollIndex}`
          : 'Generate next B-roll still (dashboard / laptop scene)',
        action: 'generate_broll_image',
        appendUser: true,
        userAttachments: [],
        brollIndex: fromMsg?.brollIndex,
      })
      return
    }
    if (action === 'approve_all_broll') {
      const frames = (fromMsg?.storyboard || []).filter(
        (frame) => frame.url && frame.index,
      )
      if (!frames.length) {
        toast.error('No B-roll stills ready to approve')
        return
      }
      await runTurn({
        userText: `Approve all ${frames.length} B-roll stills for Seedance`,
        action: 'approve_all_broll',
        appendUser: true,
        userAttachments: [],
        brollBoardApprovals: frames.map((frame) => ({
          index: frame.index as number,
          url: frame.url as string,
          byteplus_url: frame.byteplusUrl,
        })),
      })
      return
    }
    if (action === 'approve_broll') {
      const brollUrl = fromMsg?.mediaUrl
      if (!brollUrl || !fromMsg?.brollIndex) {
        toast.error('B-roll still or index is missing')
        return
      }
      await runTurn({
        userText: `Approve B-roll IMAGE ${fromMsg.brollIndex} for Seedance`,
        action: 'approve_broll',
        appendUser: true,
        userAttachments: [],
        brollIndex: fromMsg.brollIndex,
        approvedBrollOverride: brollUrl,
        approvedBrollByteplusOverride: fromMsg.byteplusUrl,
      })
      return
    }
    if (action === 'generate_next_chapter_image') {
      if (!fromMsg?.continuationMeta?.continuity_reference_url) {
        toast.error('The previous chapter continuity frame is missing')
        return
      }
      const nextChapterIndex =
        fromMsg.continuationMeta.chapter_index ??
        (fromMsg.continuationMeta.completed_segments || 0)
      await runTurn({
        userText: `Generate chapter ${nextChapterIndex + 1} still from the previous final frame`,
        action: 'generate_next_chapter_image',
        appendUser: true,
        userAttachments: [],
        imagePromptOverride: fromMsg.imagePrompt || imagePrompt,
        videoPromptOverride: fromMsg.videoPrompt || videoPrompt,
        chapterIndex: nextChapterIndex,
        continuityStyleUrl: fromMsg.continuationMeta.continuity_reference_url,
        accumulatedSegmentPaths: fromMsg.continuationMeta.staged_segment_paths,
      })
      return
    }
    if (action === 'continue_video') {
      const text = composer.trim()
      const atts = [...attachments]
      await startContinuation(fromMsg as ChatMessage, text, atts)
      return
    }
    if (
      action === 'approve_next' &&
      fromMsg?.jobId &&
      isChapterHandoffReady(
        fromMsg,
        fromMsg.continuationMeta?.requested_duration_seconds ?? projectDurationSeconds,
        clipCap,
      )
    ) {
      const text = composer.trim()
      const atts = [...attachments]
      await startContinuation(fromMsg, text, atts)
      return
    }
    if (
      (action === 'approve_next' || action === 'generate_video') &&
      !promptOnlyVideo &&
      useStoryboardReferences &&
      fromMsg?.storyboard?.length
    ) {
      const selected = storyboardFramesForVideo(fromMsg.storyboard)
      if (!selected.length) {
        toast.error('Select at least one storyboard frame for Seedance, or turn off storyboard references.')
        return
      }
    }

    const nextImagePrompt = fromMsg?.imagePrompt || imagePrompt
    const nextVideoPrompt = fromMsg?.videoPrompt || videoPrompt
    const nextApproved =
      (fromMsg?.mediaMode === 'image' && fromMsg.mediaUrl) ||
      (fromMsg?.mediaMode === 'storyboard' &&
        (fromMsg.storyboard?.find((f) => /reveal|feature|close|product/i.test(f.title || ''))
          ?.url ||
          fromMsg.storyboard?.find((f) => f.url)?.url ||
          fromMsg.mediaUrl)) ||
      approvedImageUrl

    if (fromMsg?.imagePrompt) setImagePrompt(fromMsg.imagePrompt)
    if (fromMsg?.videoPrompt) setVideoPrompt(fromMsg.videoPrompt)
    if (fromMsg?.mediaUrl && fromMsg.mediaMode === 'image') {
      setApprovedImageUrl(fromMsg.mediaUrl)
    }
    if (fromMsg?.mediaMode === 'storyboard') {
      const hero =
        fromMsg.storyboard?.find((f) =>
          /reveal|feature|close|product/i.test(f.title || ''),
        )?.url || fromMsg.storyboard?.find((f) => f.url)?.url
      if (hero) setApprovedImageUrl(hero)
    }

    let revisionNotes = ''
    if (action === 'regenerate_image') {
      const notes = window.prompt(
        'What should change in the still? (leave blank to regenerate similar)',
        '',
      )
      if (notes === null) return
      revisionNotes = notes.trim()
    }

    const label =
      action === 'approve_next'
        ? 'Approve still → generate Seedance video'
        : action === 'regenerate_image'
          ? revisionNotes
            ? `Regenerate image: ${revisionNotes}`
            : 'Regenerate image'
          : ACTION_LABELS[action] || action

    await runTurn({
      userText: label,
      action,
      revisionNotes,
      appendUser: true,
      userAttachments: [],
      imagePromptOverride: nextImagePrompt,
      videoPromptOverride: nextVideoPrompt,
      approvedImageOverride:
        fromMsg?.phase === 'awaiting_video' &&
        fromMsg?.suggestedActions?.includes('approve_next') &&
        !fromMsg?.mediaUrl
          ? ''
          : nextApproved || undefined,
      storyboardImageUrls: storyboardFramesForVideo(fromMsg?.storyboard).slice(0, 9),
      chapterIndex:
        fromMsg?.continuationMeta?.chapter_index ??
        (fromMsg &&
        isChapterHandoffReady(
          fromMsg,
          fromMsg.continuationMeta?.requested_duration_seconds ?? projectDurationSeconds,
          clipCap,
        )
          ? 1
          : fromMsg?.chapterIndex),
      continuityStyleUrl: fromMsg?.continuationMeta?.continuity_reference_url || '',
      accumulatedSegmentPaths: fromMsg?.continuationMeta?.staged_segment_paths,
    })
  }

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      void handleSend()
    }
  }

  const clearChat = () => {
    startNewChat()
  }

  const hasMessages = messages.length > 0
  const hadMessagesRef = useRef(false)

  useEffect(() => {
    if (hasMessages && !hadMessagesRef.current) {
      setComposerSettingsOpen(false)
    }
    hadMessagesRef.current = hasMessages
  }, [hasMessages])
  const activeJobMessage = useMemo(
    () =>
      [...messages]
        .reverse()
        .find((m) => m.jobId && (m.status === 'queued' || m.status === 'running')),
    [messages],
  )
  const isGenerating = Boolean(activeJobMessage)
  const phaseLabel =
    phase === 'awaiting_image'
      ? '1 · Still'
      : phase === 'image_running'
        ? '1 · Rendering still'
        : phase === 'storyboard_running'
          ? '1 · Storyboard'
          : phase === 'awaiting_video'
            ? '2 · Approve board'
            : phase === 'video_running'
              ? '3 · Seedance'
              : phase === 'done'
                ? 'Done'
                : 'Plan'

  const composerCard = (
    <div className={hasMessages ? 'w-full' : 'w-full max-w-3xl mx-auto'}>
      {imageLibraryOpen && (
        <div
          className="fixed inset-0 z-[100] bg-black/75 backdrop-blur-sm p-3 sm:p-8 grid place-items-center"
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setImageLibraryOpen(false)
          }}
        >
          <div className="w-full max-w-6xl h-[min(780px,90vh)] rounded-[28px] border border-white/10 bg-[#1d1f22] shadow-2xl overflow-hidden flex flex-col">
            <div className="flex items-center gap-1 px-4 sm:px-6 pt-4 border-b border-white/10">
              {(['uploads', 'generations', 'characters', 'liked'] as MediaLibrarySection[]).map((section) => (
                <button
                  key={section}
                  type="button"
                  onClick={() => setMediaLibrarySection(section)}
                  className={`px-4 py-2.5 rounded-t-xl text-sm font-semibold capitalize ${
                    mediaLibrarySection === section
                      ? 'bg-accent-dim text-charcoal border border-accent/30'
                      : 'text-mid hover:text-charcoal'
                  }`}
                >
                  {section}
                </button>
              ))}
              <button
                type="button"
                aria-label="Close media library"
                onClick={() => setImageLibraryOpen(false)}
                className="ml-auto mb-2 h-10 w-10 rounded-full bg-surface text-xl text-mid hover:bg-surface-hover hover:text-charcoal"
              >
                ×
              </button>
            </div>

            <div className="flex flex-wrap items-center gap-2 px-4 sm:px-6 py-3 border-b border-white/10 bg-white/[0.025]">
              {(['recent', 'all', 'images', 'videos', 'audio'] as MediaLibraryFilter[]).map((filter) => (
                <button
                  key={filter}
                  type="button"
                  onClick={() => setMediaLibraryFilter(filter)}
                  className={`rounded-full px-3.5 py-2 text-xs font-semibold capitalize ${
                    mediaLibraryFilter === filter
                      ? 'bg-accent-dim text-charcoal border border-accent/30'
                      : 'text-mid hover:text-charcoal'
                  }`}
                >
                  {filter}
                </button>
              ))}
              <label className="ml-auto flex items-center gap-2 text-xs text-mid">
                Sort by
                <select
                  value={mediaLibrarySort}
                  onChange={(event) =>
                    setMediaLibrarySort(event.target.value as MediaLibrarySort)
                  }
                  className="rounded-lg border border-border bg-white px-2 py-1.5 text-charcoal"
                >
                  <option value="newest">Newest</option>
                  <option value="oldest">Oldest</option>
                  <option value="name">Name</option>
                </select>
              </label>
            </div>

            <div className="flex-1 overflow-y-auto cs-message-scroll p-4 sm:p-6">
              {imageLibraryLoading ? (
                <div className="h-full grid place-items-center text-sm text-white/45">
                  Loading your media…
                </div>
              ) : (
                <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3">
                  {mediaLibrarySection === 'uploads' &&
                    (mediaLibraryFilter === 'recent' ||
                      mediaLibraryFilter === 'all' ||
                      mediaLibraryFilter === 'images') && (
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => fileInputRef.current?.click()}
                        className="aspect-square rounded-2xl border border-dashed border-white/20 bg-white/[0.035] grid place-items-center hover:border-[#b8f000]/60 hover:bg-[#b8f000]/5 disabled:opacity-40"
                      >
                        <span className="grid place-items-center gap-2 text-white/80">
                          <span className="grid h-12 w-12 place-items-center rounded-full border border-white/20 bg-white/5 text-2xl">
                            ↑
                          </span>
                          <span className="text-sm font-semibold">Upload files</span>
                        </span>
                      </button>
                    )}

                  {visibleLibraryAssets.map((asset) => {
                    const src = assetUrl(asset.file_url)
                    const picked = attachments.find(
                      (attachment) => attachment.url === asset.file_url,
                    )
                    const isImage = asset.file_type.startsWith('image/')
                    const isVideo = asset.file_type.startsWith('video/')
                    const isAudio = asset.file_type.startsWith('audio/')
                    const isLiked = likedAssetIds.includes(asset.id)
                    return (
                      <div
                        key={asset.id}
                        className={`group relative rounded-2xl overflow-hidden border bg-[#292b2e] ${
                          picked
                            ? 'border-[#b8f000] ring-2 ring-[#b8f000]/25'
                            : 'border-white/5 hover:border-white/20'
                        }`}
                      >
                        <button
                          type="button"
                          disabled={busy}
                          onClick={() => toggleLibraryAttachment(asset)}
                          className="relative block w-full aspect-square text-left disabled:opacity-50"
                          title={isImage ? 'Select image' : 'Only images can be used as Seedance references'}
                        >
                          {isImage && src ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={src}
                              alt={asset.file_name}
                              className="h-full w-full object-cover"
                            />
                          ) : isVideo && src ? (
                            <video src={src} muted className="h-full w-full object-cover" />
                          ) : (
                            <span className="h-full grid place-items-center text-white/45">
                              <span className="text-center">
                                <span className="block text-3xl mb-2">
                                  {isAudio ? '♪' : isVideo ? '▶' : '▧'}
                                </span>
                                <span className="text-[10px] uppercase tracking-wider">
                                  {asset.file_type.split('/')[0] || 'file'}
                                </span>
                              </span>
                            </span>
                          )}
                          {picked ? (
                            <span className="absolute top-2 left-2 h-6 w-6 rounded-full bg-[#b8f000] text-black grid place-items-center text-xs font-black">
                              ✓
                            </span>
                          ) : null}
                        </button>
                        <button
                          type="button"
                          aria-label={isLiked ? 'Remove from liked' : 'Add to liked'}
                          onClick={() => toggleLikedAsset(asset.id)}
                          className={`absolute top-2 right-2 h-8 w-8 rounded-full grid place-items-center backdrop-blur ${
                            isLiked
                              ? 'bg-[#b8f000] text-black'
                              : 'bg-black/55 text-white/80 opacity-0 group-hover:opacity-100'
                          }`}
                        >
                          {isLiked ? '♥' : '♡'}
                        </button>
                        <div className="p-2.5 space-y-2">
                          <p className="truncate text-[11px] text-white/75" title={asset.file_name}>
                            {asset.file_name}
                          </p>
                          {picked && isImage ? (
                            <div className="flex gap-1.5">
                              <select
                                value={picked.role || 'reference'}
                                onChange={(event) =>
                                  setAttachmentRole(
                                    picked,
                                    event.target.value as ChatAttachment['role'],
                                  )
                                }
                                className="min-w-0 flex-1 rounded-lg bg-black/45 border border-white/10 px-1.5 py-1 text-[10px] text-white/80"
                              >
                                <option value="proof">🔒 Proof (editor only)</option>
                                <option value="reference">Reference</option>
                                <option value="product">Product</option>
                                <option value="character">Character</option>
                                <option value="scene">Scene</option>
                                <option value="logo">Logo</option>
                              </select>
                              <button
                                type="button"
                                onClick={() => selectSavedStill(asset)}
                                className={`rounded-lg px-2 py-1 text-[10px] border ${
                                  approvedImageUrl === asset.file_url
                                    ? 'border-[#b8f000] text-[#b8f000]'
                                    : 'border-white/10 text-white/65'
                                }`}
                              >
                                Still
                              </button>
                              <button
                                type="button"
                                disabled={busy}
                                onClick={() => void startVideoFromSavedStill(asset)}
                                className="rounded-lg border border-[#b8f000]/40 px-2 py-1 text-[10px] text-[#b8f000] disabled:opacity-40"
                                title="Use this still and start Seedance"
                              >
                                Video
                              </button>
                            </div>
                          ) : null}
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}

              {!imageLibraryLoading && visibleLibraryAssets.length === 0 && (
                <p className="py-12 text-center text-sm text-white/40">
                  {mediaLibrarySection === 'generations'
                    ? 'Generated images will appear here automatically.'
                    : mediaLibrarySection === 'characters'
                      ? 'Character references and approved clone images will appear here.'
                    : mediaLibrarySection === 'liked'
                      ? 'Like media with the heart button to keep it here.'
                      : mediaLibraryFilter === 'videos' || mediaLibraryFilter === 'audio'
                        ? `No ${mediaLibraryFilter} in this library yet.`
                        : 'Upload your first reference image.'}
                </p>
              )}
            </div>

            <div className="flex items-center justify-between gap-3 px-4 sm:px-6 py-3 border-t border-white/10 bg-[#17181b]">
              <p className="text-xs text-white/45">
                {attachments.length} of 9 selected · choose a role for each image
              </p>
              <button
                type="button"
                onClick={() => setImageLibraryOpen(false)}
                className="rounded-full bg-[#b8f000] px-5 py-2 text-xs font-bold text-black"
              >
                Add selected
              </button>
            </div>
          </div>
        </div>
      )}
      {pendingContinuationMessage ? (
        <div className="mb-2 rounded-xl border border-[#b8f000]/35 bg-[#b8f000]/10 px-3 py-2.5 space-y-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div>
              <p className="text-[11px] font-bold text-[#b8f000]">
                Next chapter setup
              </p>
              <p className="text-[10px] text-white/60">
                Paste only the next chapter prompt and attach references for that chapter. Sending here continues the reviewed video.
              </p>
            </div>
            <select
              value={continuationReferenceMode}
              onChange={(event) =>
                setContinuationReferenceMode(
                  event.target.value as ContinuationReferenceMode,
                )
              }
              className="rounded-lg border border-white/15 bg-[#16171a] px-2.5 py-1.5 text-[10px] text-white"
              aria-label="Next chapter reference mode"
            >
              <option value="continuity">
                Preserve previous video continuity
              </option>
              <option value="first_frame">
                Start exactly from first attached image
              </option>
            </select>
          </div>
          <p className="text-[9px] text-white/45">
            Preserve continuity keeps the previous presenter/video and uses new uploads as visual references. Exact first frame starts from the new image and resets previous-video continuity because BytePlus cannot accept both in one request.
          </p>
        </div>
      ) : null}
      {attachments.length > 0 && (
        <div className="flex flex-wrap gap-2 mb-2 px-1">
          {attachments.map((a) => (
            <div
              key={a.id}
              className="relative group rounded-lg border border-white/15 bg-white/5 p-1"
            >
              {a.previewUrl && (a.mime || '').startsWith('image') ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={a.previewUrl} alt={a.name} className="h-16 w-16 object-cover" />
              ) : (
                <div className="h-16 w-28 px-2 flex items-center text-[10px] text-white/70 truncate">
                  {a.name}
                </div>
              )}
              <select
                value={a.role || 'reference'}
                onChange={(event) =>
                  setAttachmentRole(
                    a,
                    event.target.value as ChatAttachment['role'],
                  )
                }
                className="mt-1 block w-full max-w-28 rounded bg-black/70 px-1 py-0.5 text-[9px] text-white"
                title="How this image should be used"
              >
                <option value="proof">🔒 Proof (editor only)</option>
                <option value="product">Product</option>
                <option value="logo">Brand logo</option>
                <option value="scene">Scene / location</option>
                <option value="character">Character</option>
                <option value="reference">Other reference</option>
              </select>
              <button
                type="button"
                onClick={() => removeAttachment(a)}
                className="absolute top-0.5 right-0.5 h-5 w-5 rounded-full bg-black/70 text-white text-xs"
              >
                ×
              </button>
            </div>
          ))}
        </div>
      )}

      <div
        className={`overflow-hidden border border-white/10 bg-[#1a1b1e] ${
          hasMessages ? 'rounded-xl' : 'rounded-2xl shadow-xl'
        }`}
      >
        <textarea
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          onKeyDown={onKeyDown}
          rows={hasMessages ? 2 : 4}
          placeholder={
            pendingContinuationMessage
              ? 'Paste only the next chapter prompt, then attach its proof or reference images…'
              : 'Make a 10s UGC product video for my campaign…'
          }
          className={`w-full resize-none overflow-y-auto cs-message-scroll bg-transparent px-4 text-[15px] text-white placeholder:text-white/35 focus:outline-none ${
            hasMessages
              ? 'pt-3 pb-1 max-h-24'
              : 'pt-4 pb-2 max-h-[min(9rem,22vh)]'
          }`}
          disabled={busy}
        />

        <div className="flex items-center gap-2 px-3 pb-3 flex-wrap">
          <input
            ref={fileInputRef}
            type="file"
            accept="image/*,.pdf,.txt,.md"
            multiple
            className="hidden"
            onChange={(e) => void handleAttach(e.target.files)}
          />
          <button
            type="button"
            onClick={() => setImageLibraryOpen(true)}
            className="h-9 w-9 rounded-full border border-white/15 bg-white/5 text-white/80 hover:bg-white/10 text-lg"
            title="Open uploads and generated media"
          >
            +
          </button>

          <div className="relative">
            <button
              type="button"
              onClick={() => {
                setModelMenuOpen((o) => !o)
                setModeMenuOpen(false)
              }}
              className="h-9 px-3 rounded-full border border-white/15 bg-white/5 text-xs font-semibold text-white/90 inline-flex items-center gap-1.5"
            >
              <span className="h-2 w-2 rounded-full bg-[#b8f000]" />
              {selectedChatLabel}
              <span className="text-[10px] font-bold text-[#c8e86a] bg-[#c8e86a]/15 px-1.5 py-0.5 rounded">
                Chat
              </span>
              ▾
            </button>
            {modelMenuOpen && (
              <div className="absolute left-0 bottom-11 z-40 w-72 max-h-64 overflow-y-auto rounded-xl border border-white/10 bg-[#121316] shadow-2xl">
                <button
                  type="button"
                  className={`w-full text-left px-3 py-2 text-xs hover:bg-white/5 ${
                    chatModel === 'auto' ? 'text-[#b8f000]' : 'text-white/80'
                  }`}
                  onClick={() => {
                    setChatModel('auto')
                    setModelMenuOpen(false)
                  }}
                >
                  Auto — {defaultChatModel}
                </button>
                {chatModels.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={`w-full text-left px-3 py-2 text-xs hover:bg-white/5 ${
                      chatModel === m.id ? 'text-[#b8f000]' : 'text-white/80'
                    }`}
                    onClick={() => {
                      setChatModel(m.id)
                      setModelMenuOpen(false)
                    }}
                  >
                    <span className="text-white/40">{m.provider} · </span>
                    {m.label}
                  </button>
                ))}
                {!chatModels.length && !catalogLoading && (
                  <p className="px-3 py-2 text-[11px] text-amber-200/90">
                    {catalogError || csModels?.message || 'No chat models.'}
                    <button type="button" className="ml-2 underline" onClick={() => refetchModels()}>
                      Retry
                    </button>
                  </p>
                )}
              </div>
            )}
          </div>

          <div className="relative ml-auto">
            <button
              type="button"
              onClick={() => {
                setModeMenuOpen((o) => !o)
                setModelMenuOpen(false)
              }}
              className="h-9 px-3 rounded-full text-xs font-medium text-white/70 hover:text-white"
            >
              {MODES.find((m) => m.id === mode)?.label} mode ▾
            </button>
            {modeMenuOpen && (
              <div className="absolute right-0 bottom-11 z-40 w-52 rounded-xl border border-white/10 bg-[#121316] shadow-2xl overflow-hidden">
                {MODES.map((m) => (
                  <button
                    key={m.id}
                    type="button"
                    className={`w-full text-left px-3 py-2.5 hover:bg-white/5 ${
                      mode === m.id ? 'bg-white/5' : ''
                    }`}
                    onClick={() => {
                      setMode(m.id)
                      setModeMenuOpen(false)
                    }}
                  >
                    <p className="text-xs font-semibold text-white">{m.label}</p>
                    <p className="text-[10px] text-white/45">{m.hint}</p>
                  </button>
                ))}
              </div>
            )}
          </div>

          {isGenerating && activeJobMessage ? (
            <button
              type="button"
              onClick={() => void stopGeneration(activeJobMessage)}
              className="h-10 w-10 rounded-full bg-red-500/90 text-white font-bold text-sm hover:bg-red-500"
              title="Stop generation"
              aria-label="Stop generation"
            >
              ■
            </button>
          ) : (
            <button
              type="button"
              onClick={() => void handleSend()}
              disabled={busy || (!composer.trim() && attachments.length === 0)}
              className="h-10 w-10 rounded-full bg-[#b8f000] text-black font-bold text-lg disabled:opacity-40"
            >
              ↑
            </button>
          )}
        </div>
      </div>

      {hasMessages ? (
        <button
          type="button"
          onClick={() => setComposerSettingsOpen((open) => !open)}
          className="mt-2 w-full rounded-lg border border-white/10 bg-white/[0.03] px-3 py-2 text-left text-[11px] text-white/55 hover:bg-white/[0.06]"
        >
          <span className="font-semibold text-white/75">
            {composerSettingsOpen ? 'Hide generation settings' : 'Generation settings'}
        </span>
          <span className="text-white/40">
            {' '}
            · {videoModelLabel} · {aspect.replace('/', ':')} ·{' '}
            {duration === 'auto' ? 'Auto length' : `${duration}s`}
            {promptOnlyVideo ? ' · Direct Seedance' : ` · ${imageModelLabelText} → Seedance`}
            {soundOn
              ? speechMode === 'native_presenter'
                ? ' · Native presenter speech'
                : ' · Studio voiceover'
              : ' · Silent'}
          </span>
        </button>
      ) : null}

      {(!hasMessages || composerSettingsOpen) && (
      <div className={`flex flex-wrap items-center gap-2 text-[11px] text-white/50 ${hasMessages ? 'mt-2 max-h-40 overflow-y-auto cs-panel-scroll pr-1' : 'mt-3 justify-center'}`}>
        {!promptOnlyVideo ? (
          <select
            value={imageModel}
            onChange={(e) => setImageModel(e.target.value)}
            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80 max-w-[240px]"
            title="Image model for B-roll stills"
            aria-label="Image model for B-roll stills"
          >
            {(imageModels.length ? imageModels : [
              { id: 'openai-gpt-image-2', label: 'GPT Image 2' },
              { id: 'ark-seedream-5-0-lite', label: 'Seedream 5.0 Lite' },
              { id: 'ark-seedream-5-0-pro', label: 'Seedream 5.0 Pro' },
              { id: 'ark-seedream-5-0-flash', label: 'Seedream 5.0 Flash' },
            ]).map((model) => (
              <option key={model.id} value={model.id} className="bg-[#121316]">
                Still · {model.label}
              </option>
            ))}
          </select>
        ) : null}
        {!promptOnlyVideo && cloneMode ? (
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
            Clone Image · {cloneCount} copies
        </span>
        ) : null}
        {seedance25Only ? (
          <span
            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80"
            title="Seedance 2.5 only for this account"
          >
            Video · Seedance 2.5 · 30s clips
          </span>
        ) : (
          <select
            value={videoModel}
            onChange={(e) => setVideoModel(e.target.value)}
            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80 max-w-[220px]"
            title="Seedance video model"
            aria-label="Seedance video model"
          >
            {(videoModels.length ? videoModels : [
              { id: 'ark-seedance-2-0', label: 'Seedance 2.0 · 15s clips' },
              { id: 'ark-seedance-2-5', label: 'Seedance 2.5 · 30s clips' },
            ]).map((model) => (
              <option key={model.id} value={model.id} className="bg-[#121316]">
                Video · {model.label}
              </option>
            ))}
          </select>
        )}
        {productReferenceUrl ? (
          <span className="rounded-full border border-[#b8f000]/30 bg-[#b8f000]/10 text-[#b8f000] px-2.5 py-1">
            Product photo locked
          </span>
        ) : null}
        {characterReferenceUrl ? (
          <span className="rounded-full border border-[#b8f000]/30 bg-[#b8f000]/10 text-[#b8f000] px-2.5 py-1">
            Character reference
          </span>
        ) : null}
        <span className="rounded-full border border-[#b8f000]/30 bg-[#b8f000]/10 text-[#b8f000] px-2.5 py-1">
          {phaseLabel}
        </span>
        {productReferenceUrl && !promptOnlyVideo && (
          <label
            className="flex items-center gap-1.5"
            title="Turn off to send only your uploaded product/logo to Seedance. Use per-frame checkboxes to pick which storyboard stills are included."
          >
            <input
              type="checkbox"
              checked={useStoryboardReferences}
              disabled={busy}
              onChange={(event) => setUseStoryboardReferences(event.target.checked)}
            />
            Use selected storyboard frames in video
          </label>
        )}
        <div
          className="inline-flex overflow-hidden rounded-full border border-[#b8f000]/30 bg-white/5"
          role="group"
          aria-label="Creative Studio generation workflow"
        >
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setCloneMode(false)
              setPromptOnlyVideo(true)
            }}
            className={`px-2.5 py-1 transition-colors ${
              promptOnlyVideo && !cloneMode
                ? 'bg-[#b8f000]/15 text-[#6f9000] font-semibold'
                : 'text-white/55 hover:text-white/80'
            }`}
            title="Send the timed prompt and uploaded references directly to Seedance"
          >
            Direct Seedance
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setCloneMode(false)
              setPromptOnlyVideo(false)
            }}
            className={`border-l border-[#b8f000]/20 px-2.5 py-1 transition-colors ${
              !promptOnlyVideo && !cloneMode
                ? 'bg-[#b8f000]/15 text-[#6f9000] font-semibold'
                : 'text-white/55 hover:text-white/80'
            }`}
            title="Generate and review a GPT Image 2 starting scene, then animate the approved still with Seedance"
          >
            GPT Image 2 → Seedance
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => {
              setCloneMode(true)
              setPromptOnlyVideo(false)
              setImageModel('openai-gpt-image-2')
              setMediaLibrarySection('characters')
            }}
            className={`border-l border-[#b8f000]/20 px-2.5 py-1 transition-colors ${
              cloneMode
                ? 'bg-[#b8f000]/15 text-[#6f9000] font-semibold'
                : 'text-white/55 hover:text-white/80'
            }`}
            title="Create multiple copies of one person from reusable Character references"
          >
            Clone Image
          </button>
        </div>
        {cloneMode ? (
          <>
            <select
              value={cloneSceneId}
              onChange={(event) => setCloneSceneId(event.target.value)}
              className="rounded-full border border-[#b8f000]/30 bg-white/5 px-2.5 py-1 text-white/80 max-w-[230px]"
              aria-label="Clone scene"
              title="Choose a scene or leave Custom to describe it in the message"
            >
              <option value="" className="bg-[#121316]">Custom scene from prompt</option>
              {(cloneCatalog?.categories || []).map((category) => (
                <optgroup key={category.id} label={category.label} className="bg-[#121316]">
                  {(cloneCatalog?.scenes || [])
                    .filter((scene) => scene.category === category.id)
                    .map((scene) => (
                      <option key={scene.id} value={scene.id}>{scene.title}</option>
                    ))}
                </optgroup>
              ))}
            </select>
            <select
              value={cloneCount}
              onChange={(event) => setCloneCount(Number(event.target.value))}
              className="rounded-full border border-[#b8f000]/30 bg-white/5 px-2.5 py-1 text-white/80"
              aria-label="Number of character copies"
            >
              {[2, 3, 4, 5, 6].map((count) => (
                <option key={count} value={count} className="bg-[#121316]">{count} copies</option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => {
                setMediaLibrarySection('characters')
                setMediaLibraryFilter('recent')
                setImageLibraryOpen(true)
              }}
              className="rounded-full border border-[#b8f000]/30 bg-[#b8f000]/10 px-2.5 py-1 text-[#6f9000]"
              title="Optional: select 1–6 existing Character photos. With none selected, GPT Image 2 creates and saves a new identity first; this uses two image generations."
            >
              {Math.max(
                attachments.filter((attachment) => attachment.role === 'character').length,
                characterReferenceUrl ? 1 : 0,
              ) > 0
                ? `${Math.max(
                    attachments.filter((attachment) => attachment.role === 'character').length,
                    characterReferenceUrl ? 1 : 0,
                  )} character refs · add/select`
                : 'No character photo · auto-create first'}
            </button>
          </>
        ) : null}
        <select
          value={duration}
          onChange={(e) => setDuration(e.target.value as DurationId)}
          className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80"
        >
          {DURATIONS.map((d) => (
            <option key={d.id} value={d.id} className="bg-[#121316]">
              {d.label}
            </option>
          ))}
        </select>
        {duration !== 'auto' && Number(duration) > clipCap ? (
          <span
            className="rounded-full border border-[#b8f000]/30 bg-[#b8f000]/10 px-2.5 py-1 text-[#6f9000]"
            title={promptOnlyVideo
              ? 'Independent Seedance chapters use uploaded references as general visual guidance and are stitched after every chapter completes.'
              : "Each chapter starts from the previous chapter's final frame and keeps the cast reference locked."}
          >
            {Math.ceil(Number(duration) / clipCap)} {promptOnlyVideo ? 'upload-guided chapters' : 'continuity-linked chapters'}
          </span>
        ) : null}
        {clipCap >= 30 ? (
          <span
            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/60"
            title="Seedance 2.5 supports up to 1080p per clip"
          >
            2.5 · 1080p max
          </span>
        ) : null}
        {aspect === '4/5' ? (
          <span
            className="rounded-full border border-amber-500/30 bg-amber-500/10 px-2.5 py-1 text-amber-200/90"
            title="BytePlus Seedance does not accept 4:5; we generate at 3:4 and you can crop to 4:5 in post"
          >
            4:5 → 3:4 on Seedance
          </span>
        ) : null}
        <select
          value={aspect}
          onChange={(e) => setAspect(e.target.value as AspectId)}
          className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80"
          title={
            aspect === '4/5'
              ? 'BytePlus maps 4:5 to 3:4 (1080×1440). Crop to 1080×1350 in post for Meta feed.'
              : undefined
          }
        >
          {ASPECTS.map((a) => (
            <option key={a.id} value={a.id} className="bg-[#121316]">
              {a.label}
              {a.id === '4/5' ? ' · uses 3:4' : ''}
            </option>
          ))}
        </select>
        <select
          value={resolution}
          onChange={(e) => setResolution(e.target.value as ResolutionId)}
          className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80"
          title="Video resolution"
          aria-label="Video resolution"
        >
          {RESOLUTIONS.map((r) => (
            <option key={r.id} value={r.id} className="bg-[#121316]">
              {r.label}
            </option>
          ))}
        </select>
        <button
          type="button"
          onClick={() => setSoundOn((v) => !v)}
          className={`rounded-full border px-2.5 py-1 ${
            soundOn
              ? 'border-[#b8f000]/40 bg-[#b8f000]/10 text-[#b8f000]'
              : 'border-white/10 bg-white/5 text-white/60'
          }`}
        >
          Sound {soundOn ? 'on' : 'off'}
        </button>
        {soundOn ? (
          <select
            value={speechMode}
            onChange={(e) => setSpeechMode(e.target.value as SpeechMode)}
            className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80"
            title={
              speechMode === 'native_presenter'
                ? 'Seedance generates one voice together with the presenter mouth motion for natural lip-sync.'
                : 'Creative Studio generates an exact separate voiceover; visible people must not lip-sync.'
            }
            aria-label="Speech generation mode"
          >
            <option value="native_presenter" className="bg-[#121316]">
              Native presenter speech
            </option>
            <option value="external_voiceover" className="bg-[#121316]">
              Studio voiceover
            </option>
          </select>
        ) : null}
      </div>
      )}
    </div>
  )

  return (
    <div className="creative-studio-light w-full max-w-[1600px] mx-auto p-2 md:p-4">
      <div className="rounded-2xl border border-[#2a2b30] bg-[#0c0d10] overflow-hidden h-[calc(100vh-7.5rem)] min-h-[520px] flex shadow-soft">
        {/* Chat history sidebar (ChatGPT-style) */}
        <aside
          className={`${
            sidebarOpen ? 'w-[240px] md:w-[260px]' : 'w-0'
          } shrink-0 h-full min-h-0 border-r border-white/10 bg-[#0a0b0e] transition-[width] overflow-hidden flex flex-col`}
        >
          <div className="shrink-0 p-3 border-b border-white/10 space-y-2">
            <button
              type="button"
              onClick={startNewChat}
              className="w-full h-9 rounded-xl bg-[#b8f000] text-black text-xs font-bold hover:brightness-110"
            >
              + New chat
            </button>
            <p className="text-[10px] text-white/35 px-0.5">
              {effectiveBrandName ? `${effectiveBrandName} · ` : 'No brand · '}
              {sessions.length} {sessions.length === 1 ? 'chat' : 'chats'} · this account only
            </p>
          </div>
          <div className="flex-1 min-h-0 overflow-y-scroll cs-panel-scroll p-2 space-y-3">
            {sessionGroups.map((group) => (
              <div key={group.label} className="space-y-1">
                <p className="px-2 text-[10px] font-bold uppercase tracking-wider text-white/35 sticky top-0 bg-[#f8f9fb] py-1 z-[1]">
                  {group.label}
                </p>
                {group.sessions.map((s) => {
              const active = s.id === activeChatId
              return (
                <div
                  key={s.id}
                  role="button"
                  tabIndex={0}
                  onClick={() => switchChat(s.id)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter' || e.key === ' ') switchChat(s.id)
                  }}
                  className={`group w-full text-left rounded-xl px-3 py-2.5 cursor-pointer ${
                    active
                      ? 'bg-white/10 border border-white/15'
                      : 'hover:bg-white/5 border border-transparent'
                  }`}
                >
                      <div className="flex items-start justify-between gap-2 min-w-0">
                        <div className="min-w-0 flex-1">
                          <p className="text-xs font-semibold text-white truncate">
                      {s.title || 'New chat'}
                    </p>
                          <p className="text-[10px] text-white/35 mt-0.5 truncate">
                            {formatChatTime(s.updatedAt)}
                            {s.messages?.length ? ` · ${s.messages.length} msgs` : ''}
                          </p>
                        </div>
                    <button
                      type="button"
                      title="Delete chat"
                      onClick={(e) => deleteChat(s.id, e)}
                          className="opacity-0 group-hover:opacity-100 text-white/40 hover:text-red-300 text-xs shrink-0 leading-none pt-0.5"
                    >
                      ×
                    </button>
                  </div>
                </div>
              )
            })}
              </div>
            ))}
            {!sessions.length && (
              <p className="text-[11px] text-white/35 px-2 py-4">No chats yet</p>
            )}
          </div>
        </aside>

        <div className="flex-1 min-w-0 min-h-0 flex flex-col overflow-hidden">
        <div className="shrink-0 flex items-center justify-between gap-3 px-5 py-3 border-b border-white/10">
          <div className="flex items-center gap-2 min-w-0">
            <button
              type="button"
              onClick={() => setSidebarOpen((o) => !o)}
              className="h-8 w-8 rounded-lg border border-white/15 bg-white/5 text-white/70 text-xs hover:bg-white/10"
              title={sidebarOpen ? 'Hide history' : 'Show history'}
            >
              ☰
            </button>
            <span className="h-6 w-6 rounded-md bg-[#b8f000] text-black font-black text-sm grid place-items-center">
              ~
            </span>
            <div className="min-w-0">
              <p className="text-sm font-bold text-white truncate">{UI.aiAssistant}</p>
              <p className="text-[11px] text-white/45 truncate">
                {sessions.find((s) => s.id === activeChatId)?.title || 'New chat'} · history on the left ·{' '}
                <Link href="/variants" className="text-[#b8f000] underline">
                  {UI.creativeLibrary}
                </Link>
              </p>
            </div>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {isGenerating && activeJobMessage && (
              <button
                type="button"
                onClick={() => void stopGeneration(activeJobMessage)}
                className="h-8 px-3 rounded-full border border-red-400/50 bg-red-500/15 text-red-200 text-[11px] font-bold hover:bg-red-500/25"
                title="Stop generation"
              >
                Stop
              </button>
            )}
            <button type="button" onClick={startNewChat} className="text-[11px] text-white/50 underline">
              New chat
            </button>
          </div>
        </div>

        {!briefId && (
          <div className="px-5 py-2.5 border-b border-white/10 bg-white/[0.03] flex flex-wrap items-center gap-3">
            <label className="flex items-center gap-2 text-xs">
              <span className="font-semibold text-white/45 uppercase tracking-widest text-[10px]">
                Brand
              </span>
              <select
                value={pickedBrandId}
                onChange={(e) => setPickedBrandId(e.target.value)}
                className="rounded-lg border border-white/15 bg-[#16171a] px-2 py-1.5 text-xs text-white"
              >
                <option value="">No brand (optional)</option>
                {(brands || []).map((b) => (
                  <option key={b.id} value={b.id}>
                    {b.name}
                  </option>
                ))}
              </select>
            </label>
          </div>
        )}

        {!hasMessages ? (
          <>
            <div className="flex-1 min-h-0 overflow-y-auto cs-panel-scroll flex flex-col items-center justify-center px-4 py-8">
              <div className="text-center space-y-3 max-w-lg">
              <div className="inline-flex items-center gap-2">
                <span className="h-8 w-8 rounded-lg bg-[#b8f000] text-black font-black grid place-items-center">
                  ~
                </span>
                <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white uppercase">
                  What are we creating today?
                </h2>
              </div>
                <p className="text-sm text-white/45">
                  {promptOnlyVideo
                    ? 'Send a timed prompt directly to Seedance. Product, scene and character references are optional.'
                    : 'Generate a GPT Image 2 starting scene, review or regenerate it, then animate the approved still with Seedance.'}
              </p>
            </div>
            </div>
            <div className="shrink-0 border-t border-white/10 px-4 py-3 bg-[#0c0d10]">
            {composerCard}
          </div>
          </>
        ) : (
          <>
            <div
              ref={threadRef}
              className="flex-1 min-h-0 overflow-y-scroll cs-panel-scroll px-4 md:px-6 py-4 space-y-4"
            >
              {messages.map((m) => {
                const isUser = m.role === 'user'
                const preview = assetUrl(m.mediaUrl || null)
                const messageProjectDuration =
                  m.continuationMeta?.requested_duration_seconds ?? projectDurationSeconds
                const actions =
                  m.status === 'failed' && m.mediaMode === 'video'
                    ? (['generate_video'] as PipelineAction[])
                    : m.suggestedActions && m.suggestedActions.length
                    ? m.suggestedActions
                    : isChapterHandoffReady(m, messageProjectDuration, clipCap)
                      ? (['approve_next'] as PipelineAction[])
                    : m.mediaMode === 'image' && m.status === 'done' && m.mediaUrl
                      ? m.brollIndex
                        ? (['regenerate_image', 'approve_broll'] as PipelineAction[])
                        : (['regenerate_image', 'approve_next'] as PipelineAction[])
                      : m.mediaMode === 'storyboard' &&
                          m.status === 'done' &&
                          m.storyboard?.some((f) => f.url)
                        ? (['regenerate_image', 'approve_next'] as PipelineAction[])
                      : m.phase === 'awaiting_video' &&
                          m.suggestedActions?.includes('approve_next')
                        ? (['approve_next'] as PipelineAction[])
                      : m.phase === 'awaiting_image' && (m.imagePrompt || imagePrompt)
                        ? (['generate_image'] as PipelineAction[])
                        : []

                return (
                  <div key={m.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`w-full max-w-[min(100%,44rem)] rounded-2xl px-4 py-3 space-y-2 ${
                        isUser
                          ? 'bg-[#b8f000]/15 border border-[#b8f000]/25 text-white'
                          : 'bg-white/5 border border-white/10 text-white/90'
                      }`}
                    >
                      <p className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                        {isUser ? 'You' : UI.aiAssistant}
                      </p>
                      <CsMessageContent
                        content={m.content}
                        variant={isUser ? 'user' : 'assistant'}
                      />

                      {!isUser && (m.imagePrompt || m.videoPrompt) && !preview && (
                        <div className="rounded-lg bg-black/30 border border-white/10 p-2 space-y-1 text-[11px] text-white/55">
                          {m.imagePrompt && (
                            <p>
                              <span className="text-[#b8f000] font-semibold">Still: </span>
                              {m.imagePrompt.slice(0, 220)}
                              {m.imagePrompt.length > 220 ? '…' : ''}
                            </p>
                          )}
                          {m.videoPrompt && (
                            <p>
                              <span className="text-[#b8f000] font-semibold">Motion: </span>
                              {m.videoPrompt.slice(0, 220)}
                              {m.videoPrompt.length > 220 ? '…' : ''}
                            </p>
                          )}
                        </div>
                      )}

                      {m.attachments && m.attachments.length > 0 && (
                        <div className="flex flex-wrap gap-2 pt-1">
                          {m.attachments.map((a) =>
                            a.previewUrl ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                key={a.id}
                                src={a.previewUrl}
                                alt={a.name}
                                className="h-20 w-20 rounded-lg object-cover border border-white/15"
                              />
                            ) : (
                              <span
                                key={a.id}
                                className="text-[11px] px-2 py-1 rounded bg-black/30 border border-white/10"
                              >
                                {a.name}
                              </span>
                            ),
                          )}
                        </div>
                      )}

                      {(m.status === 'queued' || m.status === 'running') && (
                        <div className="flex flex-wrap items-center gap-2 pt-0.5">
                          <p className="text-[11px] text-[#b8f000] animate-pulse">
                            {m.progress || 'Working…'}
                          </p>
                          {m.jobId && (
                            <button
                              type="button"
                              onClick={() => void stopGeneration(m)}
                              className="text-[11px] font-bold px-2.5 py-1 rounded-full border border-red-400/45 bg-red-500/15 text-red-200 hover:bg-red-500/25"
                              title="Stop generation (kill switch)"
                            >
                              Stop
                            </button>
                          )}
                        </div>
                      )}
                      {m.status === 'cancelled' && (
                        <p className="text-[11px] text-white/45">Stopped by you</p>
                      )}
                      {m.error && m.status === 'failed' && (
                        <p className="text-[11px] text-red-300">{m.error}</p>
                      )}

                      {!isUser &&
                        m.mediaMode === 'broll_board' &&
                        m.storyboard &&
                        m.storyboard.length > 0 &&
                        (m.storyboard.some((f) => f.url) ||
                          m.status === 'queued' ||
                          m.status === 'running') && (
                          <div className="pt-2 space-y-2">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                              <p className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                                B-roll board · {m.storyboard.length} images
                              </p>
                              <p className="text-[10px] text-white/45">
                                {m.storyboard.filter((f) => f.url).length} ready
                              </p>
                            </div>
                            <p className="text-[10px] text-white/40">
                              Regenerate any dashboard with wrong text. Approve each or use Approve all when ready.
                            </p>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                              {m.storyboard.map((frame) => {
                                const src = assetUrl(frame.url || null)
                                return (
                                  <div
                                    key={frame.id}
                                    className="rounded-xl border border-white/10 overflow-hidden bg-black/40"
                                  >
                                    {src ? (
                                      <button
                                        type="button"
                                        className="block w-full"
                                        onClick={() =>
                                          setPreviewFrame({
                                            src,
                                            title: frame.title || `IMAGE ${frame.index}`,
                                          })
                                        }
                                      >
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                        <img
                                          src={src}
                                          alt={frame.title || 'B-roll'}
                                          className="w-full aspect-square object-cover bg-black"
                                        />
                                      </button>
                                    ) : (
                                      <div className="w-full aspect-square grid place-items-center text-[10px] text-white/35 animate-pulse">
                                        {frame.status === 'running' ? 'Regenerating…' : 'Rendering…'}
                                      </div>
                                    )}
                                    <div className="px-2 py-1.5 border-t border-white/10 space-y-1.5">
                                      <p className="text-[10px] font-semibold text-[#b8f000] truncate">
                                        {frame.title || `IMAGE ${frame.index}`}
                                      </p>
                                      <div className="flex flex-wrap items-center gap-1.5">
                                        <button
                                          type="button"
                                          disabled={busy}
                                          className="text-[9px] px-2 py-0.5 rounded-full border border-white/15 text-white/75"
                                          onClick={() => void regenerateBrollFrame(m, frame)}
                                        >
                                          Regenerate
                                        </button>
                                        {src ? (
                                          <button
                                            type="button"
                                            disabled={busy}
                                            className="text-[9px] px-2 py-0.5 rounded-full border border-[#b8f000]/45 text-[#b8f000]"
                                            onClick={() =>
                                              void handlePipelineAction('approve_broll', {
                                                ...m,
                                                mediaUrl: frame.url,
                                                brollIndex: frame.index,
                                              })
                                            }
                                          >
                                            Approve
                                          </button>
                                        ) : null}
                                      </div>
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )}

                      {!isUser &&
                        m.mediaMode !== 'broll_board' &&
                        m.storyboard &&
                        m.storyboard.length > 0 &&
                        (m.storyboard.some((f) => f.url) ||
                          m.status === 'queued' ||
                          m.status === 'running') && (
                          <div className="pt-2 space-y-2">
                            <div className="flex flex-wrap items-center justify-between gap-2">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                              Storyboard · {m.storyboard.length} scenes
                              </p>
                              <p className="text-[10px] text-white/45">
                                {storyboardFramesForVideo(m.storyboard).length} selected for Seedance
                              </p>
                            </div>
                            <p className="text-[10px] text-white/40">
                              Tick frames to include in video. Discard wrong product/person shots before Approve.
                            </p>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                              {m.storyboard.map((frame) => {
                                const src = assetUrl(frame.url || null)
                                const selected =
                                  Boolean(frame.url) &&
                                  frame.selected !== false &&
                                  !frame.discarded
                                return (
                                  <div
                                    key={frame.id}
                                    className={`rounded-xl border overflow-hidden bg-black/40 ${
                                      frame.discarded
                                        ? 'border-white/10 opacity-45'
                                        : selected
                                          ? 'border-[#b8f000]/70 ring-1 ring-[#b8f000]/40'
                                          : 'border-white/10'
                                    }`}
                                  >
                                    {src ? (
                                      <button
                                        type="button"
                                        className="block w-full"
                                        onClick={() =>
                                          setPreviewFrame({
                                            src,
                                            title: frame.title || `Scene ${frame.index}`,
                                          })
                                        }
                                      >
                                        {/* eslint-disable-next-line @next/next/no-img-element */}
                                      <img
                                        src={src}
                                        alt={frame.title || 'Scene'}
                                        className="w-full aspect-[9/16] object-cover bg-black"
                                      />
                                      </button>
                                    ) : (
                                      <div className="w-full aspect-[9/16] grid place-items-center text-[10px] text-white/35 animate-pulse">
                                        Rendering…
                                      </div>
                                    )}
                                    <div className="px-2 py-1.5 border-t border-white/10 space-y-1.5">
                                      <p className="text-[10px] font-semibold text-[#b8f000] truncate">
                                        {frame.title || `Scene ${frame.index}`}
                                      </p>
                                      {frame.overlays && frame.overlays[0] ? (
                                        <p className="text-[9px] text-white/40 truncate">
                                          {frame.overlays[0]}
                                        </p>
                                      ) : null}
                                      {src ? (
                                        <div className="flex flex-wrap items-center gap-1.5">
                                          <label className="flex items-center gap-1 text-[9px] text-white/70">
                                            <input
                                              type="checkbox"
                                              checked={selected}
                                              disabled={busy || frame.discarded}
                                              onChange={(event) =>
                                                patchStoryboardFrame(m.id, frame.id, {
                                                  selected: event.target.checked,
                                                  discarded: false,
                                                })
                                              }
                                            />
                                            Use
                                          </label>
                                          <button
                                            type="button"
                                            disabled={busy}
                                            className="text-[9px] px-2 py-0.5 rounded-full border border-white/15 text-white/75"
                                            onClick={() =>
                                              setPreviewFrame({
                                                src,
                                                title: frame.title || `Scene ${frame.index}`,
                                              })
                                            }
                                          >
                                            Preview
                                          </button>
                                          <button
                                            type="button"
                                            disabled={busy}
                                            className={`text-[9px] px-2 py-0.5 rounded-full border ${
                                              characterReferenceUrl === frame.url
                                                ? 'border-[#b8f000] bg-[#b8f000]/15 text-[#b8f000]'
                                                : 'border-white/15 text-white/75'
                                            }`}
                                            onClick={() => {
                                              if (!frame.url) return
                                              setCharacterReferenceUrl(frame.url)
                                              patchStoryboardFrame(m.id, frame.id, {
                                                selected: true,
                                                discarded: false,
                                              })
                                              toast.success('Character anchor selected')
                                            }}
                                          >
                                            {characterReferenceUrl === frame.url ? 'Character ✓' : 'Character'}
                                          </button>
                                          <button
                                            type="button"
                                            disabled={busy}
                                            className="text-[9px] px-2 py-0.5 rounded-full border border-red-400/35 text-red-200"
                                            onClick={() => {
                                              if (characterReferenceUrl === frame.url) {
                                                setCharacterReferenceUrl('')
                                              }
                                              patchStoryboardFrame(m.id, frame.id, {
                                                selected: false,
                                                discarded: true,
                                              })
                                            }}
                                          >
                                            Discard
                                          </button>
                                        </div>
                                      ) : null}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )}

                      {preview && m.mediaMode !== 'storyboard' && m.mediaMode !== 'broll_board' && (
                        <div className="space-y-2 pt-1">
                          {m.mediaMode === 'video' ? (
                            <video
                              src={preview}
                              controls
                              playsInline
                              className="w-full max-w-full rounded-xl bg-black border border-white/10 aspect-video object-contain"
                            />
                          ) : (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={preview}
                              alt="Generated still"
                              className="w-full max-w-full max-h-[28rem] object-contain rounded-xl border border-white/10 bg-black"
                            />
                          )}
                          <div className="flex flex-wrap gap-2">
                            {!m.variantId ? (
                              <button
                                type="button"
                                onClick={() => void saveToVariants(m)}
                                className="text-[11px] font-semibold px-3 py-1.5 rounded-full bg-white/10 border border-white/20 text-white"
                              >
                                {UI.saveToCreativeLibrary}
                              </button>
                            ) : (
                              <Link
                                href="/variants"
                                className="text-[11px] font-semibold px-3 py-1.5 rounded-full border border-[#b8f000]/40 text-[#b8f000]"
                              >
                                {UI.openCreativeLibrary}
                              </Link>
                            )}
                            {m.mediaMode === 'image' && m.mediaUrl ? (
                              <button
                                type="button"
                                disabled={busy}
                                onClick={async () => {
                                  const url = m.mediaUrl || ''
                                  setCharacterReferenceUrl(url)
                                  if (url) {
                                    try {
                                      const saved = await assetsApi.registerGenerated({
                                        file_url: url,
                                        brand_id: brandId,
                                        file_name: 'Reusable character reference',
                                        metadata: { role: 'character', reusable: true },
                                      })
                                      setImageLibrary((current) => [
                                        saved,
                                        ...current.filter((asset) => asset.id !== saved.id),
                                      ])
                                    } catch {
                                      // The visual remains usable in this chat even if persistence fails.
                                    }
                                  }
                                  toast.success('Character reference saved for reuse')
                                }}
                                className={`text-[11px] font-semibold px-3 py-1.5 rounded-full border ${
                                  characterReferenceUrl === m.mediaUrl
                                    ? 'border-[#b8f000] bg-[#b8f000]/15 text-[#b8f000]'
                                    : 'border-white/20 bg-white/10 text-white'
                                }`}
                              >
                                {characterReferenceUrl === m.mediaUrl
                                  ? 'Character reference ✓'
                                  : 'Use as character'}
                              </button>
                            ) : null}
                            {m.model && (
                              <span className="text-[10px] text-white/40 self-center">
                                {m.model}
                                {m.durationSeconds ? ` · ${m.durationSeconds}s` : ''}
                              </span>
                            )}
                          </div>
                        </div>
                      )}

                      {!isUser && actions.length > 0 && !busy && (
                        <div className="flex flex-wrap gap-2 pt-2">
                          {actions.map((a) => (
                            <button
                              key={a}
                              type="button"
                              disabled={busy}
                              onClick={() => void handlePipelineAction(a, m)}
                              className={`text-[12px] font-bold px-4 py-2 rounded-full ${
                                a === 'approve_next' ||
                                a === 'approve_broll' ||
                                a === 'approve_all_broll' ||
                                a === 'generate_image' ||
                                a === 'generate_all_broll'
                                  ? 'bg-[#b8f000] text-black hover:brightness-110'
                                  : 'bg-white/10 border border-white/20 text-white hover:bg-white/15'
                              }`}
                            >
                              {a === 'approve_next'
                                ? chapterHandoffLabel(m, clipCap, messageProjectDuration)
                                : ACTION_LABELS[a] || a}
                            </button>
                          ))}
                        </div>
                      )}
                      {!isUser &&
                        m.phase === 'awaiting_image' &&
                        !actions.length &&
                        !busy &&
                        (m.imagePrompt || imagePrompt) && (
                          <button
                            type="button"
                            onClick={() =>
                              void handlePipelineAction('generate_image', m)
                            }
                            className="text-[12px] font-bold px-4 py-2 rounded-full bg-[#b8f000] text-black"
                          >
                            Generate image (GPT Image 2)
                          </button>
                        )}
                    </div>
                  </div>
                )
              })}
              <div className="h-2 shrink-0" aria-hidden />
            </div>
            <div className="shrink-0 border-t border-white/10 px-3 md:px-4 py-2 bg-[#0c0d10]">
              {composerCard}
            </div>
          </>
        )}
        </div>
      </div>

      {previewFrame ? (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setPreviewFrame(null)}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setPreviewFrame(null)
          }}
          role="presentation"
        >
          <div
            className="max-w-3xl w-full rounded-2xl border border-white/15 bg-[#121316] p-4 space-y-3"
            onClick={(event) => event.stopPropagation()}
            role="dialog"
            aria-modal="true"
            aria-label="Storyboard frame preview"
          >
            <div className="flex items-center justify-between gap-3">
              <p className="text-sm font-semibold text-white truncate">{previewFrame.title}</p>
              <button
                type="button"
                className="text-xs px-3 py-1 rounded-full border border-white/20 text-white/80"
                onClick={() => setPreviewFrame(null)}
              >
                Close
              </button>
            </div>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={previewFrame.src}
              alt={previewFrame.title}
              className="w-full max-h-[75vh] object-contain rounded-xl bg-black"
            />
          </div>
        </div>
      ) : null}
    </div>
  )
}
