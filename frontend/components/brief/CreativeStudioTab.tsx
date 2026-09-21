'use client'

import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Link from 'next/link'
import { useApi } from '@/hooks/useApi'
import { generationApi, variantsApi, brandsApi, assetsApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { assetUrl } from '@/lib/utils'
import type { GenerationModelOption } from '@/types'
import {
  emptyCsSession,
  getCsActiveChatId,
  loadCsChatSessions,
  saveCsChatSessions,
  setCsActiveChatId,
  titleFromMessages,
  type CsChatMessage,
  type CsChatSession,
  type CsPipelineAction,
} from '@/lib/csChatHistory'

type ChatMode = 'auto' | 'ask' | 'generate'
type DurationId = 'auto' | '5' | '10' | '15' | '30' | '60' | '120' | '300' | '600'
type AspectId = '9/16' | '1/1' | '16/9' | '4/3'
type ResolutionId = '480p' | '720p' | '1080p'
type PipelineAction = CsPipelineAction

type ChatAttachment = NonNullable<CsChatMessage['attachments']>[number]
type ChatMessage = CsChatMessage

interface Props {
  briefId?: string
  brandId?: string
  briefTitle?: string
  brandName?: string
  productName?: string
  initialPrompt?: string
}

const DURATIONS: { id: DurationId; label: string }[] = [
  { id: 'auto', label: 'Auto · script length' },
  { id: '5', label: '5s' },
  { id: '10', label: '10s' },
  { id: '15', label: '15s' },
  { id: '30', label: '30s' },
  { id: '60', label: '1m' },
  { id: '120', label: '2m' },
  { id: '300', label: '5m' },
  { id: '600', label: '10m max' },
]

const ASPECTS: { id: AspectId; label: string }[] = [
  { id: '9/16', label: '9:16' },
  { id: '1/1', label: '1:1' },
  { id: '16/9', label: '16:9' },
  { id: '4/3', label: '4:3' },
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

const ACTION_LABELS: Record<string, string> = {
  generate_image: 'Generate image (GPT Image 2)',
  regenerate_image: 'Regenerate image',
  approve_next: 'Approve & Next → Seedance video',
  generate_video: 'Generate video',
}

function uid() {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`
}

function formatChatTime(ts: number) {
  try {
    return new Date(ts).toLocaleString(undefined, {
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
    })
  } catch {
    return ''
  }
}

export default function CreativeStudioTab({
  briefId,
  brandId: brandIdProp,
  briefTitle,
  brandName,
  productName,
  initialPrompt,
}: Props) {
  const {
    data: csModels,
    isLoading: catalogLoading,
    error: catalogError,
    refetch: refetchModels,
  } = useApi(
    () => generationApi.creativeStudioModels(),
    [],
    { cacheKey: 'generation/cs-models-v3-pipeline', ttlMs: 60_000 },
  )
  const { data: brands } = useApi(() => brandsApi.list(), [], {
    cacheKey: 'brands/list-cs',
    ttlMs: API_CACHE_TTL.catalog,
  })

  const [pickedBrandId, setPickedBrandId] = useState(brandIdProp || '')
  const brandId = (brandIdProp || pickedBrandId || '').trim() || undefined
  const selectedBrand = (brands || []).find((brand) => brand.id === brandId)
  const effectiveBrandName = brandName || selectedBrand?.name || ''

  const [sessions, setSessions] = useState<CsChatSession[]>([])
  const [activeChatId, setActiveChatId] = useState<string>('')
  const [sidebarOpen, setSidebarOpen] = useState(true)

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [composer, setComposer] = useState(initialPrompt || '')
  const [attachments, setAttachments] = useState<ChatAttachment[]>([])
  const [chatModel, setChatModel] = useState('auto')
  const [mode, setMode] = useState<ChatMode>('auto')
  const [duration, setDuration] = useState<DurationId>('auto')
  const [aspect, setAspect] = useState<AspectId>('9/16')
  const [resolution, setResolution] = useState<ResolutionId>('720p')
  const [soundOn, setSoundOn] = useState(true)
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
  const [additionalReferenceUrls, setAdditionalReferenceUrls] = useState<string[]>([])
  const [phase, setPhase] = useState('')
  const [imageModel, setImageModel] = useState('openai-gpt-image-2')

  const threadRef = useRef<HTMLDivElement>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const activeChatIdRef = useRef('')
  const stoppedJobsRef = useRef<Set<string>>(new Set())
  const pollingJobsRef = useRef<Set<string>>(new Set())
  const skipNextHistorySaveRef = useRef(false)
  const resumeCheckedSessionRef = useRef('')

  const chatModels = useMemo(
    () => (csModels?.chat_models || []) as GenerationModelOption[],
    [csModels],
  )
  const defaultChatModel = csModels?.default_chat_model || 'anthropic/claude-sonnet-4.6'
  const selectedChatLabel = useMemo(() => {
    if (chatModel === 'auto') return 'Auto'
    return chatModels.find((m) => m.id === chatModel)?.label || chatModel
  }, [chatModel, chatModels])

  const applySession = useCallback((session: CsChatSession) => {
    activeChatIdRef.current = session.id
    setActiveChatId(session.id)
    setMessages(session.messages || [])
    setImagePrompt(session.imagePrompt || '')
    setVideoPrompt(session.videoPrompt || '')
    setApprovedImageUrl(session.approvedImageUrl || '')
    setProductReferenceUrl(session.productReferenceUrl || '')
    setLogoReferenceUrl(session.logoReferenceUrl || '')
    setAdditionalReferenceUrls(session.additionalReferenceUrls || [])
    setPhase(session.phase || '')
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
    skipNextHistorySaveRef.current = true
    setHydrated(false)
    const loaded = loadCsChatSessions(briefId, brandId)
    let list = loaded.slice(0, 3)
    let activeId = getCsActiveChatId(briefId, brandId)
    let current = list.find((s) => s.id === activeId)
    if (!current) {
      if (list.length === 0) {
        current = emptyCsSession()
        list = [current]
        saveCsChatSessions(briefId, brandId, list)
      } else {
        current = list[0]
      }
      activeId = current.id
      setCsActiveChatId(briefId, brandId, activeId)
    }
    setSessions(list)
    applySession(current)
    setHydrated(true)
  }, [briefId, brandId, applySession])

  useEffect(() => {
    if (!hydrated || !activeChatId) return
    if (skipNextHistorySaveRef.current) {
      skipNextHistorySaveRef.current = false
      return
    }
    setSessions((prev) => {
      const existing = prev.find((s) => s.id === activeChatId)
      const title =
        messages.length > 0
          ? titleFromMessages(messages)
          : existing?.title && existing.title !== 'New chat'
            ? existing.title
            : 'New chat'
      const nextSession: CsChatSession = {
        id: activeChatId,
        title,
        createdAt: existing?.createdAt || Date.now(),
        updatedAt: Date.now(),
        messages,
        imagePrompt,
        videoPrompt,
        approvedImageUrl,
        productReferenceUrl,
        logoReferenceUrl,
        additionalReferenceUrls,
        phase,
      }
      const next = [nextSession, ...prev.filter((s) => s.id !== activeChatId)].slice(0, 3)
      saveCsChatSessions(briefId, brandId, next)
      setCsActiveChatId(briefId, brandId, activeChatId)
      return next
    })
  }, [
    messages,
    imagePrompt,
    videoPrompt,
    approvedImageUrl,
    productReferenceUrl,
    logoReferenceUrl,
    additionalReferenceUrls,
    phase,
    activeChatId,
    briefId,
    brandId,
    hydrated,
  ])

  useEffect(() => {
    if (!threadRef.current) return
    threadRef.current.scrollTop = threadRef.current.scrollHeight
  }, [messages, busy])

  const startNewChat = () => {
    const session = emptyCsSession()
    setSessions((prev) => {
      const next = [session, ...prev].slice(0, 3)
      saveCsChatSessions(briefId, brandId, next)
      return next
    })
    setCsActiveChatId(briefId, brandId, session.id)
    applySession(session)
  }

  const switchChat = (id: string) => {
    if (id === activeChatId) return
    const session = sessions.find((s) => s.id === id)
    if (!session) return
    setCsActiveChatId(briefId, brandId, id)
    applySession(session)
  }

  const deleteChat = (id: string, e?: React.MouseEvent) => {
    e?.stopPropagation()
    const remaining = sessions.filter((s) => s.id !== id)
    if (remaining.length === 0) {
      const fresh = emptyCsSession()
      saveCsChatSessions(briefId, brandId, [fresh])
      setSessions([fresh])
      setCsActiveChatId(briefId, brandId, fresh.id)
      applySession(fresh)
      return
    }
    saveCsChatSessions(briefId, brandId, remaining)
    setSessions(remaining)
    if (id === activeChatId) {
      setCsActiveChatId(briefId, brandId, remaining[0].id)
      applySession(remaining[0])
    }
  }

  const updateMessage = useCallback((id: string, patch: Partial<ChatMessage>) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)))
  }, [])

  const pollJobIntoMessage = useCallback(
    async (
      jobId: string,
      assistantMsgId: string,
      mediaMode: 'image' | 'video' | 'storyboard',
      sessionId = activeChatId,
    ) => {
      if (pollingJobsRef.current.has(jobId)) return
      pollingJobsRef.current.add(jobId)
      const patchMessage = (patch: Partial<ChatMessage>) => {
        if (!sessionId || sessionId === activeChatIdRef.current) {
          updateMessage(assistantMsgId, patch)
          return
        }
        setSessions((previous) => {
          const next = previous.map((session) =>
            session.id === sessionId
              ? {
                  ...session,
                  updatedAt: Date.now(),
                  messages: session.messages.map((message) =>
                    message.id === assistantMsgId ? { ...message, ...patch } : message,
                  ),
                }
              : session,
          )
          saveCsChatSessions(briefId, brandId, next)
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
            suggestedActions: mediaMode === 'video' ? ['approve_next'] : ['generate_image'],
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
          const board = (res.storyboard || [])
            .filter((f) => f && (f.url || f.title))
            .map((f, i) => ({
              id: String(f.id || `scene-${i + 1}`),
              index: f.index || i + 1,
              title: f.title || `Scene ${i + 1}`,
              url: f.url || undefined,
              imagePrompt: f.image_prompt || undefined,
              overlays: f.overlays || [],
              status: f.status || undefined,
            }))

          patchMessage({
            status: (res.status as ChatMessage['status']) || 'running',
            progress: res.progress || undefined,
            mediaUrl: res.url || undefined,
            seedImageUrl: res.seed_image_url || undefined,
            model: res.model || undefined,
            error: res.error || undefined,
            durationSeconds: res.duration_seconds || undefined,
            ...(done && mediaMode === 'video' && res.note
              ? {
                  content: `${res.partial ? 'Partial video ready.' : 'Video ready.'} ${res.note}`,
                }
              : {}),
            storyboard: board.length ? board : undefined,
            mediaMode:
              mediaMode === 'storyboard' || res.media_mode === 'storyboard'
                ? 'storyboard'
                : mediaMode,
            suggestedActions:
              done &&
              (mediaMode === 'image' || mediaMode === 'storyboard') &&
              (res.url || board.some((b) => b.url))
                ? ['regenerate_image', 'approve_next']
                : failed || cancelled
                  ? ['generate_image']
                  : [],
            phase: done
              ? mediaMode === 'video'
                ? 'done'
                : 'awaiting_video'
              : failed || cancelled
                ? cancelled
                  ? 'cancelled'
                  : 'failed'
                : mediaMode === 'storyboard'
                  ? 'storyboard_running'
                  : mediaMode === 'image'
                    ? 'image_running'
                    : 'video_running',
          })
          if (cancelled) {
            toast('Generation stopped', { id: 'cs-stop' })
            setBusy(false)
            return
          }
          if (done && (res.url || board.some((b) => b.url)) && mediaMode !== 'video') {
            const hero =
              board.find((b) => /reveal|feature|close|product/i.test(b.title || ''))?.url ||
              board.find((b) => b.url)?.url ||
              res.url
            if (hero) setApprovedImageUrl(hero)
            setPhase('awaiting_video')
            toast.success(
              mediaMode === 'storyboard'
                ? `Storyboard ready — ${board.filter((b) => b.url).length} scenes. Approve & Next for video.`
                : 'Still ready — Approve & Next, or Regenerate',
            )
            return
          }
          if (done && res.url && mediaMode === 'video') {
            setPhase('done')
            const warn = res.duration_warning || res.note || ''
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
          if (/job not found|server may have restarted|\b404\b/i.test(pollMessage)) {
            patchMessage({
              status: 'failed',
              progress: 'Generation interrupted',
              error:
                'This generation stopped when the backend restarted. Start a new generation; no further segments are being submitted.',
              suggestedActions: ['generate_image'],
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
      })
    },
    [activeChatId, brandId, briefId, updateMessage],
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
        const role: ChatAttachment['role'] =
          /logo|wordmark|brandmark/i.test(file.name)
            ? 'logo'
            : !productAssigned
              ? 'product'
              : 'reference'
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
        if (role === 'reference') {
          setAdditionalReferenceUrls((prev) =>
            Array.from(new Set([...prev, url])).slice(0, 7),
          )
        }
        toast.success(`${role === 'logo' ? 'Logo' : role === 'product' ? 'Product' : 'Reference'} image attached`)
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
    setAdditionalReferenceUrls((prev) => prev.filter((url) => url !== attachment.url))
    if (role === 'product') setProductReferenceUrl(attachment.url)
    if (role === 'logo') setLogoReferenceUrl(attachment.url)
    if (role === 'reference') {
      setAdditionalReferenceUrls((prev) =>
        Array.from(new Set([...prev, attachment.url])).slice(0, 7),
      )
    }
  }

  const removeAttachment = (attachment: ChatAttachment) => {
    setAttachments((prev) => prev.filter((item) => item.id !== attachment.id))
    if (productReferenceUrl === attachment.url) setProductReferenceUrl('')
    if (logoReferenceUrl === attachment.url) setLogoReferenceUrl('')
    setAdditionalReferenceUrls((prev) => prev.filter((url) => url !== attachment.url))
  }

  const saveToVariants = async (msg: ChatMessage) => {
    if (!msg.mediaUrl) return
    if (!briefId && !brandId) {
      toast.error('Select a brand (or open from a brief) to save to Variants')
      return
    }
    try {
      const variant = await variantsApi.createFromMedia({
        media_url: msg.mediaUrl,
        media_mode: msg.mediaMode || 'video',
        aspect,
        model: msg.model || (msg.mediaMode === 'image' ? imageModel : 'ark-seedance-2-0'),
        prompt: msg.videoPrompt || msg.imagePrompt || msg.content,
        duration_seconds: msg.durationSeconds,
        seed_image_url: msg.seedImageUrl || approvedImageUrl || null,
        brief_id: briefId || undefined,
        brand_id: brandId || undefined,
        brief_title: briefTitle || brandName || 'Creative Studio',
        product_name: productName || '',
      })
      updateMessage(msg.id, { variantId: variant.id })
      toast.success('Saved to Variants library')
    } catch (err) {
      toast.error(extractApiError(err, 'Could not save to Variants'))
    }
  }

  const runTurn = async (opts: {
    userText?: string
    userAttachments?: ChatAttachment[]
    action?: PipelineAction
    revisionNotes?: string
    appendUser?: boolean
    imagePromptOverride?: string
    videoPromptOverride?: string
    approvedImageOverride?: string
    storyboardImageUrls?: string[]
  }) => {
    if (busy) return
    const action = opts.action || 'continue'
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
    const turnProductRef = attachedProduct || productReferenceUrl || ''
    const turnLogoRef = attachedLogo || logoReferenceUrl || selectedBrand?.logo_url || ''
    const turnAdditionalRefs = Array.from(
      new Set([...additionalReferenceUrls, ...attachedReferences]),
    ).filter((url) => url !== turnProductRef && url !== turnLogoRef).slice(0, 7)
    if (attachedProduct) setProductReferenceUrl(attachedProduct)
    if (attachedLogo) setLogoReferenceUrl(attachedLogo)
    if (attachedReferences.length) setAdditionalReferenceUrls(turnAdditionalRefs)
    const boardUrls =
      opts.storyboardImageUrls ||
      messages
        .flatMap((m) => m.storyboard || [])
        .map((f) => f.url)
        .filter((u): u is string => Boolean(u))
        .slice(0, 9)

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
        content: userText || `(${action.replace(/_/g, ' ')})`,
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

    const pendingId = uid()
    setMessages((prev) => [
      ...prev,
      {
        id: pendingId,
        role: 'assistant',
        content:
          action === 'generate_image' || action === 'regenerate_image'
            ? 'Generating GPT Image 2 still…'
            : action === 'approve_next' || action === 'generate_video'
              ? 'Starting Seedance 2.0…'
              : 'Thinking…',
        status: 'running',
      },
    ])

    try {
      const res = await generationApi.creativeStudioChat({
        messages: historyForApi,
        mode,
        chat_model: chatModel,
        duration_seconds: duration === 'auto' ? undefined : Number(duration),
        aspect,
        resolution,
        sound_on: soundOn,
        attachment_urls: turnProductRef
          ? [turnProductRef, ...userAttachments.map((a) => a.url).filter((u) => u !== turnProductRef)]
          : userAttachments.map((a) => a.url),
        brand_name: effectiveBrandName,
        product_name: productName || '',
        action,
        image_prompt: imgP,
        video_prompt: vidP,
        approved_image_url: approved,
        product_reference_url: turnProductRef,
        logo_reference_url: turnLogoRef,
        additional_reference_urls: turnAdditionalRefs,
        storyboard_image_urls: boardUrls,
        image_model: imageModel,
        revision_notes: opts.revisionNotes || '',
        phase,
      })

      if (res.image_prompt) setImagePrompt(res.image_prompt)
      if (res.video_prompt) setVideoPrompt(res.video_prompt)
      if (res.approved_image_url) setApprovedImageUrl(res.approved_image_url)
      if (res.product_reference_url) setProductReferenceUrl(res.product_reference_url)
      if (res.phase) setPhase(res.phase)
      if (res.image_model) setImageModel(res.image_model)

      const mediaMode =
        res.media_mode === 'image' ||
        res.media_mode === 'video' ||
        res.media_mode === 'storyboard'
          ? res.media_mode
          : undefined

      const suggested = (res.suggested_actions || []).filter(Boolean) as PipelineAction[]

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
        storyboard: Array.isArray((res as { storyboard_scenes?: unknown }).storyboard_scenes)
          ? (
              (res as { storyboard_scenes: Record<string, unknown>[] }).storyboard_scenes || []
            ).map((s, i) => ({
              id: String(s.id || `scene-${i + 1}`),
              index: Number(s.index || i + 1),
              title: String(s.title || `Scene ${i + 1}`),
              imagePrompt: String(s.image_prompt || ''),
              overlays: Array.isArray(s.overlays) ? (s.overlays as string[]) : [],
            }))
          : undefined,
      })

      if (res.job_id && mediaMode) {
        void pollJobIntoMessage(res.job_id, pendingId, mediaMode)
      }
    } catch (err) {
      const msg = extractApiError(err, 'Chat failed')
      updateMessage(pendingId, { content: msg, status: 'failed', error: msg })
      toast.error(msg)
    } finally {
      setBusy(false)
    }
  }

  const handleSend = async () => {
    const text = composer.trim()
    const atts = [...attachments]
    setComposer('')
    setAttachments([])
    await runTurn({ userText: text, userAttachments: atts, action: 'continue', appendUser: true })
  }

  const handlePipelineAction = async (action: PipelineAction, fromMsg?: ChatMessage) => {
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
      approvedImageOverride: nextApproved || undefined,
      storyboardImageUrls: (fromMsg?.storyboard || [])
        .map((f) => f.url)
        .filter((u): u is string => Boolean(u))
        .slice(0, 9),
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
    <div className="w-full max-w-3xl mx-auto">
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
                    event.target.value as 'product' | 'logo' | 'reference',
                  )
                }
                className="mt-1 block w-full max-w-28 rounded bg-black/70 px-1 py-0.5 text-[9px] text-white"
                title="How this image should be used"
              >
                <option value="product">Product</option>
                <option value="logo">Brand logo</option>
                <option value="reference">Scene/style</option>
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

      <div className="rounded-2xl border border-white/10 bg-[#1a1b1e] shadow-xl overflow-hidden">
        <textarea
          value={composer}
          onChange={(e) => setComposer(e.target.value)}
          onKeyDown={onKeyDown}
          rows={hasMessages ? 3 : 4}
          placeholder="Make a 10s UGC product video for my campaign…"
          className="w-full resize-none bg-transparent px-4 pt-4 pb-2 text-[15px] text-white placeholder:text-white/35 focus:outline-none"
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
            onClick={() => fileInputRef.current?.click()}
            className="h-9 w-9 rounded-full border border-white/15 bg-white/5 text-white/80 hover:bg-white/10 text-lg"
            title="Upload reference"
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

      <div className="mt-3 flex flex-wrap items-center gap-2 justify-center text-[11px] text-white/50">
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
          Still · GPT Image 2 storyboard
        </span>
        <span className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1">
          Video · Seedance 2.0
        </span>
        {productReferenceUrl ? (
          <span className="rounded-full border border-[#b8f000]/30 bg-[#b8f000]/10 text-[#b8f000] px-2.5 py-1">
            Product photo locked
          </span>
        ) : null}
        <span className="rounded-full border border-[#b8f000]/30 bg-[#b8f000]/10 text-[#b8f000] px-2.5 py-1">
          {phaseLabel}
        </span>
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
        <select
          value={aspect}
          onChange={(e) => setAspect(e.target.value as AspectId)}
          className="rounded-full border border-white/10 bg-white/5 px-2.5 py-1 text-white/80"
        >
          {ASPECTS.map((a) => (
            <option key={a.id} value={a.id} className="bg-[#121316]">
              {a.label}
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
      </div>
    </div>
  )

  return (
    <div className="w-full max-w-[1600px] mx-auto p-4 md:p-6">
      <div className="rounded-2xl border border-[#2a2b30] bg-[#0c0d10] overflow-hidden min-h-[72vh] flex shadow-soft">
        {/* Chat history sidebar (ChatGPT-style) */}
        <aside
          className={`${
            sidebarOpen ? 'w-[240px] md:w-[260px]' : 'w-0'
          } shrink-0 border-r border-white/10 bg-[#0a0b0e] transition-[width] overflow-hidden flex flex-col`}
        >
          <div className="p-3 border-b border-white/10 space-y-2">
            <button
              type="button"
              onClick={startNewChat}
              className="w-full h-9 rounded-xl bg-[#b8f000] text-black text-xs font-bold hover:brightness-110"
            >
              + New chat
            </button>
            <p className="text-[10px] text-white/35 px-0.5">Saved in this browser</p>
          </div>
          <div className="flex-1 overflow-y-auto p-2 space-y-1">
            {sessions.map((s) => {
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
                  <div className="flex items-start justify-between gap-2">
                    <p className="text-xs font-semibold text-white truncate flex-1">
                      {s.title || 'New chat'}
                    </p>
                    <button
                      type="button"
                      title="Delete chat"
                      onClick={(e) => deleteChat(s.id, e)}
                      className="opacity-0 group-hover:opacity-100 text-white/40 hover:text-red-300 text-xs shrink-0"
                    >
                      ×
                    </button>
                  </div>
                  <p className="text-[10px] text-white/35 mt-0.5">
                    {formatChatTime(s.updatedAt)}
                    {s.messages?.length ? ` · ${s.messages.length} msgs` : ''}
                  </p>
                </div>
              )
            })}
            {!sessions.length && (
              <p className="text-[11px] text-white/35 px-2 py-4">No chats yet</p>
            )}
          </div>
        </aside>

        <div className="flex-1 min-w-0 flex flex-col">
        <div className="flex items-center justify-between gap-3 px-5 py-3 border-b border-white/10">
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
              <p className="text-sm font-bold text-white truncate">Creative Studio</p>
              <p className="text-[11px] text-white/45 truncate">
                {sessions.find((s) => s.id === activeChatId)?.title || 'New chat'} · history on the left ·{' '}
                <Link href="/variants" className="text-[#b8f000] underline">
                  Variants
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
                <option value="">Select brand…</option>
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
          <div className="flex-1 flex flex-col items-center justify-center px-4 py-12 gap-8">
            <div className="text-center space-y-3">
              <div className="inline-flex items-center gap-2">
                <span className="h-8 w-8 rounded-lg bg-[#b8f000] text-black font-black grid place-items-center">
                  ~
                </span>
                <h2 className="text-2xl md:text-3xl font-bold tracking-tight text-white uppercase">
                  What are we creating today?
                </h2>
              </div>
              <p className="text-sm text-white/45 max-w-lg mx-auto">
                Like Higgsfield Supercomputer: we draft a plan, generate a GPT Image 2 background
                still, you approve or regenerate, then Seedance 2.0 animates that frame.
              </p>
            </div>
            {composerCard}
          </div>
        ) : (
          <>
            <div ref={threadRef} className="flex-1 overflow-y-auto px-4 md:px-8 py-6 space-y-4">
              {messages.map((m) => {
                const isUser = m.role === 'user'
                const preview = assetUrl(m.mediaUrl || null)
                const actions =
                  m.suggestedActions && m.suggestedActions.length
                    ? m.suggestedActions
                    : m.mediaMode === 'image' && m.status === 'done' && m.mediaUrl
                      ? (['regenerate_image', 'approve_next'] as PipelineAction[])
                      : m.mediaMode === 'storyboard' &&
                          m.status === 'done' &&
                          m.storyboard?.some((f) => f.url)
                        ? (['regenerate_image', 'approve_next'] as PipelineAction[])
                      : m.phase === 'awaiting_image' && (m.imagePrompt || imagePrompt)
                        ? (['generate_image'] as PipelineAction[])
                        : []

                return (
                  <div key={m.id} className={`flex ${isUser ? 'justify-end' : 'justify-start'}`}>
                    <div
                      className={`max-w-[min(100%,42rem)] rounded-2xl px-4 py-3 space-y-2 ${
                        isUser
                          ? 'bg-[#b8f000]/15 border border-[#b8f000]/25 text-white'
                          : 'bg-white/5 border border-white/10 text-white/90'
                      }`}
                    >
                      <p className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                        {isUser ? 'You' : 'Creative Studio'}
                      </p>
                      <p className="text-sm whitespace-pre-wrap leading-relaxed">{m.content}</p>

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
                        m.storyboard &&
                        m.storyboard.length > 0 &&
                        (m.storyboard.some((f) => f.url) ||
                          m.status === 'queued' ||
                          m.status === 'running') && (
                          <div className="pt-2 space-y-2">
                            <p className="text-[10px] font-bold uppercase tracking-widest text-white/40">
                              Storyboard · {m.storyboard.length} scenes
                            </p>
                            <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                              {m.storyboard.map((frame) => {
                                const src = assetUrl(frame.url || null)
                                return (
                                  <div
                                    key={frame.id}
                                    className="rounded-xl border border-white/10 bg-black/40 overflow-hidden"
                                  >
                                    {src ? (
                                      // eslint-disable-next-line @next/next/no-img-element
                                      <img
                                        src={src}
                                        alt={frame.title || 'Scene'}
                                        className="w-full aspect-[9/16] object-cover bg-black"
                                      />
                                    ) : (
                                      <div className="w-full aspect-[9/16] grid place-items-center text-[10px] text-white/35 animate-pulse">
                                        Rendering…
                                      </div>
                                    )}
                                    <div className="px-2 py-1.5 border-t border-white/10">
                                      <p className="text-[10px] font-semibold text-[#b8f000] truncate">
                                        {frame.title || `Scene ${frame.index}`}
                                      </p>
                                      {frame.overlays && frame.overlays[0] ? (
                                        <p className="text-[9px] text-white/40 truncate">
                                          {frame.overlays[0]}
                                        </p>
                                      ) : null}
                                    </div>
                                  </div>
                                )
                              })}
                            </div>
                          </div>
                        )}

                      {preview && m.mediaMode !== 'storyboard' && (
                        <div className="space-y-2 pt-1">
                          {m.mediaMode === 'video' ? (
                            <video
                              src={preview}
                              controls
                              className="w-full max-h-80 rounded-xl bg-black border border-white/10"
                            />
                          ) : (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img
                              src={preview}
                              alt="Generated still"
                              className="w-full max-h-80 object-contain rounded-xl border border-white/10 bg-black"
                            />
                          )}
                          <div className="flex flex-wrap gap-2">
                            {!m.variantId ? (
                              <button
                                type="button"
                                onClick={() => void saveToVariants(m)}
                                className="text-[11px] font-semibold px-3 py-1.5 rounded-full bg-white/10 border border-white/20 text-white"
                              >
                                Save to Variants
                              </button>
                            ) : (
                              <Link
                                href="/variants"
                                className="text-[11px] font-semibold px-3 py-1.5 rounded-full border border-[#b8f000]/40 text-[#b8f000]"
                              >
                                Open Variants
                              </Link>
                            )}
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
                        <div className="flex flex-wrap gap-2 pt-2 sticky bottom-0">
                          {actions.map((a) => (
                            <button
                              key={a}
                              type="button"
                              disabled={busy}
                              onClick={() => void handlePipelineAction(a, m)}
                              className={`text-[12px] font-bold px-4 py-2 rounded-full ${
                                a === 'approve_next' || a === 'generate_image'
                                  ? 'bg-[#b8f000] text-black hover:brightness-110'
                                  : 'bg-white/10 border border-white/20 text-white hover:bg-white/15'
                              }`}
                            >
                              {ACTION_LABELS[a] || a}
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
            </div>
            <div className="border-t border-white/10 px-4 py-4 bg-[#0c0d10]">{composerCard}</div>
          </>
        )}
        </div>
      </div>
    </div>
  )
}
