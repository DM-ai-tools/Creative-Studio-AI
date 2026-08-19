'use client'

import React, { useState } from 'react'

// ─── Types ─────────────────────────────────────────────────────────────────────

type MediaMode = 'image' | 'video'

type GenreId =
  | 'general' | 'cinematic' | 'action' | 'horror' | 'romance'
  | 'sci_fi' | 'thriller' | 'comedy' | 'documentary'

type StyleId =
  | 'auto' | 'photorealistic' | 'cinematic' | 'anime'
  | 'oil_painting' | 'watercolor' | 'comic' | 'digital_art' | 'vintage'

type CameraId =
  | 'auto' | 'arc_left' | 'arc_right' | 'dolly_in' | 'dolly_out'
  | 'pan_left' | 'pan_right' | 'tilt_up' | 'tilt_down' | 'static'

type DurationId = '5' | '10' | '15' | '30'
type ResolutionId = '720p' | '1080p' | '4k'
type AspectId = '1/4' | '9/16' | '1/1' | '4/3' | '16/9'

interface CreativeStudioFields {
  mediaMode: MediaMode
  prompt: string
  genre: GenreId
  style: StyleId
  camera: CameraId
  duration: DurationId
  resolution: ResolutionId
  aspect: AspectId
  negativePrompt: string
  characters: string
  location: string
  soundOn: boolean
}

// ─── Static data ───────────────────────────────────────────────────────────────

const GENRES: { id: GenreId; label: string; emoji: string }[] = [
  { id: 'general',     label: 'General',      emoji: '🎬' },
  { id: 'cinematic',   label: 'Cinematic',    emoji: '🎭' },
  { id: 'action',      label: 'Action',       emoji: '💥' },
  { id: 'horror',      label: 'Horror',       emoji: '👻' },
  { id: 'romance',     label: 'Romance',      emoji: '❤️' },
  { id: 'sci_fi',      label: 'Sci-Fi',       emoji: '🚀' },
  { id: 'thriller',    label: 'Thriller',     emoji: '🎯' },
  { id: 'comedy',      label: 'Comedy',       emoji: '😂' },
  { id: 'documentary', label: 'Documentary',  emoji: '📽' },
]

const STYLES: { id: StyleId; label: string; icon: string }[] = [
  { id: 'auto',           label: 'Auto',          icon: '✦' },
  { id: 'photorealistic', label: 'Photoreal',      icon: '📷' },
  { id: 'cinematic',      label: 'Cinematic',      icon: '🎬' },
  { id: 'anime',          label: 'Anime',          icon: '🌸' },
  { id: 'oil_painting',   label: 'Oil Paint',      icon: '🖌' },
  { id: 'watercolor',     label: 'Watercolor',     icon: '💧' },
  { id: 'comic',          label: 'Comic',          icon: '💥' },
  { id: 'digital_art',    label: 'Digital Art',    icon: '⬡' },
  { id: 'vintage',        label: 'Vintage',        icon: '📷' },
]

const CAMERAS: { id: CameraId; label: string; icon: string }[] = [
  { id: 'auto',       label: 'Auto',       icon: '🎥' },
  { id: 'arc_left',   label: 'Arc L',      icon: '↺' },
  { id: 'arc_right',  label: 'Arc R',      icon: '↻' },
  { id: 'dolly_in',   label: 'Dolly In',   icon: '▶' },
  { id: 'dolly_out',  label: 'Dolly Out',  icon: '◀' },
  { id: 'pan_left',   label: 'Pan L',      icon: '←' },
  { id: 'pan_right',  label: 'Pan R',      icon: '→' },
  { id: 'tilt_up',    label: 'Tilt Up',    icon: '↑' },
  { id: 'tilt_down',  label: 'Tilt Dn',   icon: '↓' },
  { id: 'static',     label: 'Static',     icon: '⬜' },
]

const DURATIONS: { id: DurationId; label: string }[] = [
  { id: '5',  label: '5s'  },
  { id: '10', label: '10s' },
  { id: '15', label: '15s' },
  { id: '30', label: '30s' },
]

