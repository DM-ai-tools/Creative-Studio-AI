'use client'

import React, { useEffect, useRef, useState } from 'react'

/**
 * "Generating" animation in the app's own look: a light surface, a grid of dots and a soft green glow
 * drifting across it, with a percentage pill.
 *
 * The image service reports no real progress, so the percentage is time elapsed over how long this account's
 * images really take (measured and remembered, see lib/generationTiming). It reaches about 90% at the
 * expected time, creeps up if the image is slower, and never shows 100% until the picture is ready.
 */
function useEstimatedPercent(expectedSeconds: number, startedAt?: number) {
  const mounted = useRef(Date.now())
  const [percent, setPercent] = useState(2)
  useEffect(() => {
    const start = startedAt ?? mounted.current
    const tau = Math.max(6, expectedSeconds / 2.3) // 1 - e^-2.3 ≈ 90% at the expected time
    const tick = () => {
      const t = Math.max(0, (Date.now() - start) / 1000)
      setPercent(Math.min(98, Math.max(2, Math.round(2 + 96 * (1 - Math.exp(-t / tau))))))
    }
    tick()
    const id = window.setInterval(tick, 300)
    return () => window.clearInterval(id)
  }, [expectedSeconds, startedAt])
  return percent
}

const SPACING = 13 // px between dots
const BASE = [190, 198, 210] // soft grey-blue dots at rest
const HOT = [112, 160, 58] // the app's green, deepened to read on a light surface

export default function GeneratingDots({
  label = 'Generating image…',
  expectedSeconds = 50,
  startedAt,
  ambient = false,
}: {
  label?: string
  expectedSeconds?: number
  /** When the work really began (ms since epoch). Without it the tile counts from when it appeared. */
  startedAt?: number
  /** Only the moving dots: no label, percentage or bar. Used as a quiet background. */
  ambient?: boolean
}) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const percent = useEstimatedPercent(expectedSeconds, startedAt)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) return
    const reduced =
      typeof window.matchMedia === 'function' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

    let width = 0
    let height = 0
    let raf = 0
    const dpr = Math.min(2, window.devicePixelRatio || 1)

    const resize = () => {
      const box = canvas.getBoundingClientRect()
      width = Math.max(1, Math.round(box.width))
      height = Math.max(1, Math.round(box.height))
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    const observer = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(resize) : null
    observer?.observe(canvas)

    const draw = (now: number) => {
      const t = reduced ? 0 : now / 1000
      ctx.clearRect(0, 0, width, height)
      const big = Math.max(width, height)
      const blobs = [
        { x: width * (0.35 + 0.22 * Math.sin(t * 0.5)), y: height * (0.3 + 0.2 * Math.cos(t * 0.37)), r: big * 0.34 },
        { x: width * (0.72 + 0.18 * Math.cos(t * 0.43)), y: height * (0.72 + 0.16 * Math.sin(t * 0.55)), r: big * 0.3 },
        { x: width * (0.5 + 0.3 * Math.sin(t * 0.27 + 2)), y: height * (0.5 + 0.3 * Math.cos(t * 0.31 + 1)), r: big * 0.22 },
      ]
      const cols = Math.ceil(width / SPACING)
      const rows = Math.ceil(height / SPACING)
      const offX = (width - (cols - 1) * SPACING) / 2
      const offY = (height - (rows - 1) * SPACING) / 2
      for (let row = 0; row < rows; row++) {
        for (let col = 0; col < cols; col++) {
          const x = offX + col * SPACING
          const y = offY + row * SPACING
          let glow = 0
          for (const b of blobs) {
            const d = Math.hypot(x - b.x, y - b.y) / b.r
            glow += Math.exp(-d * d * 2.2)
          }
          const flicker = reduced ? 0 : 0.08 * Math.sin(t * 2 + col * 0.7 + row * 0.9)
          const level = Math.max(0, Math.min(1, glow * 0.85 + flicker))
          const alpha = 0.45 + level * 0.55
          const radius = 1 + level * 1.7
          const r = Math.round(BASE[0] + (HOT[0] - BASE[0]) * level)
          const g = Math.round(BASE[1] + (HOT[1] - BASE[1]) * level)
          const bl = Math.round(BASE[2] + (HOT[2] - BASE[2]) * level)
          ctx.fillStyle = `rgba(${r},${g},${bl},${alpha.toFixed(3)})`
          ctx.beginPath()
          ctx.arc(x, y, radius, 0, Math.PI * 2)
          ctx.fill()
        }
      }
      if (!reduced) raf = requestAnimationFrame(draw)
    }
    raf = requestAnimationFrame(draw)

    return () => {
      cancelAnimationFrame(raf)
      observer?.disconnect()
    }
  }, [])

  return (
    <div
      className={`absolute inset-0 overflow-hidden ${ambient ? '' : 'bg-gradient-to-br from-surface to-white'}`}
      role={ambient ? 'presentation' : 'status'}
      aria-live={ambient ? undefined : 'polite'}
      aria-label={ambient ? undefined : `${label} ${percent}%`}
      aria-hidden={ambient ? true : undefined}
    >
      <canvas ref={canvasRef} className="absolute inset-0 h-full w-full" />
      {!ambient && (
      <>
      <span className="absolute left-3 top-3 rounded-full bg-white/90 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-charcoal shadow-sm">
        {label}
      </span>
      <span className="absolute bottom-3 right-3 rounded-full border border-border bg-white px-3 py-1.5 text-sm font-bold tabular-nums text-charcoal shadow-card">
        {percent}%
      </span>
      <div className="absolute inset-x-0 bottom-0 h-1 bg-border/60">
        <div className="h-full bg-accent transition-[width] duration-300 ease-out" style={{ width: `${percent}%` }} />
      </div>
      </>
      )}
    </div>
  )
}
