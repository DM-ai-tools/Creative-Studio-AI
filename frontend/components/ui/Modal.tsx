'use client'

import React, { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'
import { cn } from '@/lib/utils'

interface ModalProps {
  isOpen: boolean
  onClose(): void
  title: string
  subtitle?: string
  children: React.ReactNode
  footer?: React.ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | '2xl'
  /** Don't close on backdrop click */
  persistent?: boolean
}

const sizes: Record<string, string> = {
  sm:  'max-w-sm',
  md:  'max-w-lg',
  lg:  'max-w-2xl',
  xl:  'max-w-4xl',
  '2xl': 'max-w-6xl',
}

export default function Modal({
  isOpen,
  onClose,
  title,
  subtitle,
  children,
  footer,
  size = 'md',
  persistent = false,
}: ModalProps) {
  const [mounted, setMounted] = useState(false)
  const [visible, setVisible] = useState(false)

  useEffect(() => { setMounted(true) }, [])

  useEffect(() => {
    if (isOpen) {
      // Small delay so CSS transition fires
      requestAnimationFrame(() => setVisible(true))
    } else {
      setVisible(false)
    }
  }, [isOpen])

  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !persistent) onClose()
    }
    if (isOpen) document.addEventListener('keydown', handler)
    return () => document.removeEventListener('keydown', handler)
  }, [isOpen, onClose, persistent])

  useEffect(() => {
    if (!isOpen) return
    const prev = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => { document.body.style.overflow = prev }
  }, [isOpen])

  if (!isOpen || !mounted) return null

  return createPortal(
    <div
      className={cn(
        'fixed inset-0 z-50 flex items-center justify-center p-4',
        'transition-opacity duration-200',
        visible ? 'opacity-100' : 'opacity-0'
      )}
    >
      {/* Backdrop */}
      <div
        className={cn(
          'absolute inset-0 bg-ink/50 backdrop-blur-sm',
          'transition-opacity duration-200',
          visible ? 'opacity-100' : 'opacity-0'
        )}
        onClick={persistent ? undefined : onClose}
        aria-hidden
      />

      {/* Panel */}
      <div
        className={cn(
          'relative w-full flex flex-col',
          'max-h-[min(90dvh,calc(100vh-2rem))]',
          'bg-white/95 backdrop-blur-2xl',
          'rounded-2xl overflow-hidden',
          'shadow-[0_0_0_1px_rgba(255,255,255,0.12),0_32px_64px_rgba(26,26,26,0.22)]',
          'border border-white/60',
          'transition-all duration-300 ease-premium',
          visible ? 'opacity-100 translate-y-0 scale-100' : 'opacity-0 translate-y-3 scale-[0.97]',
          sizes[size]
        )}
        role="dialog"
        aria-modal="true"
        aria-labelledby="modal-title"
      >
        {/* Header */}
        <div className="flex shrink-0 items-center justify-between px-6 py-4 border-b border-border/50 bg-gradient-to-r from-surface/40 to-transparent">
          <div className="min-w-0">
            <h2 id="modal-title" className="text-base font-bold text-charcoal tracking-tight">
              {title}
            </h2>
            {subtitle && (
              <p className="text-[11px] text-muted mt-0.5">{subtitle}</p>
            )}
          </div>
          <button
            onClick={onClose}
            className={cn(
              'ml-4 shrink-0 w-7 h-7 flex items-center justify-center rounded-lg',
              'text-muted hover:text-charcoal',
              'hover:bg-charcoal/[0.06]',
              'transition-all duration-150'
            )}
            aria-label="Close"
          >
            <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 min-h-0 overflow-y-auto overscroll-contain px-6 py-5">
          {children}
        </div>

        {/* Footer */}
        {footer && (
          <div className="shrink-0 border-t border-border/50 px-6 py-4 bg-surface/40 rounded-b-2xl">
            {footer}
          </div>
        )}
      </div>
    </div>,
    document.body
  )
}
