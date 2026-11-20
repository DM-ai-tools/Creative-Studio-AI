'use client'

import React, { useEffect, useState } from 'react'
import { generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { assetUrl } from '@/lib/utils'
import type { CreativeStudioInsertsResult, CreativeStudioLogoCorner, CreativeStudioStill } from '@/types'

const CORNERS: { id: CreativeStudioLogoCorner; label: string; place: string }[] = [
  { id: 'top_left', label: 'Top left', place: 'left-1.5 top-1.5' },
  { id: 'top_right', label: 'Top right', place: 'right-1.5 top-1.5' },
  { id: 'bottom_left', label: 'Bottom left', place: 'bottom-1.5 left-1.5' },
  { id: 'bottom_right', label: 'Bottom right', place: 'bottom-1.5 right-1.5' },
]

interface Props {
  open: boolean
  onClose: () => void
  /** The finished video the pictures are laid over. The original is never changed. */
  videoUrl: string
  /** Screens and graphics the script planner wants as pictures. */
  stills: CreativeStudioStill[]
  /** Image models that can draw them (GPT Image 2, Seedream). */
  imageModels: { id: string; label: string }[]
  defaultModel: string
  aspect: string
  brandId?: string
  brandName?: string
  /** Brand logo to place inside each picture. Without it the corner picker is hidden. */
  logoUrl?: string | null
  /** Dark version of the logo for light pictures, when the brand kit has one. */
  logoOnLightUrl?: string | null
  onDone: (result: CreativeStudioInsertsResult) => void
}

type Row = {
  id: string
  label: string
  prompt: string
  start: string
  length: string
  include: boolean
  /** The picture as drawn, without the logo. Kept so the corner can change without drawing again. */
  clean: string
  /** The picture that goes into the video: the clean one, with the logo placed when a corner is chosen. */
  url: string
  /** What happened with the logo on this picture (which version, or a problem). */
  logoNote: string
  logoProblem: boolean
  busy: boolean
  error: string
}

const num = (value: string) => {
  const n = Number(value)
  return Number.isFinite(n) ? n : NaN
}

export default function StillInsertsModal({
  open,
  onClose,
  videoUrl,
  stills,
  imageModels,
  defaultModel,
  aspect,
  brandId,
  brandName,
  logoUrl,
  logoOnLightUrl,
  onDone,
}: Props) {
  const [rows, setRows] = useState<Row[]>([])
  const [model, setModel] = useState(defaultModel)
  // '' means no logo. A brand with a logo starts with it top right, the usual place.
  const [corner, setCorner] = useState<CreativeStudioLogoCorner | ''>('')
  const [logoBusy, setLogoBusy] = useState(false)
  const [applying, setApplying] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    if (!open) return
    setRows(
      stills.map((s) => ({
        id: s.id,
        label: s.label,
        prompt: s.image_prompt,
        start: String(s.start),
        length: String(Math.min(6, Math.max(2, Math.round(s.duration * 2) / 2))),
        include: true,
        clean: '',
        url: '',
        logoNote: '',
        logoProblem: false,
        busy: false,
        error: '',
      })),
    )
    setModel(imageModels.some((m) => m.id === defaultModel) ? defaultModel : imageModels[0]?.id || defaultModel)
    setCorner(logoUrl ? 'top_right' : '')
    setLogoBusy(false)
    setError('')
    setApplying(false)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, videoUrl, stills])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !applying && !rows.some((r) => r.busy)) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, applying, rows, onClose])

  if (!open) return null

  const patch = (id: string, change: Partial<Row>) => setRows((prev) => prev.map((r) => (r.id === id ? { ...r, ...change } : r)))
  const anyBusy = rows.some((r) => r.busy) || logoBusy

  // Put the real logo inside a drawn picture. If that fails, the plain picture is still usable.
  const withLogo = async (cleanUrl: string, where: CreativeStudioLogoCorner | '') => {
    if (!where || !logoUrl) return { url: cleanUrl, note: '', problem: false }
    try {
      const res = await generationApi.creativeStudioStillLogo({
        image_url: cleanUrl,
        corner: where,
        logo_url: logoUrl,
        logo_on_light_url: logoOnLightUrl || null,
      })
      const used = `${res.logo_version} on a ${res.background} picture`
      return res.warnings.length
        ? { url: res.url, note: res.warnings[0], problem: true }
        : { url: res.url, note: `Logo added: ${used}`, problem: false }
    } catch (err) {
      return { url: cleanUrl, note: extractApiError(err, 'The logo could not be added to this picture.'), problem: true }
    }
  }

  const generate = async (id: string) => {
    const row = rows.find((r) => r.id === id)
    if (!row || !row.prompt.trim()) return
    patch(id, { busy: true, error: '' })
    try {
      const res = await generationApi.creativeStudioStill({
        prompt: row.prompt.trim(),
        model,
        aspect,
        brand_id: brandId || '',
        brand_name: brandName || '',
        // The model leaves this corner empty so the logo never lands on text.
        logo_corner: logoUrl ? corner : '',
      })
      const placed = await withLogo(res.url, corner)
      patch(id, { clean: res.url, url: placed.url, logoNote: placed.note, logoProblem: placed.problem, busy: false })
    } catch (err) {
      patch(id, { busy: false, error: extractApiError(err, 'Could not draw this picture. Try again.') })
    }
  }

  // Moving the logo to another corner (or taking it off) reuses the drawn pictures: no new drawing, no credits.
  const changeCorner = async (next: CreativeStudioLogoCorner | '') => {
    setCorner(next)
    const drawn = rows.filter((r) => r.clean)
    if (drawn.length === 0) return
    setLogoBusy(true)
    try {
      for (const row of drawn) {
        const placed = await withLogo(row.clean, next)
        patch(row.id, { url: placed.url, logoNote: placed.note, logoProblem: placed.problem })
      }
    } finally {
      setLogoBusy(false)
    }
  }

  const generateAll = async () => {
    for (const row of rows) {
      if (row.include && !row.url) await generate(row.id)
    }
  }

  const ready = rows.filter((r) => r.include && r.url)
  const windows = ready.map((r) => ({ id: r.id, start: num(r.start), length: num(r.length) }))
  const invalid = windows.some((w) => !(w.start >= 0) || !(w.length >= 1 && w.length <= 10))
  const sorted = [...windows].sort((a, b) => a.start - b.start)
  const overlap = sorted.some((w, i) => i > 0 && w.start < sorted[i - 1].start + sorted[i - 1].length - 1e-6)
  const canApply = ready.length > 0 && !invalid && !overlap && !applying && !anyBusy

  const apply = async () => {
    setApplying(true)
    setError('')
    try {
      const result = await generationApi.creativeStudioInserts({
        video_url: videoUrl,
        inserts: ready.map((r) => ({ image_url: r.url, start_seconds: num(r.start), duration_seconds: num(r.length) })),
      })
      onDone(result)
      onClose()
    } catch (err) {
      setError(extractApiError(err, 'Could not add the pictures to the video. Try again.'))
    } finally {
      setApplying(false)
    }
  }

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Add screens"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !applying && !anyBusy) onClose()
      }}
    >
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#121316] text-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div>
            <h2 className="text-base font-semibold">Add screens</h2>
            <p className="text-xs text-white/55">
              Each screen is drawn as a picture by an image model, then shown over your video for its seconds. The text stays exactly as
              you approve it, and the voice keeps playing. Your original video is kept.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={applying || anyBusy}
            className="h-8 w-8 rounded-full text-lg text-white/70 hover:bg-white/10 disabled:opacity-40"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="cs-message-scroll flex-1 space-y-4 overflow-y-auto px-5 py-4">
          <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-white/70">
            <label className="flex items-center gap-2">
              Image model
              <select
                value={model}
                onChange={(e) => setModel(e.target.value)}
                disabled={anyBusy || applying}
                className="rounded-full border border-white/15 bg-[#1a1b1e] px-2.5 py-1 text-xs text-white"
              >
                {imageModels.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.label}
                  </option>
                ))}
              </select>
            </label>
            {logoUrl && (
              <div className="flex items-center gap-2" role="group" aria-label="Logo corner">
                <span>Logo corner</span>
                <div
                  className={`relative rounded-md border border-white/20 bg-black/40 ${/16[/:]9/.test(aspect) ? 'h-10 w-16' : 'h-16 w-10'}`}
                >
                  {CORNERS.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      title={c.label}
                      aria-label={c.label}
                      aria-pressed={corner === c.id}
                      disabled={anyBusy || applying}
                      onClick={() => void changeCorner(c.id)}
                      className={`absolute h-3.5 w-3.5 rounded-sm border disabled:opacity-40 ${c.place} ${
                        corner === c.id ? 'border-[#b8f000] bg-[#b8f000]' : 'border-white/40 hover:bg-white/25'
                      }`}
                    />
                  ))}
                </div>
                <button
                  type="button"
                  aria-pressed={corner === ''}
                  disabled={anyBusy || applying}
                  onClick={() => void changeCorner('')}
                  className={`rounded-full border px-2.5 py-1 text-xs disabled:opacity-40 ${
                    corner === '' ? 'border-[#b8f000] text-[#b8f000]' : 'border-white/15 text-white/70 hover:bg-white/10'
                  }`}
                >
                  No logo
                </button>
              </div>
            )}
            <span className="text-white/50">
              Each picture uses one image generation.{' '}
              {logoUrl
                ? 'The logo is placed in the corner you pick, in the light or dark version that suits the picture, and that corner is kept free of text. Changing the corner later costs nothing.'
                : 'Check the spelling before you add them.'}
            </span>
          </div>

          {rows.map((row) => (
            <div key={row.id} className="rounded-xl border border-white/10 bg-white/[0.03] p-3">
              <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                <label className="flex items-center gap-2 text-sm font-semibold">
                  <input
                    type="checkbox"
                    checked={row.include}
                    onChange={(e) => patch(row.id, { include: e.target.checked })}
                    className="accent-[#b8f000]"
                  />
                  {row.label}
                </label>
                <div className="flex items-center gap-3 text-xs text-white/60">
                  <label className="flex items-center gap-1">
                    Starts at
                    <input
                      value={row.start}
                      onChange={(e) => patch(row.id, { start: e.target.value })}
                      inputMode="decimal"
                      className="w-14 rounded border border-white/15 bg-black/30 px-1.5 py-0.5 text-white"
                    />
                    s
                  </label>
                  <label className="flex items-center gap-1">
                    for
                    <input
                      value={row.length}
                      onChange={(e) => patch(row.id, { length: e.target.value })}
                      inputMode="decimal"
                      className="w-12 rounded border border-white/15 bg-black/30 px-1.5 py-0.5 text-white"
                    />
                    s
                  </label>
                </div>
              </div>
              <div className="grid gap-3 sm:grid-cols-[1fr_160px]">
                <div>
                  <textarea
                    value={row.prompt}
                    onChange={(e) => patch(row.id, { prompt: e.target.value, url: '', clean: '', logoNote: '', logoProblem: false })}
                    rows={4}
                    disabled={row.busy}
                    className="cs-message-scroll w-full resize-y rounded-lg border border-white/10 bg-black/30 p-2 text-xs text-white focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                  />
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => void generate(row.id)}
                      disabled={row.busy || !row.prompt.trim() || applying}
                      className="rounded-full border border-[#b8f000]/50 px-3 py-1 text-xs font-semibold text-[#b8f000] hover:bg-[#b8f000]/10 disabled:opacity-40"
                    >
                      {row.busy ? 'Drawing…' : row.url ? 'Draw again' : 'Draw picture'}
                    </button>
                    {row.error && <span className="text-xs text-red-300">{row.error}</span>}
                  </div>
                </div>
                <div className="flex min-h-[120px] flex-col items-center justify-center gap-1 rounded-lg border border-white/10 bg-black/40 p-1">
                  {row.url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={assetUrl(row.url) || undefined} alt={row.label} className="max-h-44 w-auto rounded" />
                  ) : (
                    <span className="px-2 text-center text-[11px] text-white/45">{row.busy ? 'Drawing…' : 'No picture yet'}</span>
                  )}
                  {row.url && row.logoNote && (
                    <span className={`px-1 text-center text-[10px] ${row.logoProblem ? 'text-amber-300' : 'text-white/50'}`}>{row.logoNote}</span>
                  )}
                </div>
              </div>
            </div>
          ))}

          {rows.length === 0 && <p className="text-sm text-white/60">This script has no screens to draw.</p>}
          {overlap && (
            <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
              Two pictures overlap in time. Change a start time or length so each has its own seconds.
            </div>
          )}
          {error && <div className="rounded-lg border border-red-400/40 bg-red-500/15 px-3 py-2 text-sm text-red-200">{error}</div>}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-white/10 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={applying || anyBusy}
            className="rounded-full border border-white/15 px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void generateAll()}
            disabled={anyBusy || applying || !rows.some((r) => r.include && !r.url)}
            className="rounded-full border border-[#b8f000]/50 px-4 py-2 text-xs font-semibold text-[#b8f000] hover:bg-[#b8f000]/10 disabled:opacity-40"
          >
            Draw all pictures
          </button>
          <button
            type="button"
            onClick={() => void apply()}
            disabled={!canApply}
            title={ready.length === 0 ? 'Draw at least one picture first' : undefined}
            className="rounded-full bg-[#b8f000] px-5 py-2 text-xs font-bold text-black hover:brightness-95 disabled:opacity-40"
          >
            {applying ? 'Adding to video…' : `Add ${ready.length || ''} to video`.replace('  ', ' ')}
          </button>
        </div>
      </div>
    </div>
  )
}
