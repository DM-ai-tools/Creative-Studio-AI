import type { Metadata } from 'next'
import { Manrope } from 'next/font/google'
import LandingPage from '@/components/landing/LandingPage'

const manrope = Manrope({
  subsets: ['latin'],
  variable: '--font-lp-body',
  weight: ['400', '500', '600', '700', '800'],
})

export const metadata: Metadata = {
  title: 'CreativeStudio AI | Professional AI Image and Video Production',
  description:
    'Create brand-controlled image and video campaigns with professional model routing, role-based references, placement formats, and production-ready exports.',
}

export default function Home() {
  return (
    <div className={`${manrope.variable} lp-font-scope`}>
      <LandingPage />
    </div>
  )
}
