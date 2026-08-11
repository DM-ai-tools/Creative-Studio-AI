import type { Metadata } from 'next'
import { Syne, Manrope } from 'next/font/google'
import LandingPage from '@/components/landing/LandingPage'

const syne = Syne({
  subsets: ['latin'],
  variable: '--font-lp-display',
  weight: ['600', '700', '800'],
})

const manrope = Manrope({
  subsets: ['latin'],
  variable: '--font-lp-body',
  weight: ['400', '500', '600', '700', '800'],
})

export const metadata: Metadata = {
  title: 'CreativeStudio AI — AI creative suite for Meta Ads',
  description:
    'Brief in, on-brand variants out. Use cases, ad angles, ICP image plans, brand safety, and Meta export — built for Australian marketers.',
}

export default function Home() {
  return (
    <div className={`${syne.variable} ${manrope.variable}`}>
      <LandingPage />
    </div>
  )
}
