import React from 'react'
import {
  BarChart3,
  Check,
  Clapperboard,
  Download,
  Eye,
  Film,
  FileText,
  FolderKanban,
  History,
  Image as ImageLucide,
  Images,
  LayoutDashboard,
  LogOut,
  Mail,
  Palette,
  Plus,
  Rocket,
  Settings,
  ShieldCheck,
  Sparkles,
  Trash2,
  TrendingUp,
  Upload,
  Wand2,
  type LucideIcon,
} from 'lucide-react'
import { cn } from '@/lib/utils'

/**
 * The app's icons: one consistent set (Lucide), same size and stroke everywhere.
 * Each export keeps the name the rest of the app already uses, so a call site never changes.
 */
type IconProps = { className?: string }

const base = 'w-[18px] h-[18px] shrink-0'

function make(Icon: LucideIcon) {
  return function AppIcon({ className }: IconProps) {
    return <Icon className={cn(base, className)} strokeWidth={1.75} aria-hidden="true" />
  }
}

export const IconDashboard = make(LayoutDashboard)
export const IconPalette = make(Palette)
export const IconFileText = make(FileText)
export const IconFilm = make(Film)
export const IconShield = make(ShieldCheck)
export const IconTrending = make(TrendingUp)
export const IconRocket = make(Rocket)
export const IconSettings = make(Settings)
export const IconLogOut = make(LogOut)
export const IconSparkles = make(Sparkles)
export const IconUsage = make(BarChart3)
export const IconHistory = make(History)
export const IconMail = make(Mail)

// New: so each place in the app has its own icon instead of sharing one.
export const IconProjects = make(FolderKanban)
export const IconLibrary = make(Images)
export const IconEditor = make(Clapperboard)
export const IconImage = make(ImageLucide)
export const IconWand = make(Wand2)
export const IconUpload = make(Upload)
export const IconDownload = make(Download)
export const IconCheck = make(Check)
export const IconPlus = make(Plus)
export const IconTrash = make(Trash2)
export const IconEye = make(Eye)
