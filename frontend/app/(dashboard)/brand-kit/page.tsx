'use client'

import React, { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import { useForm, type UseFormRegister } from 'react-hook-form'
import Topbar from '@/components/layout/Topbar'
import BrandKitPreview from '@/components/brand-kit/BrandKitPreview'
import LogoUploadZone from '@/components/brand-kit/LogoUploadZone'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import TextArea from '@/components/ui/TextArea'
import Select from '@/components/ui/Select'
import { PageLoader } from '@/components/ui/Loading'
import { IconPalette, IconShield } from '@/components/ui/icons'
import { brandsApi } from '@/lib/api'
import { AGENCY_INDUSTRY_OPTIONS } from '@/lib/industries'
import { assetUrl, cn } from '@/lib/utils'
import type { Brand, BrandKit } from '@/types'

const LANGUAGE_OPTIONS = [
  { value: 'English', label: 'English' },
  { value: 'Spanish', label: 'Spanish' },
  { value: 'French', label: 'French' },
]

function SectionBlock({
  step,
  title,
  description,
  children,
  className,
}: {
  step: string
  title: string
  description: string
  children: React.ReactNode
  className?: string
}) {
  return (
    <section
      className={cn(
        'card-premium p-6 md:p-7 animate-fade-in h-full min-h-0 flex flex-col',
        className
      )}
    >
      <div className="flex items-start gap-4 mb-6 pb-5 border-b border-border/60 shrink-0">
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-accent/15 text-xs font-bold text-[#3d5c22]">
          {step}
        </span>
        <div className="min-w-0">
          <h2 className="text-base font-bold text-charcoal tracking-tight">{title}</h2>
          <p className="text-sm text-muted mt-0.5 leading-relaxed">{description}</p>
        </div>
      </div>
      <div className="flex-1 flex flex-col min-h-0">{children}</div>
    </section>
  )
}

/** Pairs left + right cards in one row so tops align and heights match. */
function CardRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch w-full">{children}</div>
  )
}

type BrandKitForm = {
  name: string
  industry: string
  language: string
  voice_description: string
  forbidden_words: string
  primary_color: string
  secondary_color: string
  font_heading: string
  font_body: string
}

function ColorField({
  label,
  register,
  name,
  value,
}: {
  label: string
  register: UseFormRegister<BrandKitForm>
  name: 'primary_color' | 'secondary_color'
  value: string
}) {
  return (
    <div className="rounded-2xl border border-border/80 bg-surface/60 p-4 h-full flex flex-col">
      <p className="label-ui mb-3">{label}</p>
      <div
        className="h-20 rounded-xl border border-border/60 mb-3 shadow-inner transition-colors duration-300"
        style={{ backgroundColor: value || '#cccccc' }}
      />
      <div className="flex items-center gap-2">
        <input
          type="color"
          {...register(name)}
          className="w-10 h-10 rounded-lg border border-border cursor-pointer shrink-0"
        />
        <Input placeholder="#FF6B00" {...register(name)} className="flex-1 font-mono text-sm" />
      </div>
    </div>
  )
}

