'use client'

import { useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import TextArea from '@/components/ui/TextArea'
import {
  hasTimedScriptLines,
  looksLikeCreativeBrief,
  spokenTextFromTimedScript,
} from '@/lib/avatarScript'
import { generationApi } from '@/lib/api'
import type { AvatarScriptResult } from '@/types'

export interface AvatarScriptContext {
  /** Step 5 creative brief — context for AI only, not copied into the prompt box. */
  briefNotes: string
  productName: string
  offer: string
  brandName: string
  targetAudience: string
  adCopyTone: string
  cta: string
  targetSeconds: number
  avatarLabel: string
  voiceLabel: string
  forbiddenWords?: string[]
}

interface AvatarScriptPanelProps {
  context: AvatarScriptContext
  approvedScript: string | null
  onApprovedScript: (script: string | null) => void
}

function scriptTextFromResult(result: AvatarScriptResult | null): string {
  if (!result) return ''
  const full = (result.full_script || '').trim()
  if (full) return full
  return result.lines.map((line) => `[${line.start} - ${line.end}] ${line.text}`).join('\n')
}

export default function AvatarScriptPanel({
  context,
  approvedScript,
  onApprovedScript,
}: AvatarScriptPanelProps) {
  const [scriptPrompt, setScriptPrompt] = useState('')
  const [preview, setPreview] = useState<AvatarScriptResult | null>(null)
  const [manualEdit, setManualEdit] = useState(false)
  const [editedScript, setEditedScript] = useState('')
  const [loading, setLoading] = useState(false)
  const hasBriefNotes = Boolean(context.briefNotes?.trim())

  const runGenerate = async (variation: 'default' | 'different_hook' = 'default') => {
    setLoading(true)
    setManualEdit(false)
    try {
      const result = await generationApi.generateAvatarScript({
        purpose: 'avatar_script',
        script_prompt: scriptPrompt.trim() || undefined,
        product_name: context.productName,
        offer: context.offer,
        brand_name: context.brandName,
        target_audience: context.targetAudience,
        ad_copy_tone: context.adCopyTone,
        cta: context.cta,
        notes: context.briefNotes || undefined,
        target_seconds: context.targetSeconds,
        avatar_label: context.avatarLabel,
        voice_label: context.voiceLabel,
        forbidden_words: context.forbiddenWords,
        variation,
      })
      const text = scriptTextFromResult(result)
      if (!text || looksLikeCreativeBrief(text)) {
        toast.error(
          'AI returned brief directions, not spoken lines — try again or edit manually'
        )
        return
      }
      setPreview(result)
      setEditedScript(text)
      toast.success('Spoken script generated — review and Approve')
    } catch {
      toast.error('Could not generate script — check OPENROUTER_API_KEY')
    } finally {
      setLoading(false)
    }
  }

  const generatedScript = scriptTextFromResult(preview).trim()

  const readableScript = (
    manualEdit ? editedScript : generatedScript || approvedScript || ''
  ).trim()

  const showPreview = Boolean(preview || approvedScript || manualEdit)

  const startManualEdit = () => {
    const text = generatedScript || approvedScript || editedScript || ''
    setEditedScript(text)
    setManualEdit(true)
  }

  const scriptForApprove = (manualEdit ? editedScript : generatedScript || approvedScript || '').trim()

  const canApprove = Boolean(
    scriptForApprove &&
      !looksLikeCreativeBrief(scriptForApprove) &&
      (preview || manualEdit || hasTimedScriptLines(scriptForApprove))
  )

  return (
    <div className="rounded-xl border-2 border-sky-200 bg-white p-4 shadow-sm relative">
      <span className="absolute top-3 right-3 flex h-6 w-6 items-center justify-center rounded-full bg-teal text-[11px] font-bold text-white">
        8
      </span>

      <div className="flex flex-wrap items-center justify-between gap-3 mb-2 pr-8">
        <h3 className="text-sm font-bold text-sky-700">
          Avatar Script — spoken lines for HeyGen
        </h3>
        <Button
          type="button"
          size="sm"
          variant="primary"
          isLoading={loading}
          onClick={() => runGenerate('default')}
        >
          Generate spoken script
        </Button>
      </div>

      <p className="text-[11px] text-mid mb-3 rounded-lg bg-amber-50 border border-amber-200/80 px-3 py-2 text-amber-950">
        <strong>Step 5 above</strong> only saves creative brief notes (ideas for writers). They are{' '}
        <strong>not</strong> what the avatar says. Use this section to generate real dialogue, then{' '}
        <strong>Approve &amp; send to HeyGen</strong>.
      </p>

      {hasBriefNotes && (
        <div className="mb-3 flex flex-wrap items-center gap-2">
          <p className="text-[11px] text-mid flex-1 min-w-[200px]">
            Brief notes from step 5 are used as context when you generate — they will not auto-fill
            this box.
          </p>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={loading}
            onClick={() => void runGenerate('default')}
          >
            Write script from brief notes
          </Button>
        </div>
      )}

      <TextArea
        label="Optional prompt (tone or angle — not the final script)"
        rows={3}
        value={scriptPrompt}
        onChange={(e) => setScriptPrompt(e.target.value)}
        placeholder="e.g. Friendly expert tone, mention free audit, end with Book a call."
      />

      {showPreview && (
        <div className="rounded-lg bg-slate-900 p-4 border border-slate-700 mt-4">
          <div className="flex flex-wrap items-center justify-between gap-2 mb-3 border-b border-slate-600 pb-2">
            <span className="text-[10px] font-bold uppercase tracking-wide text-teal">
              {manualEdit ? 'Editing spoken script' : 'Spoken script preview'} ·{' '}
              {preview?.model_label ?? 'Claude Sonnet 4.6'}
            </span>
            {preview && !manualEdit && (
              <span className="text-[10px] text-slate-400">
                {preview.word_count} words · ~ {Math.round(preview.estimated_seconds)} seconds @{' '}
                {preview.words_per_second} wps
              </span>
            )}
          </div>

          {manualEdit ? (
            <textarea
              value={editedScript}
              onChange={(e) => setEditedScript(e.target.value)}
              rows={10}
              spellCheck
              className="w-full min-h-[200px] px-3 py-2 rounded-lg border border-slate-600 bg-slate-800 text-white text-sm font-mono leading-relaxed resize-y focus:outline-none focus:ring-2 focus:ring-teal/50 placeholder:text-slate-500"
              placeholder="Paste or type what the avatar says, with [00:00 - 00:05] timestamps optional…"
            />
          ) : (
            <div className="text-sm leading-relaxed text-slate-100 font-mono whitespace-pre-wrap">
              {(preview?.lines ?? []).length > 1 ? (
                preview!.lines.map((line) => (
                  <p key={`${line.start}-${line.end}`} className="mb-2">
                    <span className="text-amber-300 font-semibold">
                      [{line.start} - {line.end}]
                    </span>{' '}
                    <span className="text-slate-100">{line.text}</span>
                  </p>
                ))
              ) : (
                <p className="text-slate-100">{readableScript}</p>
              )}
            </div>
          )}

          {!manualEdit && preview?.validations && preview.validations.length > 0 && (
            <ul className="flex flex-wrap gap-2 mt-4 pt-3 border-t border-slate-600">
              {preview.validations.map((v) => (
                <li
                  key={v.id}
                  className={`text-[10px] font-semibold px-2 py-1 rounded-full ${
                    v.status === 'ok'
                      ? 'bg-emerald-900/60 text-emerald-200'
                      : 'bg-amber-900/60 text-amber-100'
                  }`}
                >
                  {v.status === 'ok' ? '✓' : '⚠'} {v.label}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}

      {!showPreview && (
        <p className="text-[11px] text-mid mt-3">
          Click <strong>Generate spoken script</strong>, then <strong>Approve</strong>. HeyGen uses
          this exact dialogue — B-roll and text cuts are synced to what the avatar says in each beat.
        </p>
      )}

      <div className="flex flex-wrap gap-2 mt-4">
        {manualEdit ? (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={() => {
              setManualEdit(false)
              if (preview) {
                setPreview({ ...preview, full_script: editedScript })
              }
              toast.success('Edits saved to preview')
            }}
          >
            Done editing
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            disabled={!readableScript}
            onClick={startManualEdit}
          >
            Edit manually
          </Button>
        )}
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => runGenerate('default')}
        >
          Regenerate
        </Button>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={loading}
          onClick={() => runGenerate('different_hook')}
        >
          Try different hook
        </Button>
        <Button
          type="button"
          variant="primary"
          size="sm"
          className="ml-auto"
          disabled={!canApprove}
          onClick={() => {
            if (!canApprove) {
              toast.error(
                'Generate a spoken script first (brief notes alone are not sent to HeyGen)'
              )
              return
            }
            const toSave = hasTimedScriptLines(scriptForApprove)
              ? spokenTextFromTimedScript(scriptForApprove) || scriptForApprove
              : scriptForApprove
            onApprovedScript(toSave)
            toast.success('Script approved for HeyGen')
          }}
        >
          Approve &amp; send to HeyGen →
        </Button>
      </div>

      {approvedScript && (
        <p className="text-xs text-teal font-semibold mt-2">
          ✓ Approved script saved ({approvedScript.split(/\s+/).length} words) — this is what the
          avatar will speak
        </p>
      )}
    </div>
  )
}
