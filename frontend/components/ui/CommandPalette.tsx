'use client'

import React, { useEffect, useMemo, useRef, useState } from 'react'
import { useRouter } from 'next/navigation'
import { AnimatePresence, motion, useReducedMotion } from 'framer-motion'
import { CornerDownLeft, Search } from 'lucide-react'
import {
  IconDashboard,
  IconEditor,
  IconHistory,
  IconLibrary,
  IconMail,
  IconPalette,
  IconPlus,
  IconProjects,
  IconRocket,
  IconShield,
  IconTrending,
  IconUsage,
} from '@/components/ui/icons'

type Item = { href: string; label: string; hint: string; icon: React.ReactNode; keywords?: string }

const ITEMS: Item[] = [
  { href: '/briefs/new', label: 'New project', hint: 'Start a new campaign', icon: <IconPlus />, keywords: 'create brief campaign' },
  { href: '/dashboard', label: 'Dashboard', hint: 'Your creative performance', icon: <IconDashboard /> },
  { href: '/brand-kit', label: 'Brand Kit', hint: 'Logos, colours, fonts', icon: <IconPalette />, keywords: 'brand colour color logo font palette' },
  { href: '/briefs', label: 'Projects', hint: 'All your projects', icon: <IconProjects />, keywords: 'briefs campaigns' },
  { href: '/variants', label: 'Creative library', hint: 'Every creative you made', icon: <IconLibrary />, keywords: 'variants images' },
  { href: '/email-templates', label: 'Email templates', hint: 'Draft emails', icon: <IconMail /> },
  { href: '/editor', label: 'Video editor', hint: 'Edit your videos', icon: <IconEditor /> },
  { href: '/history', label: 'Generation history', hint: 'Past images and videos', icon: <IconHistory /> },
  { href: '/brand-safety', label: 'Brand & content checks', hint: 'Compliance results', icon: <IconShield />, keywords: 'compliance safety' },
  { href: '/performance', label: 'Performance', hint: 'How your ads perform', icon: <IconTrending />, keywords: 'roas stats' },
  { href: '/export', label: 'Export to Meta', hint: 'Send approved creatives', icon: <IconRocket /> },
  { href: '/usage', label: 'Usage & costs', hint: 'Credits and spend', icon: <IconUsage />, keywords: 'billing credits' },
]

/** Ctrl+K (or Cmd+K) opens a quick "go to" search over the app's pages. Arrow keys move, Enter opens, Esc closes. */
export default function CommandPalette({ isAllowed }: { isAllowed?: (href: string) => boolean }) {
  const router = useRouter()
  const reduce = useReducedMotion()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)
  const inputRef = useRef<HTMLInputElement | null>(null)

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    return ITEMS.filter((item) => (isAllowed ? isAllowed(item.href) : true)).filter(
      (item) => !q || `${item.label} ${item.hint} ${item.keywords ?? ''}`.toLowerCase().includes(q),
    )
  }, [query, isAllowed])

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault()
        setOpen((value) => !value)
      } else if (event.key === 'Escape') {
        setOpen(false)
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  useEffect(() => {
    if (open) {
      setQuery('')
      setActive(0)
      window.setTimeout(() => inputRef.current?.focus(), 30)
    }
  }, [open])

  useEffect(() => setActive(0), [query])

  const go = (href: string) => {
    setOpen(false)
    router.push(href)
  }

  const onInputKey = (event: React.KeyboardEvent) => {
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setActive((i) => Math.min(results.length - 1, i + 1))
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setActive((i) => Math.max(0, i - 1))
    } else if (event.key === 'Enter' && results[active]) {
      event.preventDefault()
      go(results[active].href)
    }
  }

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-[100] flex items-start justify-center bg-charcoal/40 px-4 pt-[14vh] backdrop-blur-sm"
          initial={reduce ? false : { opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.15 }}
          onMouseDown={(event) => {
            if (event.target === event.currentTarget) setOpen(false)
          }}
        >
          <motion.div
            role="dialog"
            aria-label="Quick search"
            className="w-full max-w-lg overflow-hidden rounded-2xl border border-border bg-white shadow-2xl"
            initial={reduce ? false : { opacity: 0, y: -12, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            transition={{ duration: 0.2, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="flex items-center gap-3 border-b border-border px-4 py-3">
              <Search className="h-4 w-4 text-muted" aria-hidden="true" />
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={onInputKey}
                placeholder="Go to a page or start something…"
                className="flex-1 bg-transparent text-sm text-charcoal outline-none placeholder:text-lt"
                aria-label="Search pages"
              />
              <kbd className="rounded-md border border-border bg-surface px-1.5 py-0.5 text-[10px] font-semibold text-muted">Esc</kbd>
            </div>
            <ul className="max-h-[50vh] overflow-y-auto p-2">
              {results.length === 0 && <li className="px-3 py-6 text-center text-sm text-muted">Nothing matches “{query}”.</li>}
              {results.map((item, index) => (
                <li key={item.href}>
                  <button
                    type="button"
                    onMouseEnter={() => setActive(index)}
                    onClick={() => go(item.href)}
                    className={`flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors ${
                      index === active ? 'bg-accent/15' : 'hover:bg-surface'
                    }`}
                  >
                    <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-surface text-charcoal">{item.icon}</span>
                    <span className="min-w-0 flex-1">
                      <span className="block text-sm font-semibold text-charcoal">{item.label}</span>
                      <span className="block truncate text-[11px] text-muted">{item.hint}</span>
                    </span>
                    {index === active && <CornerDownLeft className="h-3.5 w-3.5 text-muted" aria-hidden="true" />}
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex items-center justify-between border-t border-border bg-surface px-4 py-2 text-[10px] text-muted">
              <span>↑ ↓ to move · Enter to open</span>
              <span>Ctrl K to close</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  )
}
