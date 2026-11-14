'use client'

import React, { ChangeEvent, useEffect, useMemo, useRef, useState } from 'react'
import Topbar from '@/components/layout/Topbar'
import Button from '@/components/ui/Button'
import { useApi } from '@/hooks/useApi'
import { API_CACHE_TTL } from '@/lib/apiCache'
import { variantsApi } from '@/lib/api'
import { getVariantPreviewUrls } from '@/lib/variantMedia'
import { useActiveBrand } from '@/hooks/useActiveBrand'
import type { Variant } from '@/types'
import { cn } from '@/lib/utils'

type AspectId = '9:16' | '1:1' | '4:5' | '16:9' | '1080:1320'
type TextPosition = 'top' | 'centre' | 'bottom'
type EditorSource = {
  id: string
  name: string
  url: string
  kind: 'video' | 'image'
  brandId?: string
  temporary?: boolean
}
type EditorDraft = {
  sourceId: string | null
  projectName: string
  aspect: AspectId
  trimStart: number
  trimEnd: number
  overlayText: string
  overlayStart: number
  overlayEnd: number
  textPosition: TextPosition
  textSize: number
  volume: number
  muted: boolean
}

const DRAFT_KEY = 'creative-studio-video-editor-draft-v1'
const initialDraft: EditorDraft = {
  sourceId: null,
  projectName: 'Untitled video edit',
  aspect: '9:16',
  trimStart: 0,
  trimEnd: 0,
  overlayText: '',
  overlayStart: 0,
  overlayEnd: 5,
  textPosition: 'bottom',
  textSize: 36,
  volume: 1,
  muted: false,
}
const aspectClasses: Record<AspectId, string> = {
  '9:16': 'aspect-[9/16] max-h-[54vh]',
  '1:1': 'aspect-square max-h-[54vh]',
  '4:5': 'aspect-[4/5] max-h-[54vh]',
  '16:9': 'aspect-video max-w-4xl',
  '1080:1320': 'aspect-[9/11] max-h-[54vh]',
}
const positionClasses: Record<TextPosition, string> = {
  top: 'top-[8%]',
  centre: 'top-1/2 -translate-y-1/2',
  bottom: 'bottom-[8%]',
}

function sourceFromVariant(variant: Variant): EditorSource | null {
  const { videoUrl, imageUrl } = getVariantPreviewUrls(variant)
  const url = videoUrl || imageUrl
  if (!url) return null
  return {
    id: variant.id,
    name: variant.headline || variant.hook || 'Untitled creative',
    url,
    kind: videoUrl ? 'video' : 'image',
    brandId: variant.brand_id,
  }
}

function clock(seconds: number) {
  const value = Number.isFinite(seconds) ? Math.max(0, seconds) : 0
  const minutes = Math.floor(value / 60)
  return `${String(minutes).padStart(2, '0')}:${(value - minutes * 60).toFixed(1).padStart(4, '0')}`
}
function clamp(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value))
}