export default function BrandKitPage() {
  const [brand, setBrand] = useState<Brand | null>(null)
  const [kit, setKit] = useState<BrandKit | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isUploadingLogo, setIsUploadingLogo] = useState(false)
  const [isUploadingLogoLight, setIsUploadingLogoLight] = useState(false)

  const { register, handleSubmit, reset, watch } = useForm<BrandKitForm>()

  const watched = watch()

  useEffect(() => {
    async function load() {
      try {
        const brands = await brandsApi.list()
        if (brands.length > 0) {
          const b = brands[0]
          setBrand(b)
          const voice = b.voice_rules as { description?: string }
          reset({
            name: b.name,
            industry: b.industry,
            language: b.language,
            voice_description: voice?.description ?? '',
            forbidden_words: b.forbidden_words?.join(', ') ?? '',
            primary_color: b.primary_color ?? '#FF6B00',
            secondary_color: b.secondary_color ?? '#FFD200',
            font_heading: '',
            font_body: '',
          })
          try {
            const k = await brandsApi.getKit(b.id)
            setKit(k)
            reset((prev) => ({
              ...prev,
              font_heading: (k.fonts as { heading?: string })?.heading ?? '',
              font_body: (k.fonts as { body?: string })?.body ?? '',
            }))
          } catch {
            /* no kit yet */
          }
        }
      } catch {
        /* no brands */
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [reset])

  const onSubmit = async (data: {
    name: string
    industry: string
    language: string
    voice_description: string
    forbidden_words: string
    primary_color: string
    secondary_color: string
    font_heading: string
    font_body: string
  }) => {
    setIsSaving(true)
    try {
      const brandData = {
        name: data.name,
        industry: data.industry,
        language: data.language,
        voice_rules: { description: data.voice_description },
        forbidden_words: data.forbidden_words.split(',').map((w) => w.trim()).filter(Boolean),
        primary_color: data.primary_color,
        secondary_color: data.secondary_color,
      }
      const preservedLogoVariations =
        kit?.logo_variations && typeof kit.logo_variations === 'object'
          ? { ...(kit.logo_variations as Record<string, unknown>) }
          : {}
      const kitData = {
        name: kit?.name ?? 'Default Kit',
        colors: { primary: data.primary_color, secondary: data.secondary_color },
        fonts: { heading: data.font_heading, body: data.font_body },
        logo_variations: preservedLogoVariations,
      }
      if (brand) {
        const updated = await brandsApi.update(brand.id, brandData)
        setBrand(updated)
        if (kit) {
          const updatedKit = await brandsApi.updateKit(brand.id, kit.id, kitData)
          setKit(updatedKit)
        } else {
          const newKit = await brandsApi.createKit(brand.id, kitData)
          setKit(newKit)
        }
      } else {
        const newBrand = await brandsApi.create(brandData)
        setBrand(newBrand)
        const newKit = await brandsApi.createKit(newBrand.id, kitData)
        setKit(newKit)
      }
      toast.success('Brand kit saved')
    } catch {
      toast.error('Failed to save brand kit')
    } finally {
      setIsSaving(false)
    }
  }

  const handleLogoUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!brand) {
      toast.error('Save your brand kit first (top-right), then upload a logo')
      event.target.value = ''
      return
    }
    if (!file.type.startsWith('image/')) {
      toast.error('Please upload a PNG or JPG logo')
      return
    }
    setIsUploadingLogo(true)
    try {
      const updated = await brandsApi.uploadLogo(brand.id, file)
      setBrand(updated)
      toast.success('Logo uploaded')
    } catch {
      toast.error('Failed to upload logo')
    } finally {
      setIsUploadingLogo(false)
      event.target.value = ''
    }
  }

  const logoPreview = assetUrl(brand?.logo_url ?? null, brand?.updated_at)
  const logoOnLightUrl = (kit?.logo_variations as { on_light?: string } | undefined)?.on_light
  const logoLightPreview = assetUrl(logoOnLightUrl ?? null, kit?.updated_at)

  const handleLogoOnLightUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!brand) {
      toast.error('Save your brand kit first (top-right), then upload a logo')
      event.target.value = ''
      return
    }
    if (!file.type.startsWith('image/')) {
      toast.error('Please upload a PNG or JPG logo')
      return
    }
    setIsUploadingLogoLight(true)
    try {
      const updatedKit = await brandsApi.uploadLogoOnLight(brand.id, file)
      setKit(updatedKit)
      toast.success('Light-background logo saved')
    } catch {
      toast.error('Failed to upload logo')
    } finally {
      setIsUploadingLogoLight(false)
      event.target.value = ''
    }
  }

  if (isLoading) return <PageLoader />

  return (
    <div className="flex flex-col min-h-full w-full">
      <Topbar
        title="Brand Kit"
        subtitle="Identity, voice, and visuals — applied to every generated creative"
        actions={
          <Button type="submit" form="brand-kit-form" variant="primary" isLoading={isSaving}>
            Save changes
          </Button>
        }
      />

      <form
        id="brand-kit-form"
        onSubmit={handleSubmit(onSubmit)}
        className="flex-1 w-full px-6 md:px-8 lg:px-10 py-6 md:py-8 space-y-8"
      >
        <BrandKitPreview
          brandName={watched.name ?? ''}
          industry={watched.industry ?? ''}
          logoUrl={logoPreview}
          logoLightUrl={logoLightPreview}
          primaryColor={watched.primary_color ?? '#FF6B00'}
          secondaryColor={watched.secondary_color ?? '#000000'}
          headingFont={watched.font_heading ?? ''}
          bodyFont={watched.font_body ?? ''}
        />

        <div className="flex flex-col gap-6 w-full">
          <CardRow>
            <SectionBlock
              step="01"
              title="Foundation"
              description="Core metadata used across briefs, exports, and compliance checks."
            >
              <div className="space-y-5 flex-1 flex flex-col">
                <Input label="Brand name" placeholder="Click Trends" {...register('name')} />
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-5">
                  <Select
                    label="Agency type"
                    options={AGENCY_INDUSTRY_OPTIONS.map((o) => ({ value: o.value, label: o.label }))}
                    {...register('industry')}
                  />
                  <Select label="Default language" options={LANGUAGE_OPTIONS} {...register('language')} />
                </div>
                <p className="text-xs text-muted rounded-xl bg-surface/80 border border-border/60 px-4 py-3 leading-relaxed mt-auto">
                  This is your agency profile. Target industries for each campaign are set when you create a brief.
                </p>
              </div>
            </SectionBlock>

            <SectionBlock
              step="04"
              title="Logos"
              description="Burned onto every generated video: light mark on dark areas, dark mark on bright corners (auto-detected)."
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1 h-full min-h-[200px] auto-rows-fr">
                <LogoUploadZone
                  label="On dark"
                  hint="White or light text on charcoal backgrounds"
                  previewUrl={logoPreview}
                  variant="dark"
                  emptyLabel="Upload logo"
                  uploadLabel="Replace logo"
                  isUploading={isUploadingLogo}
                  disabled={!brand}
                  disabledHint={!brand ? 'Click “Save changes” above first' : undefined}
                  onChange={handleLogoUpload}
                />
                <LogoUploadZone
                  label="On light"
                  hint="Optional — dark text for white ad canvases"
                  previewUrl={logoLightPreview}
                  variant="light"
                  emptyLabel="Upload light logo"
                  uploadLabel="Replace light logo"
                  isUploading={isUploadingLogoLight}
                  disabled={!brand}
                  disabledHint={!brand ? 'Click “Save changes” above first' : undefined}
                  onChange={handleLogoOnLightUpload}
                />
              </div>
            </SectionBlock>
          </CardRow>

          <CardRow>
            <SectionBlock
              step="02"
              title="Voice & tone"
              description="Guides AI copy generation — tone, personality, and messaging style."
            >
              <div className="flex flex-1 flex-col min-h-[240px] [&_textarea]:min-h-[200px] [&_textarea]:flex-1">
                <TextArea
                  label="Brand voice & style guide"
                  placeholder="Bold, confident, AI-forward. Short sentences. Lead with outcomes…"
                  rows={10}
                  {...register('voice_description')}
                />
              </div>
            </SectionBlock>

            <SectionBlock
              step="05"
              title="Color palette"
              description="Primary drives CTAs and accents; secondary supports backgrounds and type."
            >
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 flex-1 h-full auto-rows-fr">
                <ColorField
                  label="Primary"
                  register={register}
                  name="primary_color"
                  value={watched.primary_color ?? ''}
                />
                <ColorField
                  label="Secondary"
                  register={register}
                  name="secondary_color"
                  value={watched.secondary_color ?? ''}
                />
              </div>
            </SectionBlock>
          </CardRow>

          <CardRow>
            <SectionBlock
              step="03"
              title="Compliance guardrails"
              description="Blocked terms and claims — generation will fail compliance if these appear."
            >
              <div className="flex flex-col flex-1 gap-4">
                <div className="flex gap-3 p-4 rounded-2xl bg-accent/[0.08] border border-accent/20">
                  <IconShield className="w-5 h-5 text-[#3d5c22] shrink-0 mt-0.5" />
                  <p className="text-xs text-muted leading-relaxed">
                    Add comma-separated words or phrases your brand cannot use (e.g. medical claims, guarantees, superlatives).
                  </p>
                </div>
                <Input
                  label="Forbidden words / claims"
                  placeholder="cures, guaranteed, miracle, cheapest, #1"
                  {...register('forbidden_words')}
                />
              </div>
            </SectionBlock>

            <SectionBlock
              step="06"
              title="Typography"
              description="Optional — preview updates in the hero mockup above."
            >
              <div className="flex flex-col flex-1 gap-4">
                <div className="flex items-center gap-2 text-muted shrink-0">
                  <IconPalette className="w-4 h-4 text-accent" />
                  <span className="text-xs">Leave blank to use system defaults (Inter)</span>
                </div>
                <Input label="Heading font" placeholder="e.g. Inter, 700" {...register('font_heading')} />
                <Input label="Body font" placeholder="e.g. Inter, 400" {...register('font_body')} />
                {(watched.font_heading || watched.font_body) && (
                  <div className="mt-auto p-4 rounded-2xl border border-border/70 bg-surface/50">
                    <p
                      className="text-lg font-bold text-charcoal"
                      style={watched.font_heading ? { fontFamily: watched.font_heading } : undefined}
                    >
                      Heading preview
                    </p>
                    <p
                      className="text-sm text-muted mt-2"
                      style={watched.font_body ? { fontFamily: watched.font_body } : undefined}
                    >
                      Body preview — The quick brown fox jumps over the lazy dog.
                    </p>
                  </div>
                )}
              </div>
            </SectionBlock>
          </CardRow>
        </div>

        <div className="lg:hidden sticky bottom-0 z-10 -mx-6 px-6 py-4 glass-topbar border-t border-border/80">
          <Button type="submit" variant="primary" size="lg" isLoading={isSaving} className="w-full">
            Save changes
          </Button>
        </div>
      </form>
    </div>
  )
}
