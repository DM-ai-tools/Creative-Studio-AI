'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import TextArea from '@/components/ui/TextArea'
import Select from '@/components/ui/Select'
import { AuthProvider } from '@/hooks/useAuth'
import { useApi } from '@/hooks/useApi'
import { brandsApi, briefsApi, metaApi } from '@/lib/api'

const STEPS = ['Brand', 'Connect', 'First Brief']

const INDUSTRY_OPTIONS = [
  { value: 'dtc', label: 'DTC E-commerce' },
  { value: 'saas', label: 'SaaS / B2B' },
  { value: 'local', label: 'Local / Trades' },
  { value: 'pro_services', label: 'Pro Services' },
  { value: 'digital_marketing', label: 'Digital Marketing' },
  { value: 'general', label: 'General' },
]

const OPTIONAL_CONNECTIONS = [
  { key: 'shopify', name: 'Shopify (Product Catalog)', desc: 'Powers dynamic product creatives', icon: '🛍', color: '#96BF48' },
  { key: 'drive', name: 'Google Drive', desc: 'Auto-export approved creatives', icon: '▶', color: '#4285F4' },
  { key: 'slack', name: 'Slack', desc: 'Notifications when generation finishes', icon: '#', color: '#4A154B' },
]

function StepIndicator({ current, total }: { current: number; total: number }) {
  return (
    <div className="flex items-center justify-center gap-0 mb-8 relative">
      <div className="absolute top-4 left-1/2 -translate-x-1/2 h-0.5 bg-border" style={{ width: `${(total - 1) * 120}px` }} />
      {STEPS.map((label, i) => {
        const done = i < current
        const active = i === current
        return (
          <div key={label} className="flex flex-col items-center relative z-10 w-[120px]">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-xs font-bold mb-1.5 ${
              done ? 'bg-green-500 text-white' : active ? 'bg-mint text-navy' : 'bg-light text-lt border border-border'
            }`}>
              {done ? '✓' : i + 1}
            </div>
            <span className={`text-[10px] font-semibold ${active || done ? 'text-navy' : 'text-lt'}`}>{label}</span>
          </div>
        )
      })}
    </div>
  )
}

function OnboardingContent() {
  const router = useRouter()
  const [step, setStep] = useState(() => {
    if (typeof window !== 'undefined') return Number(localStorage.getItem('cs_onboard_step') ?? 0)
    return 0
  })
  const [brandId, setBrandId] = useState<string | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const { data: metaStatus } = useApi(() => metaApi.getStatus(), [])

  const [brand, setBrand] = useState({ name: '', industry: 'dtc', language: 'English', voice: '', forbidden: '' })
  const [brief, setBrief] = useState({ title: '', product_name: '', objective: '', cta: 'Shop Now' })

  useEffect(() => {
    localStorage.setItem('cs_onboard_step', String(step))
  }, [step])

  const handleBrandSubmit = async () => {
    if (!brand.name) { toast.error('Enter your brand name'); return }
    setIsSaving(true)
    try {
      const b = await brandsApi.create({
        name: brand.name,
        industry: brand.industry,
        language: brand.language,
        voice_rules: { description: brand.voice },
        forbidden_words: brand.forbidden.split(',').map((w) => w.trim()).filter(Boolean),
      })
      setBrandId(b.id)
      setStep(1)
    } catch {
      toast.error('Failed to save brand')
    } finally {
      setIsSaving(false)
    }
  }

  const handleBriefSubmit = async () => {
    if (!brief.title || !brandId) { toast.error('Complete all fields'); return }
    setIsSaving(true)
    try {
      await briefsApi.create({
        brand_id: brandId,
        title: brief.title,
        product_name: brief.product_name,
        objective: brief.objective,
        cta: brief.cta,
        formats: ['static', 'reel'],
        ad_copy_tone: 'Professional',
        target_audience: 'General audience',
        key_benefits: {},
      })
      localStorage.removeItem('cs_onboard_step')
      toast.success('All set! Welcome to CreativeStudio AI 🎉')
      router.push('/dashboard')
    } catch {
      toast.error('Failed to create brief')
    } finally {
      setIsSaving(false)
    }
  }

  return (
    <div className="min-h-screen bg-light flex items-center justify-center p-6">
      <div className="w-full max-w-xl">
        <div className="text-center mb-6">
          <h1 className="text-2xl font-extrabold text-navy">Creative<span className="text-mint">Studio</span> AI</h1>
          <p className="text-xs text-lt mt-1">Let's set up your workspace in 3 quick steps</p>
        </div>

        <div className="bg-white rounded-2xl p-8 shadow-lg border border-border">
          <StepIndicator current={step} total={3} />

          {/* Step 1: Brand */}
          {step === 0 && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-navy">Tell us about your brand</h2>
              <p className="text-xs text-lt -mt-2">CreativeStudio AI uses this to calibrate every generated creative.</p>
              <Input label="Brand Name" placeholder="Northwood Coffee Co." value={brand.name} onChange={(e) => setBrand({ ...brand, name: e.target.value })} />
              <div className="grid grid-cols-2 gap-3">
                <Select label="Industry" options={INDUSTRY_OPTIONS} value={brand.industry} onChange={(e) => setBrand({ ...brand, industry: e.target.value })} />
                <Select label="Language" options={[{ value: 'English', label: 'English' }, { value: 'Spanish', label: 'Spanish' }]} value={brand.language} onChange={(e) => setBrand({ ...brand, language: e.target.value })} />
              </div>
              <TextArea label="Brand Voice" placeholder="Warm and direct. Speaks like a friendly barista..." value={brand.voice} onChange={(e) => setBrand({ ...brand, voice: e.target.value })} />
              <Input label="Forbidden Words / Claims" placeholder="cures, miracle, guaranteed" hint="Comma-separated" value={brand.forbidden} onChange={(e) => setBrand({ ...brand, forbidden: e.target.value })} />
              <Button variant="primary" size="lg" className="w-full" isLoading={isSaving} onClick={handleBrandSubmit}>
                Continue → Connect Accounts
              </Button>
            </div>
          )}

          {/* Step 2: Connections */}
          {step === 1 && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-navy">Workspace connections</h2>
              <p className="text-xs text-lt -mt-2">Meta uses server credentials from backend configuration. Optional integrations can be added later.</p>
              <div className="p-3 border border-border rounded-xl flex items-center justify-between gap-3">
                <div className="flex items-center gap-3">
                  <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-base font-bold" style={{ backgroundColor: '#1877F2' }}>f</div>
                  <div>
                    <div className="text-sm font-bold text-navy">Meta Business Manager</div>
                    <div className="text-[10px] text-lt">Configured from META_APP_ID and META_ACCESS_TOKEN</div>
                  </div>
                </div>
                <span className={`px-3 py-1.5 text-xs font-bold rounded-lg border ${
                  metaStatus?.connected
                    ? 'bg-green-50 border-green-300 text-green-700'
                    : 'bg-amber-50 border-amber-300 text-amber-700'
                }`}>
                  {metaStatus?.connected ? 'Ready' : 'Not configured'}
                </span>
              </div>
              <div className="space-y-2">
                {OPTIONAL_CONNECTIONS.map((conn) => (
                  <div key={conn.key} className="flex items-center justify-between p-3 border border-border rounded-xl">
                    <div className="flex items-center gap-3">
                      <div className="w-9 h-9 rounded-lg flex items-center justify-center text-white text-base font-bold" style={{ backgroundColor: conn.color }}>
                        {conn.icon}
                      </div>
                      <div>
                        <div className="text-sm font-bold text-navy">{conn.name}</div>
                        <div className="text-[10px] text-lt">{conn.desc}</div>
                      </div>
                    </div>
                    <span className="px-3 py-1.5 text-xs font-bold rounded-lg border bg-light border-border text-mid">
                      Coming soon
                    </span>
                  </div>
                ))}
              </div>
              <Button variant="primary" size="lg" className="w-full" onClick={() => setStep(2)}>
                Continue → Create First Brief
              </Button>
            </div>
          )}

          {/* Step 3: First Brief */}
          {step === 2 && (
            <div className="space-y-4">
              <h2 className="text-lg font-bold text-navy">Create your first brief</h2>
              <p className="text-xs text-lt -mt-2">This will kick off your first AI creative generation.</p>
              <Input label="Campaign Title" placeholder="Spring Launch" value={brief.title} onChange={(e) => setBrief({ ...brief, title: e.target.value })} />
              <Input label="Product Name" placeholder="Ethiopian Single Origin Coffee" value={brief.product_name} onChange={(e) => setBrief({ ...brief, product_name: e.target.value })} />
              <TextArea label="Campaign Objective" placeholder="Drive subscription sign-ups..." value={brief.objective} onChange={(e) => setBrief({ ...brief, objective: e.target.value })} />
              <Input label="Call to Action" placeholder="Shop Now" value={brief.cta} onChange={(e) => setBrief({ ...brief, cta: e.target.value })} />
              <Button variant="primary" size="lg" className="w-full" isLoading={isSaving} onClick={handleBriefSubmit}>
                Launch CreativeStudio AI 🚀
              </Button>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default function OnboardingPage() {
  return (
    <AuthProvider>
      <OnboardingContent />
    </AuthProvider>
  )
}