export default function VideoEditorPage() {
  const { activeBrandId } = useActiveBrand()
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const uploadRef = useRef<HTMLInputElement | null>(null)
  const [draft, setDraft] = useState(initialDraft)
  const [localSources, setLocalSources] = useState<EditorSource[]>([])
  const [duration, setDuration] = useState(0)
  const [currentTime, setCurrentTime] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [savedAt, setSavedAt] = useState<string | null>(null)
  const [hydrated, setHydrated] = useState(false)
  const { data: variants, isLoading, error } = useApi(
    () => variantsApi.list({ limit: 300 }),
    [],
    { cacheKey: 'video-editor/library', ttlMs: API_CACHE_TTL.variants },
  )

  const librarySources = useMemo(
    () => (variants ?? [])
      .filter((variant) => !activeBrandId || variant.brand_id === activeBrandId)
      .map(sourceFromVariant)
      .filter((source): source is EditorSource => Boolean(source)),
    [variants, activeBrandId],
  )
  const sources = useMemo(() => [...localSources, ...librarySources], [localSources, librarySources])
  const selected = sources.find((source) => source.id === draft.sourceId) ?? null
  const overlayVisible = Boolean(draft.overlayText.trim()) && currentTime >= draft.overlayStart && currentTime <= draft.overlayEnd
  const update = (patch: Partial<EditorDraft>) => setDraft((value) => ({ ...value, ...patch }))

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(DRAFT_KEY)
      if (stored) setDraft({ ...initialDraft, ...(JSON.parse(stored) as Partial<EditorDraft>) })
    } catch { /* ignore an invalid local draft */ }
    setHydrated(true)
  }, [])
  useEffect(() => {
    if (!hydrated) return
    const timer = window.setTimeout(() => {
      window.localStorage.setItem(DRAFT_KEY, JSON.stringify(draft))
      setSavedAt(new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }))
    }, 350)
    return () => window.clearTimeout(timer)
  }, [draft, hydrated])
  useEffect(() => {
    if (!videoRef.current) return
    videoRef.current.volume = clamp(draft.volume, 0, 1)
    videoRef.current.muted = draft.muted
  }, [draft.volume, draft.muted, selected])

  const selectSource = (source: EditorSource) => {
    setDuration(0)
    setCurrentTime(0)
    setIsPlaying(false)
    setDraft((value) => ({
      ...value,
      sourceId: source.id,
      projectName: value.projectName === initialDraft.projectName ? `${source.name} edit` : value.projectName,
      trimStart: 0,
      trimEnd: 0,
      overlayStart: 0,
      overlayEnd: 5,
    }))
  }
  const onUpload = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    const kind = file.type.startsWith('video/') ? 'video' : file.type.startsWith('image/') ? 'image' : null
    if (!kind) return
    const source: EditorSource = { id: `local-${Date.now()}`, name: file.name, url: URL.createObjectURL(file), kind, temporary: true }
    setLocalSources((value) => [source, ...value])
    selectSource(source)
    event.target.value = ''
  }
  const onLoadedMetadata = () => {
    const nextDuration = videoRef.current?.duration || 0
    setDuration(nextDuration)
    setDraft((value) => ({
      ...value,
      trimStart: clamp(value.trimStart, 0, nextDuration),
      trimEnd: value.trimEnd > value.trimStart ? clamp(value.trimEnd, value.trimStart, nextDuration) : nextDuration,
      overlayEnd: clamp(value.overlayEnd || 5, 0, nextDuration),
    }))
  }
  const seek = (value: number) => {
    const next = clamp(value, draft.trimStart, draft.trimEnd || duration)
    setCurrentTime(next)
    if (videoRef.current) videoRef.current.currentTime = next
  }
  const togglePlayback = async () => {
    const video = videoRef.current
    if (!video || selected?.kind !== 'video') return
    if (!video.paused) return video.pause()
    if (video.currentTime < draft.trimStart || video.currentTime >= (draft.trimEnd || duration)) seek(draft.trimStart)
    await video.play()
  }
  const onTimeUpdate = () => {
    const video = videoRef.current
    if (!video) return
    if (video.currentTime >= (draft.trimEnd || duration)) {
      video.pause()
      video.currentTime = draft.trimStart
    }
    setCurrentTime(video.currentTime)
  }
  const reset = () => {
    if (!window.confirm('Reset this local editor draft? Creative Library media will not be deleted.')) return
    setDraft(initialDraft)
    setDuration(0)
    setCurrentTime(0)
    window.localStorage.removeItem(DRAFT_KEY)
  }

  return (
    <div className="min-h-screen bg-[#eef1f4]">
      <Topbar
        title="Video Editor"
        subtitle="Independent editing workspace · no AI generation calls"
        actions={<div className="flex items-center gap-2">
          <span className="hidden text-[11px] text-lt sm:inline">{savedAt ? `Draft saved ${savedAt}` : 'Local autosave ready'}</span>
          <Button variant="outline" size="sm" onClick={reset}>Reset</Button>
          <Button variant="primary" size="sm" disabled={!selected} title="Server rendering is the next isolated editor milestone">Export (next step)</Button>
        </div>}
      />

      <div className="grid min-h-[calc(100vh-64px)] grid-cols-1 xl:grid-cols-[270px_minmax(0,1fr)_270px]">
        <aside className="border-r border-border bg-white p-3 xl:h-[calc(100vh-64px)] xl:overflow-y-auto">
          <div className="flex items-center justify-between gap-2">
            <div><h2 className="text-sm font-bold text-navy">Media</h2><p className="text-[10px] text-lt">Creative Library and uploads</p></div>
            <Button variant="outline" size="sm" onClick={() => uploadRef.current?.click()}>Upload</Button>
            <input ref={uploadRef} className="hidden" type="file" accept="video/*,image/*" onChange={onUpload} />
          </div>
          <div className="mt-3 grid grid-cols-2 gap-2 xl:grid-cols-1">
            {isLoading && <p className="col-span-full py-8 text-center text-xs text-lt">Loading Creative Library…</p>}
            {error && <p className="col-span-full rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700">Library unavailable. Local upload still works.</p>}
            {!isLoading && !error && sources.length === 0 && <p className="col-span-full rounded-lg border border-dashed border-border p-4 text-center text-xs text-lt">No media for this brand.</p>}
            {sources.map((source) => <button key={source.id} type="button" onClick={() => selectSource(source)} className={cn('overflow-hidden rounded-lg border text-left', source.id === draft.sourceId ? 'border-accent ring-2 ring-accent/20' : 'border-border hover:border-accent/60')}>
              <div className="relative aspect-video bg-black">
                {source.kind === 'video' ? <video src={source.url} className="h-full w-full object-cover" muted preload="metadata" /> : <img src={source.url} alt="" className="h-full w-full object-cover" />}
                <span className="absolute left-1.5 top-1.5 rounded bg-black/70 px-1.5 py-0.5 text-[8px] font-bold uppercase text-white">{source.kind}</span>
              </div>
              <p className="truncate px-2 py-1.5 text-[10px] font-semibold text-navy">{source.name}</p>
            </button>)}
          </div>
        </aside>

        <main className="flex min-w-0 flex-col">
          <section className="flex min-h-[430px] flex-1 items-center justify-center overflow-hidden bg-[#17191d] p-5">
            {!selected ? <div className="max-w-md text-center"><div className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-white/10 text-3xl">▶</div><h2 className="mt-4 text-lg font-bold text-white">Choose media to begin</h2><p className="mt-1 text-sm text-white/55">Select Creative Library media or upload a file. This does not call the AI Assistant.</p></div> :
              <div className="flex h-full w-full flex-col items-center justify-center gap-3">
                <div className={cn('relative mx-auto w-full overflow-hidden bg-black shadow-2xl', aspectClasses[draft.aspect])}>
                  {selected.kind === 'video' ? <video key={selected.id} ref={videoRef} src={selected.url} className="h-full w-full object-contain" playsInline preload="metadata" onLoadedMetadata={onLoadedMetadata} onTimeUpdate={onTimeUpdate} onPlay={() => setIsPlaying(true)} onPause={() => setIsPlaying(false)} /> : <img src={selected.url} alt="" className="h-full w-full object-contain" />}
                  {overlayVisible && <div className={cn('pointer-events-none absolute inset-x-[6%] text-center', positionClasses[draft.textPosition])}><span className="inline-block max-w-full rounded-md bg-black/65 px-3 py-1.5 font-extrabold leading-tight text-white shadow-lg" style={{ fontSize: `${draft.textSize}px` }}>{draft.overlayText}</span></div>}
                </div>
                {selected.kind === 'video' && <div className="flex w-full max-w-3xl items-center gap-3 rounded-xl bg-black/35 px-3 py-2 text-white">
                  <button type="button" onClick={togglePlayback} className="w-8 text-lg">{isPlaying ? '❚❚' : '▶'}</button>
                  <span className="w-[54px] text-[10px] tabular-nums">{clock(currentTime)}</span>
                  <input className="min-w-0 flex-1 accent-[#9ed365]" type="range" min={draft.trimStart} max={draft.trimEnd || duration || 0.1} step="0.05" value={clamp(currentTime, draft.trimStart, draft.trimEnd || duration || 0.1)} onChange={(event) => seek(Number(event.target.value))} />
                  <span className="w-[54px] text-right text-[10px] tabular-nums">{clock(draft.trimEnd || duration)}</span>
                </div>}
              </div>}
          </section>

          <section className="border-t border-border bg-white p-3">
            <div className="mb-2 flex items-center justify-between"><div><h2 className="text-xs font-bold text-navy">Timeline</h2><p className="text-[9px] text-lt">Preview trial · FFmpeg export comes next</p></div><span className="text-[10px] tabular-nums text-lt">{clock(draft.trimStart)} – {clock(draft.trimEnd || duration)}</span></div>
            {[['Video', selected?.name || 'No source'], ['Text', draft.overlayText || 'No text overlay'], ['Audio', draft.muted ? 'Muted' : `${Math.round(draft.volume * 100)}% source audio`]].map(([label, value], index) => <div key={label} className="mb-1.5 grid grid-cols-[55px_1fr] items-center gap-2"><span className="text-[9px] font-bold uppercase text-lt">{label}</span><div className={cn('flex h-8 items-center overflow-hidden rounded-md px-2 text-[9px] font-semibold', index === 0 ? 'bg-[#28384a] text-white' : index === 1 ? 'bg-[#dff0ca] text-navy' : 'bg-[#e8f3df] text-[#466b25]')}>{value}</div></div>)}
          </section>
        </main>

        <aside className="border-l border-border bg-white p-4 xl:h-[calc(100vh-64px)] xl:overflow-y-auto">
          <h2 className="text-sm font-bold text-navy">Edit settings</h2><p className="text-[10px] text-lt">Saved locally while testing.</p>
          <label className="mt-4 block text-[9px] font-bold uppercase text-lt">Project name</label><input className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-xs" value={draft.projectName} onChange={(event) => update({ projectName: event.target.value })} />
          <label className="mt-4 block text-[9px] font-bold uppercase text-lt">Canvas ratio</label><div className="mt-1 grid grid-cols-3 gap-1.5">{(Object.keys(aspectClasses) as AspectId[]).map((aspect) => <button key={aspect} type="button" onClick={() => update({ aspect })} className={cn('rounded-md border px-1 py-2 text-[10px] font-bold', draft.aspect === aspect ? 'border-accent bg-accent/10 text-navy' : 'border-border text-lt')}>{aspect}</button>)}</div>

          <div className="mt-5 border-t border-border pt-4"><h3 className="text-xs font-bold text-navy">Trim</h3><div className="mt-2 grid grid-cols-2 gap-2">
            <label className="text-[9px] text-lt">Start<input className="mt-1 w-full rounded-md border border-border px-2 py-1.5 text-xs" type="number" min={0} max={draft.trimEnd || duration} step="0.1" value={draft.trimStart} onChange={(event) => { const value = clamp(Number(event.target.value), 0, draft.trimEnd || duration); update({ trimStart: value }); seek(value) }} /></label>
            <label className="text-[9px] text-lt">End<input className="mt-1 w-full rounded-md border border-border px-2 py-1.5 text-xs" type="number" min={draft.trimStart} max={duration} step="0.1" value={draft.trimEnd || 0} onChange={(event) => update({ trimEnd: clamp(Number(event.target.value), draft.trimStart, duration) })} /></label>
          </div></div>

          <div className="mt-5 border-t border-border pt-4"><h3 className="text-xs font-bold text-navy">Text / CTA</h3><textarea className="mt-2 min-h-20 w-full rounded-lg border border-border px-3 py-2 text-xs" placeholder="Exact on-screen text" value={draft.overlayText} onChange={(event) => update({ overlayText: event.target.value })} />
            <div className="mt-2 grid grid-cols-2 gap-2"><label className="text-[9px] text-lt">Show from<input className="mt-1 w-full rounded-md border border-border px-2 py-1.5 text-xs" type="number" min={0} max={duration} step="0.1" value={draft.overlayStart} onChange={(event) => update({ overlayStart: clamp(Number(event.target.value), 0, draft.overlayEnd) })} /></label><label className="text-[9px] text-lt">Until<input className="mt-1 w-full rounded-md border border-border px-2 py-1.5 text-xs" type="number" min={draft.overlayStart} max={duration} step="0.1" value={draft.overlayEnd} onChange={(event) => update({ overlayEnd: clamp(Number(event.target.value), draft.overlayStart, duration) })} /></label></div>
            <div className="mt-2 grid grid-cols-3 gap-1.5">{(['top', 'centre', 'bottom'] as TextPosition[]).map((position) => <button key={position} type="button" onClick={() => update({ textPosition: position })} className={cn('rounded-md border px-2 py-1.5 text-[9px] font-bold capitalize', draft.textPosition === position ? 'border-accent bg-accent/10' : 'border-border text-lt')}>{position}</button>)}</div>
            <label className="mt-3 block text-[9px] text-lt">Text size · {draft.textSize}px<input className="mt-1 w-full accent-[#82bd4f]" type="range" min={18} max={72} value={draft.textSize} onChange={(event) => update({ textSize: Number(event.target.value) })} /></label>
          </div>

          <div className="mt-5 border-t border-border pt-4"><div className="flex items-center justify-between"><h3 className="text-xs font-bold text-navy">Source audio</h3><button type="button" onClick={() => update({ muted: !draft.muted })} className={cn('rounded-md border px-2 py-1 text-[9px] font-bold', draft.muted ? 'border-red-300 bg-red-50 text-red-700' : 'border-border')}>{draft.muted ? 'Muted' : 'Sound on'}</button></div><label className="mt-2 block text-[9px] text-lt">Volume · {Math.round(draft.volume * 100)}%<input className="mt-1 w-full accent-[#82bd4f]" type="range" min={0} max={1} step={0.01} value={draft.volume} onChange={(event) => update({ volume: Number(event.target.value) })} /></label></div>
          <div className="mt-5 rounded-lg border border-blue-200 bg-blue-50 p-3 text-[10px] leading-relaxed text-blue-900"><strong>Isolated:</strong> this page reads completed media only. It does not modify Projects, AI Assistant chat, prompts, settings or provider continuations.</div>
        </aside>
      </div>
    </div>
  )
}
