'use client'

import React, { useEffect, useState } from 'react'
import { useReducedMotion } from 'framer-motion'

/**
 * Shows a figure that counts up to its value once, e.g. "128", "3.4x" or "92%". Text without a number
 * (a dash, "n/a") is shown as it is. With reduced motion it just shows the final value.
 */
export default function CountUp({ value, duration = 0.9 }: { value: string | number; duration?: number }) {
  const reduce = useReducedMotion()
  const text = String(value ?? '')
  const match = text.match(/^([^0-9-]*)(-?[\d,]*\.?\d+)(.*)$/)
  const target = match ? parseFloat(match[2].replace(/,/g, '')) : NaN
  const decimals = match && match[2].includes('.') ? match[2].split('.')[1].length : 0
  const [shown, setShown] = useState<number>(reduce || Number.isNaN(target) ? target : 0)

  useEffect(() => {
    if (Number.isNaN(target)) return
    if (reduce) {
      setShown(target)
      return
    }
    let raf = 0
    const started = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - started) / (duration * 1000))
      const eased = 1 - Math.pow(1 - t, 3)
      setShown(target * eased)
      if (t < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration, reduce])

  if (!match || Number.isNaN(target)) return <>{text}</>
  const formatted = shown.toLocaleString(undefined, { minimumFractionDigits: decimals, maximumFractionDigits: decimals })
  return (
    <span className="tabular-nums" aria-label={text}>
      {match[1]}
      {formatted}
      {match[3]}
    </span>
  )
}
