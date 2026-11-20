'use client'

import React, { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import { generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import type { CreativeStudioEndCardSpec, CreativeStudioScriptPlan, CreativeStudioStill } from '@/types'

interface Props {
  open: boolean
  onClose: () => void
  /**
   * Receives the compiled prompt and the end card text from the script. The tab drops the prompt
   * into its normal prompt box (nothing is sent) and keeps the end card text for later.
   */
  onUsePrompt: (prompt: string, endCard: CreativeStudioEndCardSpec | null, stills: CreativeStudioStill[]) => void
  chatModel: string
  videoModel: string
  /** Seedance models to choose from (same list as the composer). */
  videoModelOptions: { id: string; label: string }[]
  /** Changes the composer's video model, so planning and generation always use the same one. */
  onVideoModelChange: (id: string) => void
  /** Account is locked to Seedance 2.5: show it, do not offer a choice. */
  videoModelLocked?: boolean
  aspect: string
  speechMode: 'native_presenter' | 'external_voiceover'
  brandId?: string
  brandName?: string
  productName?: string
}

const ACCEPT = '.docx,.txt,.md'

function clock(seconds: number) {
  const s = Math.max(0, Math.round(seconds))
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`
}

function editListText(plan: CreativeStudioScriptPlan) {
  return plan.edit_list
    .map(
      (e) =>
        `${clock(e.start)}-${clock(e.end)}  [${e.kind}]  Scene ${e.scene} (${e.scene_title})\n${e.note}`,
    )
    .join('\n\n')
}

export default function ScriptPlanModal({
  open,
  onClose,
  onUsePrompt,
  chatModel,
  videoModel,
  videoModelOptions,
  onVideoModelChange,
  videoModelLocked = false,
  aspect,
  speechMode,
  brandId,
  brandName,
  productName,
}: Props) {
  const fileRef = useRef<HTMLInputElement>(null)
  const [file, setFile] = useState<File | null>(null)
  const [scriptText, setScriptText] = useState('')
  const [notes, setNotes] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [plan, setPlan] = useState<CreativeStudioScriptPlan | null>(null)
  const [prompt, setPrompt] = useState('')
  const [includeText, setIncludeText] = useState(false)
  const [promptEdited, setPromptEdited] = useState(false)

  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !loading) onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, loading, onClose])

  if (!open) return null

  const canPlan = !loading && (!!file || scriptText.trim().length > 0)

  const runPlan = async () => {
    setLoading(true)
    setError('')
    try {
      const result = await generationApi.creativeStudioScriptPlan({
        file,
        scriptText: file ? '' : scriptText,
        chatModel,
        videoModel,
        aspect,
        speechMode,
        brandId,
        brandName,
        productName,
        notes,
      })
      setPlan(result)
      setPrompt(result.canonical_prompt)
      setIncludeText(false)
      setPromptEdited(false)
    } catch (err) {
      setError(extractApiError(err, 'Could not plan this script. Try again.'))
    } finally {
      setLoading(false)
    }
  }

  const reset = () => {
    setPlan(null)
    setPrompt('')
    setIncludeText(false)
    setPromptEdited(false)
    setError('')
  }

  const toggleIncludeText = (next: boolean) => {
    if (!plan) return
    if (promptEdited && !window.confirm('Switching replaces the prompt and discards your edits. Continue?')) return
    setIncludeText(next)
    setPrompt(next ? plan.canonical_prompt_with_text : plan.canonical_prompt)
    setPromptEdited(false)
  }

  const usePrompt = () => {
    if (!prompt.trim()) return
    onUsePrompt(prompt, plan?.end_card ?? null, plan?.stills ?? [])
    toast.success(
      plan?.stills?.length
        ? 'Prompt added to the box. When the video is ready, use "Add screens" and "Add end card" under it.'
        : plan?.end_card
        ? 'Prompt added to the box. When the video is ready, use "Add end card" under it.'
        : 'Prompt added to the box. Review it, then press Generate as usual.',
    )
    onClose()
  }

  const copy = async (text: string, label: string) => {
    try {
      await navigator.clipboard.writeText(text)
      toast.success(`${label} copied`)
    } catch {
      toast.error('Could not copy. Select the text and copy it manually.')
    }
  }

  const voiceSummary = plan
    ? plan.voice.gender
      ? `${plan.voice.accent} ${plan.voice.gender} voice (${plan.voice.gender} chosen by your script)`
      : `${plan.voice.accent} voice (your script names no male or female, so the system default is used)`
    : ''
  const modelLabel =
    videoModelOptions.find((m) => m.id === videoModel)?.label ||
    (/2-5|2\.5/i.test(videoModel) ? 'Seedance 2.5 · 30s clips' : 'Seedance 2.0 · 15s clips')
  const planIsStale = !!plan && plan.video_model !== videoModel
  const speechSummary =
    speechMode === 'native_presenter' ? 'Seedance speaks the voiceover' : 'OpenAI narration is added afterwards'

  return (
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/70 p-3 sm:p-6"
      role="dialog"
      aria-modal="true"
      aria-label="Plan from script"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget && !loading) onClose()
      }}
    >
      <div className="flex max-h-[92vh] w-full max-w-4xl flex-col overflow-hidden rounded-2xl border border-white/10 bg-[#121316] text-white shadow-2xl">
        <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
          <div>
            <h2 className="text-base font-semibold">Plan from script</h2>
            <p className="text-xs text-white/55">
              Reads your script and writes the timed prompt. Nothing is generated and no video credits are used.
            </p>
          </div>
          <button
            type="button"
            onClick={onClose}
            disabled={loading}
            className="h-8 w-8 rounded-full text-lg text-white/70 hover:bg-white/10 disabled:opacity-40"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        <div className="cs-message-scroll flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {!plan ? (
            <>
              <div className="rounded-xl border border-dashed border-white/20 bg-white/[0.03] p-4">
                <input
                  ref={fileRef}
                  type="file"
                  accept={ACCEPT}
                  className="hidden"
                  onChange={(e) => {
                    const picked = e.target.files?.[0] || null
                    setFile(picked)
                    setError('')
                    e.target.value = ''
                  }}
                />
                <div className="flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => fileRef.current?.click()}
                    disabled={loading}
                    className="rounded-full bg-[#b8f000] px-4 py-2 text-xs font-bold text-black hover:brightness-95 disabled:opacity-50"
                  >
                    Upload script (.docx, .txt, .md)
                  </button>
                  {file ? (
                    <span className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs">
                      {file.name}
                      <button
                        type="button"
                        onClick={() => setFile(null)}
                        className="text-white/60 hover:text-white"
                        aria-label="Remove file"
                      >
                        ×
                      </button>
                    </span>
                  ) : (
                    <span className="text-xs text-white/50">or paste the script below</span>
                  )}
                </div>
                {!file && (
                  <textarea
                    value={scriptText}
                    onChange={(e) => setScriptText(e.target.value)}
                    rows={9}
                    disabled={loading}
                    placeholder="Paste your script: scenes, voiceover lines, visual direction, on-screen text, durations…"
                    className="cs-message-scroll mt-3 w-full resize-y rounded-lg border border-white/10 bg-black/30 p-3 text-sm text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                  />
                )}
              </div>

              <label className="block text-xs text-white/60">
                Notes for the planner (optional)
                <input
                  value={notes}
                  onChange={(e) => setNotes(e.target.value)}
                  disabled={loading}
                  maxLength={1500}
                  placeholder="e.g. keep the same presenter in every scene"
                  className="mt-1 w-full rounded-lg border border-white/10 bg-black/30 px-3 py-2 text-sm text-white placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                />
              </label>

              <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                <label className="flex items-center gap-2 text-xs text-white/70">
                  Video model
                  {videoModelLocked ? (
                    <span className="rounded-full bg-white/10 px-2.5 py-1 font-semibold text-white">{modelLabel}</span>
                  ) : (
                    <select
                      value={videoModel}
                      onChange={(e) => onVideoModelChange(e.target.value)}
                      disabled={loading}
                      className="rounded-full border border-white/15 bg-[#1a1b1e] px-2.5 py-1 text-xs text-white focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                    >
                      {videoModelOptions.map((m) => (
                        <option key={m.id} value={m.id}>
                          {m.label}
                        </option>
                      ))}
                    </select>
                  )}
                </label>
                <span className="text-[11px] text-white/50">
                  Scenes are cut to this model&apos;s clip limit. Seedance 2.5 allows longer clips (30s) than 2.0 (15s).
                </span>
              </div>

              <p className="text-[11px] text-white/45">
                Also uses: {aspect.replace('/', ':')} · {speechSummary}. Change those in the composer before planning if
                needed. The voice is always Australian English; if the script says &quot;female voice&quot; or &quot;male
                voice&quot;, that is used.
              </p>

              {error && (
                <div className="rounded-lg border border-red-400/40 bg-red-500/15 px-3 py-2 text-sm text-red-200">
                  {error}
                </div>
              )}
            </>
          ) : (
            <>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                {[
                  ['Length', `${plan.total_seconds}s`],
                  ['Scenes', String(plan.scenes.length)],
                  ['Editing items', String(plan.edit_count)],
                  [
                    'Clip limit',
                    `${plan.clip_cap_seconds}s · ${/2-5|2\.5/i.test(plan.video_model) ? 'Seedance 2.5' : /gemini/i.test(plan.video_model) ? 'Gemini Omni' : 'Seedance 2.0'}`,
                  ],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                    <div className="text-[10px] uppercase tracking-wide text-white/45">{label}</div>
                    <div className="text-lg font-semibold">{value}</div>
                  </div>
                ))}
              </div>

              <div className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs text-white/80">
                <span className="font-semibold text-[#b8f000]">Voice: </span>
                {voiceSummary}. {speechSummary}.
              </div>

              {planIsStale && (
                <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  The video model changed after this plan was made. Press <b>Start over</b> and plan again so the scene
                  lengths match {modelLabel}.
                </div>
              )}

              {plan.warnings.length > 0 && (
                <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  <div className="mb-1 font-semibold">Check these</div>
                  <ul className="list-disc space-y-1 pl-4">
                    {plan.warnings.map((w, i) => (
                      <li key={i}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              <section>
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wide text-white/60">Scenes (Seedance generates all of these)</h3>
                <div className="space-y-2">
                  {plan.scenes.map((s) => (
                    <div key={s.index} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2">
                      <div className="flex items-center justify-between gap-2 text-xs">
                        <span className="font-semibold">
                          {s.index}. {s.title}
                        </span>
                        <span className="text-white/50">
                          {clock(s.start)}–{clock(s.end)} · {s.duration_seconds}s
                          {s.duration_source === 'estimated' ? ' (from voiceover)' : ''}
                          {s.shots.length > 0 ? ` · ${s.shots.length} shots` : ''}
                        </span>
                      </div>
                      {s.voiceover && <p className="mt-1 text-xs italic text-white/70">“{s.voiceover}”</p>}
                    </div>
                  ))}
                </div>
              </section>

              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wide text-white/60">
                    You add in editing ({plan.edit_list.length})
                  </h3>
                  {plan.edit_list.length > 0 && (
                    <button
                      type="button"
                      onClick={() => void copy(editListText(plan), 'Editing list')}
                      className="text-xs text-[#b8f000] hover:underline"
                    >
                      Copy list
                    </button>
                  )}
                </div>
                {plan.edit_list.length === 0 ? (
                  <p className="text-xs text-white/50">Nothing to add in editing for this script.</p>
                ) : (
                  <div className="space-y-2">
                    {plan.edit_list.map((e, i) => (
                      <div key={i} className="rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2 text-xs">
                        <div className="flex items-center gap-2">
                          <span className="rounded bg-[#b8f000]/15 px-1.5 py-0.5 font-semibold text-[#b8f000]">{e.kind}</span>
                          {e.image_prompt ? (
                            <span className="rounded bg-white/10 px-1.5 py-0.5 text-[10px] font-semibold text-white/70">AI picture</span>
                          ) : null}
                          <span className="text-white/55">
                            {clock(e.start)}–{clock(e.end)} · scene {e.scene}
                          </span>
                        </div>
                        <p className="mt-1 text-white/80">{e.note}</p>
                      </div>
                    ))}
                  </div>
                )}
              </section>

              <section>
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-xs font-bold uppercase tracking-wide text-white/60">Prompt for Creative Studio (editable)</h3>
                  <button
                    type="button"
                    onClick={() => void copy(prompt, 'Prompt')}
                    className="text-xs text-[#b8f000] hover:underline"
                  >
                    Copy prompt
                  </button>
                </div>
                <label className="mb-2 flex items-start gap-2 text-xs text-white/70">
                  <input
                    type="checkbox"
                    checked={includeText}
                    onChange={(e) => toggleIncludeText(e.target.checked)}
                    className="mt-0.5 accent-[#b8f000]"
                  />
                  <span>
                    Let the app add the on-screen text automatically.{' '}
                    <span className="text-white/45">
                      Off by default: the video stays free of text and logos, and the exact lines are in the editing
                      list above for you to place. When on, the app writes the text into the video itself, so check the
                      spelling.
                    </span>
                  </span>
                </label>
                <textarea
                  value={prompt}
                  onChange={(e) => {
                    setPrompt(e.target.value)
                    setPromptEdited(true)
                  }}
                  rows={14}
                  className="cs-message-scroll w-full resize-y rounded-lg border border-white/10 bg-black/30 p-3 font-mono text-xs leading-relaxed text-white/90 focus:outline-none focus:ring-1 focus:ring-[#b8f000]/60"
                />
              </section>
            </>
          )}
        </div>

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-white/10 px-5 py-3">
          {!plan ? (
            <>
              <button
                type="button"
                onClick={onClose}
                disabled={loading}
                className="rounded-full border border-white/15 px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/10 disabled:opacity-40"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void runPlan()}
                disabled={!canPlan}
                className="rounded-full bg-[#b8f000] px-5 py-2 text-xs font-bold text-black hover:brightness-95 disabled:opacity-40"
              >
                {loading ? 'Reading your script…' : 'Plan script'}
              </button>
            </>
          ) : (
            <>
              <button
                type="button"
                onClick={reset}
                className="rounded-full border border-white/15 px-4 py-2 text-xs font-semibold text-white/80 hover:bg-white/10"
              >
                Start over
              </button>
              <button
                type="button"
                onClick={usePrompt}
                disabled={!prompt.trim() || planIsStale}
                title={planIsStale ? 'Plan again: the video model changed' : undefined}
                className="rounded-full bg-[#b8f000] px-5 py-2 text-xs font-bold text-black hover:brightness-95 disabled:opacity-40"
              >
                Use this prompt
              </button>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
