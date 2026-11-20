'use client'

import React, { useEffect, useState } from 'react'
import { generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { assetUrl } from '@/lib/utils'
import type { CreativeStudioEndCardResult, CreativeStudioEndCardSpec } from '@/types'

interface Props {
  open: boolean
  onClose: () => void
  /** The finished video the card is laid over. The original is never changed. */
  videoUrl: string
  /** Logo to use (composer logo, else the Brand kit logo). */
  logoUrl?: string | null
  /** Text and timing taken from the script's closing scene, when a script was planned. */
  initial?: CreativeStudioEndCardSpec | null
  onDone: (result: CreativeStudioEndCardResult) => void
}

const DEFAULT_BUTTON = '#1D6FE8'
const DEFAULT_ACCENT = '#2FA862'

export default function EndCardModal({ open, onClose, videoUrl, logoUrl, initial, onDone }: Props) {
  const [headline, setHeadline] = useState('')
  const [sublines, setSublines] = useState('')
  const [buttonText, setButtonText] = useState('')
  const [hold, setHold] = useState(4)
  const [buttonHex, setButtonHex] = useState(DEFAULT_BUTTON)
  const [accentHex, setAccentHex] = useState(DEFAULT_ACCENT)
  const [busy, setBusy] = useState<'preview' | 'apply' | null>(null)
  const [error, setError] = useState('')
  const [preview, setPreview] = useState<CreativeStudioEndCardResult | null>(null)

  // Fill from the script each time the window opens for a video.
  useEffect(() => {
    if (!open) return
    setHeadline(initial?.headline || '')
    setSublines((initial?.sublines || []).join('\n'))
    setButtonText(initial?.button_text || '')
    setHold(Math.min(6, Math.max(2, Math.round(initial?.hold_seconds || 4))))
    setButtonHex(DEFAULT_BUTTON)
    setAccentHex(DEFAULT_ACCENT)
    setPreview(null)
    setError('')
    setBusy(null)
  }, [open, videoUrl, initial])

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !busy) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, busy, onClose])

  if (!open) return null

  const subLineList = sublines
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean)
  const tooMany = subLineList.length > 3
  const canRun = !busy && headline.trim().length > 0 && !tooMany

  const request = (previewOnly: boolean) =>
    generationApi.creativeStudioEndCard({
      video_url: videoUrl,
      headline: headline.trim(),
      sublines: subLineList,
      button_text: buttonText.trim(),
      logo_url: logoUrl || null,
      button_hex: buttonHex,
      accent_hex: accentHex,
      hold_seconds: hold,
      preview: previewOnly,
    })

  const run = async (previewOnly: boolean) => {
    setBusy(previewOnly ? 'preview' : 'apply')
    setError('')
    try {
      const result = await request(previewOnly)
      if (previewOnly) setPreview(result)
      else {
        onDone(result)
        onClose()
      }
    } catch (err) {
      setError(extractApiError(err, 'Could not build the end card. Try again.'))
    } finally {
      setBusy(null)
    }
  }

  const stale = (fn: () => void) => () => {
    fn()
    setPreview(null) // a changed field makes the old preview wrong
  }

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Add end card"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !busy) onClose()
      }}
    >
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#121316] text-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div>
            <h2 className="text-base font-semibold">Add end card</h2>
            <p className="text-xs text-white/55">
              Your logo and the exact text, laid over the last seconds. No AI and no credits are used. The original video is kept.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={Boolean(busy)}
            className="h-8 w-8 rounded-full text-lg text-white/70 hover:bg-white/10 disabled:opacity-40"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="cs-message-scroll flex-1 overflow-y-auto px-5 py-4">
          <div className="grid gap-5 md:grid-cols-2">
            <div className="space-y-3">
              <label className="block text-xs text-white/60">
                Headline
                <input
                  value={headline}
                  onChange={(e) => stale(() => setHeadline(e.target.value))()}
                  maxLength={120}
                  disabled={Boolean(busy)}
                  placeholder="FREE GOOGLE ADS AUDIT"
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                />
              </label>
              <label className="block text-xs text-white/60">
                Lines under the headline (one per line, up to 3)
                <textarea
                  value={sublines}
                  onChange={(e) => stale(() => setSublines(e.target.value))()}
                  rows={3}
                  disabled={Boolean(busy)}
                  placeholder="NO FEES. NO OBLIGATION."
                  className="mt-1 w-full resize-none rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                />
                {tooMany && <span className="text-[11px] text-red-300">Use at most 3 lines.</span>}
              </label>
              <label className="block text-xs text-white/60">
                Button text (optional)
                <input
                  value={buttonText}
                  onChange={(e) => stale(() => setButtonText(e.target.value))()}
                  maxLength={120}
                  disabled={Boolean(busy)}
                  placeholder="BOOK YOUR FREE AUDIT"
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                />
              </label>
              <div className="flex flex-wrap items-center gap-4 text-xs text-white/60">
                <label className="flex items-center gap-2">
                  Shown for
                  <select
                    value={hold}
                    onChange={(e) => stale(() => setHold(Number(e.target.value)))()}
                    disabled={Boolean(busy)}
                    className="rounded-full border border-white/15 bg-[#1a1b1e] px-2.5 py-1 text-xs text-white"
                  >
                    {[2, 3, 4, 5, 6].map((s) => (
                      <option key={s} value={s}>
                        last {s}s
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-2">
                  Button
                  <input type="color" value={buttonHex} onChange={(e) => stale(() => setButtonHex(e.target.value))()} disabled={Boolean(busy)} className="h-6 w-8 cursor-pointer rounded border-0 bg-transparent" />
                </label>
                <label className="flex items-center gap-2">
                  Accent
                  <input type="color" value={accentHex} onChange={(e) => stale(() => setAccentHex(e.target.value))()} disabled={Boolean(busy)} className="h-6 w-8 cursor-pointer rounded border-0 bg-transparent" />
                </label>
              </div>
              <p className="text-[11px] text-white/45">
                {logoUrl
                  ? 'The logo is your attached or Brand kit logo, placed exactly as uploaded: scaled, never recoloured or stretched.'
                  : 'No logo is attached or saved on the brand, so the card will have text only. Attach a logo with the Logo role or add one to the brand first.'}
              </p>
            </div>

            <div>
              <div className="mb-2 text-xs font-bold uppercase tracking-wide text-white/60">Preview on the real frame</div>
              <div className="flex min-h-[260px] items-center justify-center rounded-xl border border-white/10 bg-black/40 p-2">
                {busy === 'preview' ? (
                  <span className="text-xs text-white/55">Building preview…</span>
                ) : preview ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img src={assetUrl(preview.url) || undefined} alt="End card preview" className="max-h-[52vh] w-auto rounded-lg" />
                ) : (
                  <span className="px-6 text-center text-xs text-white/45">
                    Press Preview to see exactly how the card will look on your video before it is applied.
                  </span>
                )}
              </div>
              {preview && (
                <p className="mt-2 text-[11px] text-white/50">
                  Appears at {preview.start_seconds}s and stays for the last {preview.hold_seconds}s. {preview.theme === 'dark' ? 'Dark card (your logo is light-coloured).' : 'White card.'}
                </p>
              )}
              {preview && preview.warnings.length > 0 && (
                <div className="mt-2 rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  {preview.warnings.join(' ')}
                </div>
              )}
            </div>
          </div>

          {error && (
            <div className="mt-4 rounded-lg border border-red-400/40 bg-red-500/15 px-3 py-2 text-sm text-red-200">{error}</div>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-white/10 px-5 py-3">
          <button
            type="button"
            onClick={onClose}
            disabled={Boolean(busy)}
            className="rounded-full border border-white/15 px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:opacity-40"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={() => void run(true)}
            disabled={!canRun}
            className="rounded-full border border-[#b8f000]/50 px-4 py-2 text-xs font-semibold text-[#b8f000] hover:bg-[#b8f000]/10 disabled:opacity-40"
          >
            {busy === 'preview' ? 'Building preview…' : 'Preview'}
          </button>
          <button
            type="button"
            onClick={() => void run(false)}
            disabled={!canRun || !preview}
            title={!preview ? 'Preview first, so you see the card before it is applied' : undefined}
            className="rounded-full bg-[#b8f000] px-5 py-2 text-xs font-bold text-black hover:brightness-95 disabled:opacity-40"
          >
            {busy === 'apply' ? 'Adding end card…' : 'Add to video'}
          </button>
        </div>
      </div>
    </div>
  )
}
