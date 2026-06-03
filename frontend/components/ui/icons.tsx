import React from 'react'
import { cn } from '@/lib/utils'

type IconProps = { className?: string }

const base = 'w-[18px] h-[18px] shrink-0'

export function IconDashboard({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </svg>
  )
}

export function IconPalette({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <circle cx="12" cy="12" r="9" />
      <circle cx="8" cy="10" r="1.25" fill="currentColor" stroke="none" />
      <circle cx="14" cy="8" r="1.25" fill="currentColor" stroke="none" />
      <circle cx="15" cy="14" r="1.25" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconFileText({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
      <path d="M14 2v6h6M16 13H8M16 17H8M10 9H8" />
    </svg>
  )
}

export function IconFilm({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <rect x="2" y="4" width="20" height="16" rx="2" />
      <path d="M2 8h20M7 4v4M17 4v4" />
    </svg>
  )
}

export function IconShield({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M12 2l8 4v6c0 5-3.5 9.5-8 10-4.5-.5-8-5-8-10V6l8-4z" />
    </svg>
  )
}

export function IconTrending({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M3 17l6-6 4 4 8-10" />
      <path d="M14 5h7v7" />
    </svg>
  )
}

export function IconRocket({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M4.5 16.5c1.5-4 5-7.5 9-9l2-2 4 1-1 4-2 2c-1.5 4-5 7.5-9 9l-3 1 1-3z" />
      <circle cx="15" cy="9" r="1" fill="currentColor" stroke="none" />
    </svg>
  )
}

export function IconSettings({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <circle cx="12" cy="12" r="3" />
      <path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42" />
    </svg>
  )
}

export function IconLogOut({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9" />
    </svg>
  )
}

export function IconSparkles({ className }: IconProps) {
  return (
    <svg className={cn(base, className)} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75">
      <path d="M12 2v4M12 18v4M4.93 4.93l2.83 2.83M16.24 16.24l2.83 2.83M2 12h4M18 12h4M4.93 19.07l2.83-2.83M16.24 7.76l2.83-2.83" />
      <circle cx="12" cy="12" r="3" fill="currentColor" stroke="none" opacity="0.9" />
    </svg>
  )
}
