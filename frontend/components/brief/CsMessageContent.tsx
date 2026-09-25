'use client'

import React, { useMemo, useState } from 'react'

const LONG_CHAR_THRESHOLD = 260
const LONG_LINE_THRESHOLD = 6

type Props = {
  content: string
  variant?: 'user' | 'assistant'
}

function isLongMessage(content: string) {
  const lines = content.split('\n').length
  return content.length > LONG_CHAR_THRESHOLD || lines > LONG_LINE_THRESHOLD
}

export default function CsMessageContent({ content, variant = 'assistant' }: Props) {
  const [expanded, setExpanded] = useState(false)
  const long = useMemo(() => isLongMessage(content), [content])
  const lineCount = useMemo(() => content.split('\n').length, [content])

  if (!long) {
    return <p className="text-sm whitespace-pre-wrap leading-relaxed">{content}</p>
  }

  const panelClass =
    variant === 'user'
      ? 'border-[#b8f000]/15 bg-black/25'
      : 'border-white/10 bg-black/30'

  if (!expanded) {
    return (
      <div className="space-y-2">
        <p className="text-sm whitespace-pre-wrap leading-relaxed line-clamp-3 text-white/85">
          {content}
        </p>
        <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[10px] text-white/45">
          <span>
            {content.length.toLocaleString()} chars · {lineCount} lines
          </span>
          <button
            type="button"
            onClick={() => setExpanded(true)}
            className="font-semibold text-[#b8f000]/90 hover:text-[#b8f000] underline-offset-2 hover:underline"
          >
            Show full prompt
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-2">
      <div
        className={`cs-message-scroll overflow-y-auto overscroll-contain rounded-lg border px-2.5 py-2 max-h-[min(16rem,38vh)] ${panelClass}`}
      >
        <p className="text-sm whitespace-pre-wrap leading-relaxed">{content}</p>
      </div>
      <div className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 text-[10px] text-white/45">
        <span>Scroll for full text · {content.length.toLocaleString()} chars</span>
        <button
          type="button"
          onClick={() => setExpanded(false)}
          className="font-semibold text-[#b8f000]/90 hover:text-[#b8f000] underline-offset-2 hover:underline"
        >
          Show less
        </button>
      </div>
    </div>
  )
}
