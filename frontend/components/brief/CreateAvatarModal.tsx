'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import { generationApi } from '@/lib/api'

interface CreateAvatarModalProps {
  open: boolean
  onClose(): void
  /** Called once the avatar is ready — passes the look_id and display name */
  onAvatarReady(lookId: string, name: string): void
}

type Stage = 'upload' | 'processing' | 'done' | 'error'

const POLL_INTERVAL_MS = 5_000
const MAX_POLLS = 60 // 5 min

export default function CreateAvatarModal({ open, onClose, onAvatarReady }: CreateAvatarModalProps) {
  const [name, setName] = useState('')
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState<string | null>(null)
  const [stage, setStage] = useState<Stage>('upload')
  const [errorMsg, setErrorMsg] = useState('')
  const [pollCount, setPollCount] = useState(0)
  const [avatarId, setAvatarId] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPolling = () => {
    if (pollRef.current) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  useEffect(() => {
    if (!open) {
      stopPolling()
    }
    return stopPolling
  }, [open])

  const handleFileChange = (f: File | null) => {
    setFile(f)
    if (f) {
      const url = URL.createObjectURL(f)
      setPreview(url)
    } else {
      setPreview(null)
    }
  }

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault()
    const f = e.dataTransfer.files[0]
    if (f && f.type.startsWith('image/')) handleFileChange(f)
  }, [])

  const startPolling = (id: string, displayName: string) => {
    let count = 0
    pollRef.current = setInterval(async () => {
      count++
      setPollCount(count)
      if (count > MAX_POLLS) {
        stopPolling()
        setStage('error')
        setErrorMsg('Avatar processing timed out. Please try again.')
        return
      }
      try {
        const result = await generationApi.getPhotoAvatarStatus(id)
        if (result.status === 'completed' && result.look_id) {
          stopPolling()
          setStage('done')
          onAvatarReady(result.look_id, displayName)
        } else if (result.status === 'failed') {
          stopPolling()
          setStage('error')
          setErrorMsg(result.error || 'HeyGen avatar creation failed.')
        }
      } catch {
        // network hiccup — keep polling
      }
    }, POLL_INTERVAL_MS)
  }

  const handleSubmit = async () => {
    if (!file || !name.trim()) return
    setSubmitting(true)
    setErrorMsg('')
    try {
      const result = await generationApi.createPhotoAvatar(file, name.trim())
      setAvatarId(result.photo_avatar_id)
      if (result.status === 'completed' && result.look_id) {
        setStage('done')
        onAvatarReady(result.look_id, name.trim())
      } else {
        setStage('processing')
        startPolling(result.photo_avatar_id, name.trim())
      }
    } catch (err: unknown) {
      const msg =
        (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail ||
        'Failed to create avatar. Check your photo and try again.'
      setErrorMsg(msg)
    } finally {
      setSubmitting(false)
    }
  }

  const handleReset = () => {
    stopPolling()
    setFile(null)
    setPreview(null)
    setName('')
    setStage('upload')
    setErrorMsg('')
    setPollCount(0)
    setAvatarId(null)
    setSubmitting(false)
  }

  const handleClose = () => {
    handleReset()
    onClose()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-2">
            <span className="text-xl">🤳</span>
            <h2 className="font-bold text-navy text-sm">Create your avatar</h2>
          </div>
          <button
            type="button"
            onClick={handleClose}
            className="text-muted hover:text-charcoal transition-colors text-lg leading-none"
          >
            ✕
          </button>
        </div>

        <div className="px-6 py-5 space-y-4">
          {/* Stage: upload */}
          {stage === 'upload' && (
            <>
              <p className="text-xs text-muted">
                Upload a clear, front-facing portrait photo. HeyGen will generate an AI avatar you
                can use in any video.
              </p>

              {/* Drop zone */}
              <div
                onDrop={handleDrop}
                onDragOver={(e) => e.preventDefault()}
                onClick={() => inputRef.current?.click()}
                className="border-2 border-dashed border-border rounded-xl h-40 flex flex-col items-center justify-center cursor-pointer hover:border-accent/50 hover:bg-accent/[0.03] transition-all overflow-hidden relative"
              >
                {preview ? (
                  <img
                    src={preview}
                    alt="Preview"
                    className="w-full h-full object-cover"
                  />
                ) : (
                  <>
                    <span className="text-3xl mb-1">📷</span>
                    <p className="text-xs text-muted font-medium">
                      Drop a photo here or <span className="text-accent">browse</span>
                    </p>
                    <p className="text-[10px] text-muted/60 mt-0.5">JPEG / PNG · max 10 MB</p>
                  </>
                )}
                <input
                  ref={inputRef}
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="hidden"
                  onChange={(e) => handleFileChange(e.target.files?.[0] ?? null)}
                />
              </div>

              {/* Name */}
              <div className="space-y-1">
                <label className="text-xs font-semibold text-muted uppercase tracking-wide">
                  Avatar name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  placeholder="e.g. Alex — casual"
                  maxLength={60}
                  className="w-full rounded-xl border border-border bg-surface px-3 py-2 text-sm text-charcoal placeholder-muted focus:outline-none focus:ring-2 focus:ring-accent/40"
                />
              </div>

              {errorMsg && (
                <p className="text-xs text-red-500 bg-red-50 rounded-xl px-3 py-2">{errorMsg}</p>
              )}

              <button
                type="button"
                disabled={!file || !name.trim() || submitting}
                onClick={handleSubmit}
                className="w-full rounded-xl bg-accent text-white font-semibold text-sm py-2.5 transition-opacity disabled:opacity-40"
              >
                {submitting ? 'Uploading…' : 'Generate avatar'}
              </button>
            </>
          )}

          {/* Stage: processing */}
          {stage === 'processing' && (
            <div className="flex flex-col items-center gap-4 py-6">
              <div className="relative w-16 h-16">
                <svg className="animate-spin w-16 h-16 text-accent/20" fill="none" viewBox="0 0 64 64">
                  <circle cx="32" cy="32" r="28" stroke="currentColor" strokeWidth="6" />
                </svg>
                <svg className="animate-spin w-16 h-16 text-accent absolute inset-0" fill="none" viewBox="0 0 64 64">
                  <path
                    d="M32 4a28 28 0 0128 28"
                    stroke="currentColor"
                    strokeWidth="6"
                    strokeLinecap="round"
                  />
                </svg>
                <span className="absolute inset-0 flex items-center justify-center text-lg">🤖</span>
              </div>
              <div className="text-center">
                <p className="font-semibold text-navy text-sm">HeyGen is building your avatar…</p>
                <p className="text-xs text-muted mt-1">
                  This usually takes 30–90 seconds. We&apos;ll auto-select it when ready.
                </p>
                {pollCount > 0 && (
                  <p className="text-[10px] text-muted/60 mt-2">
                    Checking… ({pollCount * 5}s elapsed)
                  </p>
                )}
              </div>
              <button
                type="button"
                onClick={handleClose}
                className="text-xs text-muted underline underline-offset-2"
              >
                Close (will continue in background)
              </button>
            </div>
          )}

          {/* Stage: done */}
          {stage === 'done' && (
            <div className="flex flex-col items-center gap-4 py-6">
              <span className="text-5xl">🎉</span>
              <div className="text-center">
                <p className="font-semibold text-navy text-sm">Avatar ready!</p>
                <p className="text-xs text-muted mt-1">
                  <strong>{name}</strong> has been added to your avatar list and selected.
                </p>
              </div>
              <button
                type="button"
                onClick={handleClose}
                className="rounded-xl bg-accent text-white font-semibold text-sm px-6 py-2"
              >
                Done
              </button>
            </div>
          )}

          {/* Stage: error */}
          {stage === 'error' && (
            <div className="flex flex-col items-center gap-4 py-4">
              <span className="text-4xl">⚠️</span>
              <div className="text-center">
                <p className="font-semibold text-red-600 text-sm">Something went wrong</p>
                <p className="text-xs text-muted mt-1">{errorMsg}</p>
              </div>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={handleReset}
                  className="rounded-xl border border-border px-4 py-2 text-xs font-semibold text-charcoal hover:bg-surface transition-colors"
                >
                  Try again
                </button>
                <button
                  type="button"
                  onClick={handleClose}
                  className="rounded-xl bg-accent text-white text-xs font-semibold px-4 py-2"
                >
                  Close
                </button>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
