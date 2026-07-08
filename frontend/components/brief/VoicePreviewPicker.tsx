'use client'

import { useEffect, useRef, useState } from 'react'
import { generationApi } from '@/lib/api'
import type { CatalogOption } from '@/types'

interface VoicePreviewPickerProps {
  voices: CatalogOption[]
  selectedId: string
  onChange(id: string): void
  /** Optional sample text for TTS preview */
  sampleText?: string
}

type PlayState = 'idle' | 'loading' | 'playing'

export default function VoicePreviewPicker({
  voices,
  selectedId,
  onChange,
  sampleText,
}: VoicePreviewPickerProps) {
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [playState, setPlayState] = useState<PlayState>('idle')
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Stop audio when component unmounts
  useEffect(() => {
    return () => {
      audioRef.current?.pause()
    }
  }, [])

  const stopAudio = () => {
    audioRef.current?.pause()
    audioRef.current = null
    setPlayingId(null)
    setPlayState('idle')
  }

  const handlePreview = async (voiceId: string) => {
    if (playingId === voiceId && playState === 'playing') {
      stopAudio()
      return
    }
    stopAudio()
    setPlayingId(voiceId)
    setPlayState('loading')
    try {
      const url = await generationApi.previewVoice(voiceId, sampleText)
      const audio = new Audio(url)
      audioRef.current = audio
      audio.onended = stopAudio
      audio.onerror = stopAudio
      await audio.play()
      setPlayState('playing')
    } catch {
      setPlayingId(null)
      setPlayState('idle')
    }
  }

  const female = voices.filter((v) => v.gender?.toLowerCase() === 'female')
  const male = voices.filter((v) => v.gender?.toLowerCase() === 'male')
  const other = voices.filter(
    (v) => !v.gender || (v.gender.toLowerCase() !== 'female' && v.gender.toLowerCase() !== 'male'),
  )

  const groups: { label: string; items: CatalogOption[] }[] = [
    ...(female.length ? [{ label: 'Female', items: female }] : []),
    ...(male.length ? [{ label: 'Male', items: male }] : []),
    ...(other.length ? [{ label: 'Other', items: other }] : []),
  ]

  if (!groups.length) {
    return (
      <div className="flex flex-col gap-1">
        <span className="text-xs font-semibold text-muted uppercase tracking-wide">Voice</span>
        <p className="text-xs text-muted italic">No voices available</p>
      </div>
    )
  }

  return (
    <div className="flex flex-col gap-2 md:col-span-2">
      <span className="text-xs font-semibold text-muted uppercase tracking-wide">
        Voice <span className="normal-case font-normal opacity-60">— click ▶ to preview</span>
      </span>

      {groups.map(({ label, items }) => (
        <div key={label}>
          <p className="text-[10px] font-bold text-muted/60 uppercase tracking-wider mb-1 ml-1">
            {label}
          </p>
          <div className="flex flex-col gap-1">
            {items.map((v) => {
              const isSelected = v.id === selectedId
              const isLoading = playingId === v.id && playState === 'loading'
              const isPlaying = playingId === v.id && playState === 'playing'

              return (
                <div
                  key={v.id}
                  className={[
                    'flex items-center gap-2 rounded-xl px-3 py-2 cursor-pointer transition-all border text-xs',
                    isSelected
                      ? 'bg-accent/10 border-accent/40 text-navy font-semibold'
                      : 'bg-surface border-border hover:border-accent/30 hover:bg-accent/5 text-charcoal font-normal',
                  ].join(' ')}
                  onClick={() => onChange(v.id)}
                >
                  {/* Radio dot */}
                  <span
                    className={[
                      'flex-shrink-0 w-3.5 h-3.5 rounded-full border-2 transition-colors',
                      isSelected ? 'border-accent bg-accent' : 'border-border',
                    ].join(' ')}
                  />

                  {/* Label */}
                  <span className="flex-1 truncate">{v.label}</span>

                  {/* Play / stop button */}
                  <button
                    type="button"
                    onClick={(e) => {
                      e.stopPropagation()
                      handlePreview(v.id)
                    }}
                    disabled={isLoading}
                    title={isPlaying ? 'Stop preview' : 'Preview voice'}
                    className={[
                      'flex-shrink-0 flex items-center justify-center w-7 h-7 rounded-lg transition-colors',
                      isPlaying
                        ? 'bg-red-500/10 text-red-500 hover:bg-red-500/20'
                        : 'bg-accent/10 text-accent hover:bg-accent/20',
                      isLoading ? 'opacity-50 cursor-wait' : '',
                    ].join(' ')}
                  >
                    {isLoading ? (
                      <svg
                        className="animate-spin w-3.5 h-3.5"
                        fill="none"
                        viewBox="0 0 24 24"
                      >
                        <circle
                          className="opacity-25"
                          cx="12"
                          cy="12"
                          r="10"
                          stroke="currentColor"
                          strokeWidth="4"
                        />
                        <path
                          className="opacity-75"
                          fill="currentColor"
                          d="M4 12a8 8 0 018-8v8z"
                        />
                      </svg>
                    ) : isPlaying ? (
                      // Stop icon
                      <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 16 16">
                        <rect x="3" y="3" width="10" height="10" rx="1" />
                      </svg>
                    ) : (
                      // Play icon
                      <svg className="w-3.5 h-3.5" fill="currentColor" viewBox="0 0 16 16">
                        <path d="M4 2.5l9 5.5-9 5.5V2.5z" />
                      </svg>
                    )}
                  </button>
                </div>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
