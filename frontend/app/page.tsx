import type { Metadata } from 'next'
import LandingPage from '@/components/landing/LandingPage'

export const metadata: Metadata = {
  title: 'CreativeStudio AI | Professional AI Image and Video Production',
  description:
    'Create brand-controlled image and video campaigns with professional model routing, role-based references, placement formats, and production-ready exports.',
}

export default function Home() {
  return (
    <div className="lp-font-scope">
      <LandingPage />
    </div>
  )
}
