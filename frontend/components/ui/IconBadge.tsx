import React from 'react'
import { cn } from '@/lib/utils'

type Tone = 'accent' | 'dark' | 'soft' | 'sky' | 'violet' | 'amber' | 'rose'
type Size = 'sm' | 'md' | 'lg'

const TONES: Record<Tone, string> = {
  accent: 'bg-gradient-to-br from-[#bfe589] to-[#7fae48] text-white shadow-[0_6px_16px_rgba(127,174,72,0.35)]',
  dark: 'bg-gradient-to-br from-[#41434c] to-[#1d1e24] text-accent shadow-[0_6px_16px_rgba(0,0,0,0.25)]',
  soft: 'bg-accent/15 text-[#5b8a2d]',
  sky: 'bg-gradient-to-br from-sky-300 to-sky-500 text-white shadow-[0_6px_16px_rgba(14,165,233,0.3)]',
  violet: 'bg-gradient-to-br from-violet-300 to-violet-500 text-white shadow-[0_6px_16px_rgba(139,92,246,0.3)]',
  amber: 'bg-gradient-to-br from-amber-300 to-orange-400 text-white shadow-[0_6px_16px_rgba(251,146,60,0.3)]',
  rose: 'bg-gradient-to-br from-rose-300 to-rose-500 text-white shadow-[0_6px_16px_rgba(244,63,94,0.3)]',
}

const SIZES: Record<Size, string> = {
  sm: 'h-7 w-7 rounded-lg [&_svg]:h-4 [&_svg]:w-4',
  md: 'h-10 w-10 rounded-xl [&_svg]:h-5 [&_svg]:w-5',
  lg: 'h-12 w-12 rounded-2xl [&_svg]:h-6 [&_svg]:w-6',
}

/**
 * An icon on a soft gradient tile. Put it inside a parent with the `group` class and the tile tilts and
 * grows a little when the parent is hovered (it does nothing for people who asked for reduced motion).
 */
export default function IconBadge({
  icon,
  tone = 'accent',
  size = 'md',
  className,
}: {
  icon: React.ReactNode
  tone?: Tone
  size?: Size
  className?: string
}) {
  return (
    <span
      aria-hidden="true"
      className={cn(
        'inline-flex shrink-0 items-center justify-center transition-transform duration-300 ease-spring',
        'group-hover:scale-110 group-hover:-rotate-6 motion-reduce:transition-none motion-reduce:group-hover:transform-none',
        TONES[tone],
        SIZES[size],
        className,
      )}
    >
      {icon}
    </span>
  )
}
