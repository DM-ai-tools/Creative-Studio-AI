'use client'

import { useEffect, useState } from 'react'
import Button from '@/components/ui/Button'
import { generationApi } from '@/lib/api'
import type { PerformanceStatsContext } from '@/types'

export type MasterBeat = {
  start: string
  end: string
  spoken: string
  visual: string
  stat_image?: string | null
  stat_headline?: string | null
  stat_warning?: string | null
}

export default function MasterScriptPreview({
  avatarScript,
  sceneBrollDirections,
  targetSeconds,
  performanceStatsPerImage,
  scriptApproved,
  brollReady,
  onWarningsChange,
  onScriptChange,
}: {
  avatarScript: string | null
  sceneBrollDirections: string
  targetSeconds: number
  performanceStatsPerImage: PerformanceStatsContext[]
  scriptApproved: boolean
  brollReady: boolean
  onWarningsChange?: (warnings: string[]) => void
  onScriptChange?: (newScript: string) => void
}) {
  const [beats, setBeats] = useState<MasterBeat[]>([])
  const [warnings, setWarnings] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [editing, setEditing] = useState(false)
  const [draft, setDraft] = useState<string[]>([])

  useEffect(() => {
    const script = (avatarScript || '').trim()
    if (!script) {
      setBeats([])
      setWarnings([])
      return
    }
    let cancelled = false
    setLoading(true)
    generationApi
      .masterScriptPreview({
        avatar_script: script,
        scene_broll_directions: sceneBrollDirections || '',
        target_seconds: targetSeconds,
        performance_stats_per_image: performanceStatsPerImage,
      })
      .then((res) => {
        if (cancelled) return
        setBeats(res.beats)
        setWarnings(res.warnings)
        onWarningsChange?.(res.warnings)
      })
      .catch(() => {
        if (!cancelled) {
          const err = ['Could not load master script preview']
          setWarnings(err)
          onWarningsChange?.(err)
        }
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [
    avatarScript,
    sceneBrollDirections,
    targetSeconds,
    performanceStatsPerImage,
  ])

  useEffect(() => {
    if (!editing) setDraft(beats.map((b) => b.spoken))
  }, [beats, editing])

  const saveEdits = () => {
    const newScript = beats
      .map((b, i) => `[${b.start} - ${b.end}] ${(draft[i] ?? b.spoken).trim()}`)
      .join('\n')
    onScriptChange?.(newScript)
    setEditing(false)
  }

  const cancelEdits = () => {
    setDraft(beats.map((b) => b.spoken))
    setEditing(false)
  }

  if (!(avatarScript || '').trim()) {
    return null
  }

  return (
    <div className="rounded-xl border-2 border-indigo-300 bg-indigo-50/50 p-4 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-bold text-indigo-900 uppercase tracking-wide">
            Master script — full video timeline
          </p>
          <p className="text-[11px] text-indigo-800 mt-1">
            This is what Generate uses: voice + visuals + stat images per second. OCR numbers from
            your stats images go into the <strong>Voice</strong> column — the avatar speaks them and
            captions show digits (e.g. $105 million). Stat-image cards are optional post overlays.{' '}
            <strong>[INSERT STAT IMAGE]</strong> in B-roll is a timing cue only.
          </p>
        </div>
        {onScriptChange && beats.length > 0 && (
          <div className="flex shrink-0 gap-2">
            {editing ? (
              <>
                <Button size="sm" variant="ghost" onClick={cancelEdits}>
                  Cancel
                </Button>
                <Button size="sm" onClick={saveEdits}>
                  Save changes
                </Button>
              </>
            ) : (
              <Button size="sm" variant="secondary" onClick={() => setEditing(true)}>
                ✎ Edit master script
              </Button>
            )}
          </div>
        )}
      </div>
      {editing && (
        <p className="text-[11px] text-indigo-700">
          Edit the exact words the avatar speaks per beat below, then <strong>Save changes</strong>.
          Timings and stat-image cues stay locked to keep voice and visuals in sync.
        </p>
      )}

      {loading && (
        <p className="text-xs text-indigo-700">Building timeline…</p>
      )}

      {warnings.length > 0 && (
        <ul className="text-[11px] text-amber-900 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 space-y-1 list-disc list-inside">
          {warnings.map((w) => (
            <li key={w}>{w}</li>
          ))}
        </ul>
      )}

      {beats.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-indigo-200 bg-white">
          <table className="w-full text-left text-[11px]">
            <thead>
              <tr className="bg-indigo-100/80 text-indigo-900 uppercase tracking-wide">
                <th className="px-2 py-1.5 font-bold whitespace-nowrap">Time</th>
                <th className="px-2 py-1.5 font-bold">Voice (what avatar says)</th>
                <th className="px-2 py-1.5 font-bold">Visual (B-roll / camera)</th>
                <th className="px-2 py-1.5 font-bold whitespace-nowrap">Stats image</th>
              </tr>
            </thead>
            <tbody>
              {beats.map((beat, i) => (
                <tr
                  key={`${beat.start}-${beat.end}`}
                  className={`border-t border-indigo-100 align-top ${
                    beat.stat_warning ? 'bg-amber-50/60' : ''
                  }`}
                >
                  <td className="px-2 py-2 font-mono text-indigo-800 whitespace-nowrap">
                    {beat.start}–{beat.end}
                  </td>
                  <td className="px-2 py-2 text-charcoal">
                    {editing ? (
                      <textarea
                        value={draft[i] ?? beat.spoken}
                        onChange={(e) => {
                          const next = [...draft]
                          next[i] = e.target.value
                          setDraft(next)
                        }}
                        rows={Math.max(2, Math.ceil((draft[i] ?? beat.spoken).length / 40))}
                        className="w-full min-w-[220px] rounded border border-indigo-300 bg-white px-2 py-1 text-[11px] text-charcoal focus:border-indigo-500 focus:outline-none focus:ring-1 focus:ring-indigo-400"
                      />
                    ) : (
                      beat.spoken
                    )}
                  </td>
                  <td className="px-2 py-2 text-muted">{beat.visual}</td>
                  <td className="px-2 py-2 whitespace-nowrap">
                    {beat.stat_image ? (
                      <span className="inline-block rounded bg-emerald-100 text-emerald-800 px-1.5 py-0.5 font-semibold">
                        {beat.stat_headline || beat.stat_image}
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                    {beat.stat_warning && (
                      <p className="text-amber-800 mt-1">{beat.stat_warning}</p>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {scriptApproved && brollReady && beats.length > 0 && warnings.length === 0 && (
        <p className="text-xs font-semibold text-emerald-800">
          ✓ Timeline aligned — safe to Generate
        </p>
      )}
    </div>
  )
}