const RESOLUTIONS: { id: ResolutionId; label: string }[] = [
  { id: '720p',  label: '720p'  },
  { id: '1080p', label: '1080p' },
  { id: '4k',    label: '4K'    },
]

const ASPECTS: { id: AspectId; label: string; desc: string }[] = [
  { id: '9/16', label: '9:16',  desc: 'Stories / Reels' },
  { id: '1/1',  label: '1:1',   desc: 'Square' },
  { id: '4/3',  label: '4:3',   desc: 'Standard' },
  { id: '16/9', label: '16:9',  desc: 'Widescreen' },
]

// ─── Defaults ─────────────────────────────────────────────────────────────────

const defaults: CreativeStudioFields = {
  mediaMode:      'video',
  prompt:         '',
  genre:          'general',
  style:          'auto',
  camera:         'auto',
  duration:       '15',
  resolution:     '1080p',
  aspect:         '9/16',
  negativePrompt: '',
  characters:     '',
  location:       '',
  soundOn:        true,
}

// ─── Component ────────────────────────────────────────────────────────────────

interface Props {
  briefTitle?: string
  brandName?: string
  productName?: string
  initialPrompt?: string
}

export default function CreativeStudioTab({ initialPrompt }: Props) {
  const [fields, setFields] = useState<CreativeStudioFields>({
    ...defaults,
    prompt: initialPrompt || '',
  })
  const [advancedOpen, setAdvancedOpen] = useState(false)
  const [copied, setCopied] = useState(false)

  const set = <K extends keyof CreativeStudioFields>(k: K, v: CreativeStudioFields[K]) =>
    setFields((p) => ({ ...p, [k]: v }))

  const builtPrompt = [
    fields.prompt.trim(),
    fields.genre !== 'general' ? `Genre: ${GENRES.find((g) => g.id === fields.genre)?.label}` : '',
    fields.style !== 'auto'    ? `Style: ${STYLES.find((s) => s.id === fields.style)?.label}` : '',
    fields.camera !== 'auto'   ? `Camera: ${CAMERAS.find((c) => c.id === fields.camera)?.label}` : '',
    fields.characters.trim()   ? `Characters: ${fields.characters}` : '',
    fields.location.trim()     ? `Location: ${fields.location}` : '',
    fields.negativePrompt.trim()? `Negative: ${fields.negativePrompt}` : '',
  ].filter(Boolean).join(' | ')

  const handleCopy = async () => {
    try { await navigator.clipboard.writeText(builtPrompt); setCopied(true); setTimeout(() => setCopied(false), 2000) }
    catch { /* noop */ }
  }

  return (
    <div className="w-full max-w-[1600px] mx-auto p-6 md:p-8">
      <div className="rounded-2xl border border-border bg-white overflow-hidden shadow-soft">

        {/* ── Header ─────────────────────────────────────────────────────── */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-surface">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-navy">Creative Studio</span>
            <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-accent/15 text-accent border border-accent/20 leading-none">
              NEW
            </span>
          </div>
          <p className="text-xs text-mid">
            Cinematic scene builder — compose your prompt, pick genre, style &amp; camera, then generate.
          </p>
        </div>

        <div className="flex divide-x divide-border">

          {/* ── Left: Genre list ────────────────────────────────────────── */}
          <div className="w-[180px] shrink-0 p-4 bg-surface/50">
            <p className="text-[10px] font-bold uppercase tracking-widest text-mid mb-3">Genre</p>
            <div className="flex flex-col gap-0.5">
              {GENRES.map((g) => (
                <button
                  key={g.id}
                  type="button"
                  onClick={() => set('genre', g.id)}
                  className={`w-full text-left flex items-center gap-2 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                    fields.genre === g.id
                      ? 'bg-accent/10 text-charcoal border border-accent/30'
                      : 'text-mid hover:text-charcoal hover:bg-surface-hover border border-transparent'
                  }`}
                >
                  <span>{g.emoji}</span>
                  {g.label}
                </button>
              ))}
            </div>
          </div>

          {/* ── Centre: Prompt + controls ───────────────────────────────── */}
          <div className="flex-1 flex flex-col">

            {/* Image / Video toggle */}
            <div className="flex gap-1 px-5 pt-4">
              {(['image', 'video'] as const).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => set('mediaMode', m)}
                  className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-semibold transition-all border ${
                    fields.mediaMode === m
                      ? 'bg-white border-border text-charcoal shadow-xs'
                      : 'border-transparent text-mid hover:text-charcoal hover:bg-surface-hover'
                  }`}
                >
                  {m === 'image' ? (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <rect x="3" y="3" width="18" height="18" rx="2" strokeWidth="1.8" />
                      <circle cx="8.5" cy="8.5" r="1.5" strokeWidth="1.8" />
                      <polyline points="21 15 16 10 5 21" strokeWidth="1.8" />
                    </svg>
                  ) : (
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <polygon points="23 7 16 12 23 17 23 7" strokeWidth="1.8" />
                      <rect x="1" y="5" width="15" height="14" rx="2" strokeWidth="1.8" />
                    </svg>
                  )}
                  {m.charAt(0).toUpperCase() + m.slice(1)}
                </button>
              ))}
            </div>

            {/* Prompt */}
            <div className="relative px-5 mt-3">
              <textarea
                rows={5}
                placeholder={`Describe your scene — use @ to add characters & locations`}
                value={fields.prompt}
                onChange={(e) => set('prompt', e.target.value)}
                className="w-full bg-surface border border-border rounded-xl px-4 py-3 text-sm text-charcoal
                           placeholder:text-lt resize-none outline-none
                           focus:border-accent/50 focus:ring-2 focus:ring-accent/15 transition-all"
              />
              <span className="absolute bottom-3 right-8 text-[10px] text-lt">
                {fields.prompt.length}/2000
              </span>
            </div>

            {/* Quick tags */}
            <div className="flex items-center gap-3 px-5 py-2 text-xs text-mid">
              <span>Add:</span>
              <button
                type="button"
                onClick={() => set('prompt', fields.prompt + ' @character')}
                className="flex items-center gap-1 hover:text-charcoal transition-colors"
              >@ Characters</button>
              <button
                type="button"
                onClick={() => set('prompt', fields.prompt + ' @location')}
                className="flex items-center gap-1 hover:text-charcoal transition-colors"
              >📍 Location</button>
              {builtPrompt && (
                <button
                  type="button"
                  onClick={handleCopy}
                  className="ml-auto hover:text-charcoal transition-colors font-medium"
                >
                  {copied ? '✓ Copied' : 'Copy prompt'}
                </button>
              )}
            </div>

            {/* Control bar */}
            <div className="flex flex-wrap items-center gap-2 px-5 py-3 border-t border-border bg-surface/50">

              {/* Style select */}
              <label className="flex items-center gap-1.5 text-xs">
                <span className="font-semibold text-mid uppercase tracking-widest text-[10px]">Style</span>
                <select
                  value={fields.style}
                  onChange={(e) => set('style', e.target.value as StyleId)}
                  className="border border-border rounded-lg px-2 py-1 text-xs text-charcoal bg-white outline-none
                             focus:border-accent/50 cursor-pointer"
                >
                  {STYLES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </select>
              </label>

              {fields.mediaMode === 'video' && (
                <>
                  <label className="flex items-center gap-1.5 text-xs">
                    <span className="font-semibold text-mid uppercase tracking-widest text-[10px]">Camera</span>
                    <select
                      value={fields.camera}
                      onChange={(e) => set('camera', e.target.value as CameraId)}
                      className="border border-border rounded-lg px-2 py-1 text-xs text-charcoal bg-white outline-none
                                 focus:border-accent/50 cursor-pointer"
                    >
                      {CAMERAS.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
                    </select>
                  </label>

                  <label className="flex items-center gap-1.5 text-xs">
                    <span className="font-semibold text-mid uppercase tracking-widest text-[10px]">Duration</span>
                    <div className="flex gap-1">
                      {DURATIONS.map((d) => (
                        <button
                          key={d.id}
                          type="button"
                          onClick={() => set('duration', d.id)}
                          className={`px-2.5 py-1 rounded-full text-xs font-semibold border transition-all ${
                            fields.duration === d.id
                              ? 'border-accent bg-accent/10 text-charcoal'
                              : 'border-border text-mid hover:border-accent/40 hover:text-charcoal'
                          }`}
                        >
                          {d.label}
                        </button>
                      ))}
                    </div>
                  </label>
                </>
              )}

              <label className="flex items-center gap-1.5 text-xs">
                <span className="font-semibold text-mid uppercase tracking-widest text-[10px]">Quality</span>
                <select
                  value={fields.resolution}
                  onChange={(e) => set('resolution', e.target.value as ResolutionId)}
                  className="border border-border rounded-lg px-2 py-1 text-xs text-charcoal bg-white outline-none
                             focus:border-accent/50 cursor-pointer"
                >
                  {RESOLUTIONS.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
                </select>
              </label>

              {/* Aspect ratio */}
              <div className="flex items-center gap-1.5">
                <span className="font-semibold text-mid uppercase tracking-widest text-[10px]">Ratio</span>
                <div className="flex gap-1">
                  {ASPECTS.map((a) => (
                    <button
                      key={a.id}
                      type="button"
                      title={a.desc}
                      onClick={() => set('aspect', a.id)}
                      className={`px-2 py-1 rounded-lg text-[11px] font-mono border transition-all ${
                        fields.aspect === a.id
                          ? 'border-accent bg-accent/10 text-charcoal'
                          : 'border-border text-mid hover:border-accent/40 hover:text-charcoal'
                      }`}
                    >
                      {a.label}
                    </button>
                  ))}
                </div>
              </div>

              {fields.mediaMode === 'video' && (
                <button
                  type="button"
                  onClick={() => set('soundOn', !fields.soundOn)}
                  className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-full border transition-all ${
                    fields.soundOn
                      ? 'border-accent bg-accent/10 text-charcoal'
                      : 'border-border text-mid hover:border-border-strong'
                  }`}
                >
                  {fields.soundOn ? '🔊' : '🔇'}
                  <span>{fields.soundOn ? 'Sound on' : 'Sound off'}</span>
                </button>
              )}
            </div>

            {/* Advanced */}
            <div className="px-5 pb-4">
              <button
                type="button"
                onClick={() => setAdvancedOpen((p) => !p)}
                className="flex items-center gap-1.5 text-xs text-mid hover:text-charcoal transition-colors mt-2"
              >
                <svg
                  className={`w-3 h-3 transition-transform ${advancedOpen ? 'rotate-90' : ''}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                </svg>
                Advanced options
              </button>

              {advancedOpen && (
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-mid mb-1.5">Characters</p>
                    <input
                      type="text"
                      placeholder="e.g. woman, 30s, professional"
                      value={fields.characters}
                      onChange={(e) => set('characters', e.target.value)}
                      className="w-full border border-border rounded-lg px-3 py-2 text-xs text-charcoal
                                 bg-white outline-none focus:border-accent/50 focus:ring-2 focus:ring-accent/15"
                    />
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-mid mb-1.5">Location</p>
                    <input
                      type="text"
                      placeholder="e.g. city rooftop at sunset"
                      value={fields.location}
                      onChange={(e) => set('location', e.target.value)}
                      className="w-full border border-border rounded-lg px-3 py-2 text-xs text-charcoal
                                 bg-white outline-none focus:border-accent/50 focus:ring-2 focus:ring-accent/15"
                    />
                  </div>
                  <div className="col-span-2">
                    <p className="text-[10px] font-bold uppercase tracking-widest text-mid mb-1.5">
                      Negative prompt (what to avoid)
                    </p>
                    <textarea
                      rows={2}
                      placeholder="e.g. blurry, distorted, watermark, text overlay"
                      value={fields.negativePrompt}
                      onChange={(e) => set('negativePrompt', e.target.value)}
                      className="w-full border border-border rounded-lg px-3 py-2 text-xs text-charcoal
                                 bg-white outline-none resize-none focus:border-accent/50 focus:ring-2 focus:ring-accent/15"
                    />
                  </div>
                </div>
              )}

              {/* Prompt preview */}
              {builtPrompt && (
                <div className="mt-3 p-3 rounded-xl bg-surface border border-border">
                  <p className="text-[10px] font-bold uppercase tracking-widest text-mid mb-1.5">Full prompt</p>
                  <p className="text-xs text-charcoal leading-relaxed break-words">{builtPrompt}</p>
                </div>
              )}
            </div>
          </div>

          {/* ── Right: Style + Camera grid ─────────────────────────────── */}
          <div className="w-[200px] shrink-0 p-4 bg-surface/50">
            <p className="text-[10px] font-bold uppercase tracking-widest text-mid mb-3">Style</p>
            <div className="grid grid-cols-2 gap-1.5">
              {STYLES.map((s) => (
                <button
                  key={s.id}
                  type="button"
                  onClick={() => set('style', s.id)}
                  className={`aspect-square rounded-xl flex flex-col items-center justify-center gap-1
                              text-[9px] font-bold uppercase tracking-wide transition-all border ${
                    fields.style === s.id
                      ? 'border-accent bg-accent/10 text-charcoal shadow-glow-sm'
                      : 'border-border bg-white text-mid hover:border-accent/40 hover:text-charcoal hover:bg-surface-hover'
                  }`}
                >
                  <span className="text-xl">{s.icon}</span>
                  <span className="leading-none text-center px-0.5">{s.label}</span>
                </button>
              ))}
            </div>

            {fields.mediaMode === 'video' && (
              <div className="mt-4">
                <p className="text-[10px] font-bold uppercase tracking-widest text-mid mb-2">Camera</p>
                <div className="grid grid-cols-3 gap-1">
                  {CAMERAS.map((c) => (
                    <button
                      key={c.id}
                      type="button"
                      title={c.label}
                      onClick={() => set('camera', c.id)}
                      className={`aspect-square rounded-lg flex flex-col items-center justify-center gap-0.5
                                  text-xs transition-all border ${
                        fields.camera === c.id
                          ? 'bg-accent/10 text-charcoal border-accent/40'
                          : 'bg-white text-mid border-border hover:border-accent/30 hover:text-charcoal hover:bg-surface-hover'
                      }`}
                    >
                      <span>{c.icon}</span>
                      <span className="text-[8px] font-bold leading-none">{c.label}</span>
                    </button>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* ── Footer / Generate bar ──────────────────────────────────────── */}
        <div className="border-t border-border bg-surface px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-2 text-xs text-mid flex-wrap">
            <span className="font-medium text-charcoal">
              {fields.mediaMode === 'video' ? 'Video' : 'Image'}
            </span>
            <span>·</span>
            <span>{fields.resolution}</span>
            <span>·</span>
            <span>{fields.aspect.replace('/', ':')}</span>
            {fields.mediaMode === 'video' && (
              <>
                <span>·</span>
                <span>{fields.duration}s</span>
              </>
            )}
            {fields.genre !== 'general' && (
              <>
                <span>·</span>
                <span>{GENRES.find((g) => g.id === fields.genre)?.label}</span>
              </>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setFields({ ...defaults, prompt: initialPrompt || '' })}
              className="text-xs text-mid hover:text-charcoal px-3 py-1.5 rounded-lg border border-border
                         hover:border-border-strong transition-all"
            >
              Reset
            </button>
            <button
              type="button"
              disabled={!fields.prompt.trim()}
              className="flex items-center gap-2 bg-accent text-white font-bold text-sm
                         px-6 py-2.5 rounded-xl transition-all shadow-glow-sm
                         hover:bg-accent-dark
                         disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5}
                      d="M13 10V3L4 14h7v7l9-11h-7z" />
              </svg>
              Generate
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
