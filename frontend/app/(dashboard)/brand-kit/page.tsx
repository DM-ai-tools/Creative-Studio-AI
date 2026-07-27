'use client'

import React, { useCallback, useEffect, useState } from 'react'
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

function CardRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch w-full">{children}</div>
  )
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

/** Brand list item in the sidebar */
function BrandListItem({
  brand,
  active,
  onClick,
}: {
  brand: Brand
  active: boolean
  onClick: () => void
}) {
  const initials = (brand.name || 'B')
    .split(' ')
    .map((w) => w[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()

  return (
    <button
      type="button"
      onClick={onClick}
      className={cn(
        'w-full flex items-center gap-3 px-3 py-2.5 rounded-xl text-left transition-all',
        active
          ? 'bg-accent/10 border border-accent/30 shadow-sm'
          : 'hover:bg-surface/80 border border-transparent'
      )}
    >
      {brand.logo_url ? (
        <img
          src={assetUrl(brand.logo_url, brand.updated_at) ?? ''}
          alt={brand.name}
          className="w-8 h-8 rounded-lg object-contain bg-charcoal border border-border/60 shrink-0"
        />
      ) : (
        <span
          className="w-8 h-8 rounded-lg flex items-center justify-center text-xs font-bold text-white shrink-0"
          style={{ backgroundColor: brand.primary_color || '#555' }}
        >
          {initials}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className={cn('text-sm font-semibold truncate', active ? 'text-accent' : 'text-charcoal')}>
          {brand.name}
        </p>
        <p className="text-[10px] text-muted truncate">{brand.industry || 'No industry set'}</p>
      </div>
      {active && (
        <span className="w-2 h-2 rounded-full bg-accent shrink-0" />
      )}
    </button>
  )
}

export default function BrandKitPage() {
  const [brands, setBrands] = useState<Brand[]>([])
  const [activeBrandId, setActiveBrandId] = useState<string | null>(null)
  const [activeKit, setActiveKit] = useState<BrandKit | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const [isUploadingLogo, setIsUploadingLogo] = useState(false)
  const [isUploadingLogoLight, setIsUploadingLogoLight] = useState(false)
  const [isCreatingNew, setIsCreatingNew] = useState(false)

  const { register, handleSubmit, reset, watch } = useForm<BrandKitForm>()
  const watched = watch()

  const activeBrand = brands.find((b) => b.id === activeBrandId) ?? null

  /** Load kit for a given brand and populate form */
  const loadBrand = useCallback(
    async (b: Brand) => {
      setActiveBrandId(b.id)
      setActiveKit(null)
      setIsCreatingNew(false)
      const voice = b.voice_rules as { description?: string }
      reset({
        name: b.name,
        industry: b.industry,
        language: b.language,
        voice_description: voice?.description ?? '',
        forbidden_words: b.forbidden_words?.join(', ') ?? '',
        primary_color: b.primary_color ?? '#FF6B00',
        secondary_color: b.secondary_color ?? '#1A1A2E',
        font_heading: '',
        font_body: '',
      })
      try {
        const k = await brandsApi.getKit(b.id)
        setActiveKit(k)
        reset((prev) => ({
          ...prev,
          font_heading: (k.fonts as { heading?: string })?.heading ?? '',
          font_body: (k.fonts as { body?: string })?.body ?? '',
        }))
      } catch {
        /* no kit yet — that's fine */
      }
    },
    [reset]
  )

  /** Initial load */
  useEffect(() => {
    async function load() {
      try {
        const list = await brandsApi.list()
        setBrands(list)
        if (list.length > 0) {
          await loadBrand(list[0])
        } else {
          // No brands — start in "create new" mode
          setIsCreatingNew(true)
          reset({
            name: '',
            industry: '',
            language: 'English',
            voice_description: '',
            forbidden_words: '',
            primary_color: '#FF6B00',
            secondary_color: '#1A1A2E',
            font_heading: '',
            font_body: '',
          })
        }
      } catch {
        /* ignore */
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [loadBrand, reset])

  /** Start creating a new brand */
  const handleNewBrand = () => {
    setActiveBrandId(null)
    setActiveKit(null)
    setIsCreatingNew(true)
    reset({
      name: '',
      industry: '',
      language: 'English',
      voice_description: '',
      forbidden_words: '',
      primary_color: '#FF6B00',
      secondary_color: '#1A1A2E',
      font_heading: '',
      font_body: '',
    })
  }

  const onSubmit = async (data: BrandKitForm) => {
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
        activeKit?.logo_variations && typeof activeKit.logo_variations === 'object'
          ? { ...(activeKit.logo_variations as Record<string, unknown>) }
          : {}
      const kitData = {
        name: activeKit?.name ?? 'Default Kit',
        colors: { primary: data.primary_color, secondary: data.secondary_color },
        fonts: { heading: data.font_heading, body: data.font_body },
        logo_variations: preservedLogoVariations,
      }

      let savedBrand: Brand
      if (activeBrand) {
        savedBrand = await brandsApi.update(activeBrand.id, brandData)
        // Update in list
        setBrands((prev) => prev.map((b) => (b.id === savedBrand.id ? savedBrand : b)))
        if (activeKit) {
          const updatedKit = await brandsApi.updateKit(activeBrand.id, activeKit.id, kitData)
          setActiveKit(updatedKit)
        } else {
          const newKit = await brandsApi.createKit(activeBrand.id, kitData)
          setActiveKit(newKit)
        }
      } else {
        // Creating a new brand
        savedBrand = await brandsApi.create(brandData)
        const newKit = await brandsApi.createKit(savedBrand.id, kitData)
        setActiveKit(newKit)
        setBrands((prev) => [...prev, savedBrand])
        setActiveBrandId(savedBrand.id)
        setIsCreatingNew(false)
      }
      toast.success(`Brand "${savedBrand.name}" saved`)
    } catch {
      toast.error('Failed to save brand kit')
    } finally {
      setIsSaving(false)
    }
  }

  const handleDeleteBrand = async () => {
    if (!activeBrand) return
    if (!confirm(`Delete brand "${activeBrand.name}"? This cannot be undone.`)) return
    setIsDeleting(true)
    try {
      await brandsApi.delete(activeBrand.id)
      const remaining = brands.filter((b) => b.id !== activeBrand.id)
      setBrands(remaining)
      if (remaining.length > 0) {
        await loadBrand(remaining[0])
      } else {
        handleNewBrand()
      }
      toast.success('Brand deleted')
    } catch {
      toast.error('Failed to delete brand')
    } finally {
      setIsDeleting(false)
    }
  }

  const handleLogoUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!activeBrand) {
      toast.error('Save the brand first, then upload a logo')
      event.target.value = ''
      return
    }
    setIsUploadingLogo(true)
    try {
      const updated = await brandsApi.uploadLogo(activeBrand.id, file)
      setBrands((prev) => prev.map((b) => (b.id === updated.id ? updated : b)))
      setActiveBrandId(updated.id)
      toast.success('Logo uploaded')
    } catch {
      toast.error('Failed to upload logo')
    } finally {
      setIsUploadingLogo(false)
      event.target.value = ''
    }
  }

  const handleLogoOnLightUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    if (!file) return
    if (!activeBrand) {
      toast.error('Save the brand first, then upload a logo')
      event.target.value = ''
      return
    }
    setIsUploadingLogoLight(true)
    try {
      const updatedKit = await brandsApi.uploadLogoOnLight(activeBrand.id, file)
      setActiveKit(updatedKit)
      toast.success('Light-background logo saved')
    } catch {
      toast.error('Failed to upload logo')
    } finally {
      setIsUploadingLogoLight(false)
      event.target.value = ''
    }
  }

  const logoPreview = assetUrl(activeBrand?.logo_url ?? null, activeBrand?.updated_at)
  const logoOnLightUrl = (activeKit?.logo_variations as { on_light?: string } | undefined)?.on_light
  const logoLightPreview = assetUrl(logoOnLightUrl ?? null, activeKit?.updated_at)

  if (isLoading) return <PageLoader />

  return (
    <div className="flex flex-col min-h-full w-full">
      <Topbar
        title="Brand Kit"
        subtitle="Manage multiple brands — each with its own identity, voice, and visuals"
        actions={
          <div className="flex items-center gap-2">
            {activeBrand && (
              <Button
                type="button"
                variant="outline"
                size="sm"
                isLoading={isDeleting}
                onClick={() => void handleDeleteBrand()}
                className="text-red-600 border-red-200 hover:bg-red-50"
              >
                Delete brand
              </Button>
            )}
            <Button type="submit" form="brand-kit-form" variant="primary" isLoading={isSaving}>
              {isCreatingNew ? 'Create brand' : 'Save changes'}
            </Button>
          </div>
        }
      />

      <div className="flex flex-1 min-h-0 w-full">

        {/* ── Brand selector sidebar ───────────────────────────────────── */}
        <aside className="hidden md:flex flex-col w-56 lg:w-64 shrink-0 border-r border-border/60 bg-surface/40 px-3 py-4 gap-1 overflow-y-auto">
          <div className="flex items-center justify-between px-1 mb-2">
            <p className="text-[10px] font-bold uppercase tracking-widest text-muted">Your Brands</p>
            <span className="text-[10px] font-semibold bg-accent/10 text-accent px-1.5 py-0.5 rounded-full">
              {brands.length}
            </span>
          </div>

          {brands.map((b) => (
            <BrandListItem
              key={b.id}
              brand={b}
              active={b.id === activeBrandId && !isCreatingNew}
              onClick={() => void loadBrand(b)}
            />
          ))}

          <div className="mt-2 pt-2 border-t border-border/50">
            <button
              type="button"
              onClick={handleNewBrand}
              className={cn(
                'w-full flex items-center gap-2 px-3 py-2.5 rounded-xl text-sm font-semibold transition-all border',
                isCreatingNew
                  ? 'bg-accent/10 border-accent/30 text-accent'
                  : 'border-dashed border-border/60 text-muted hover:border-accent/40 hover:text-accent hover:bg-accent/5'
              )}
            >
              <span className="text-lg leading-none">+</span>
              {isCreatingNew ? 'New brand (unsaved)' : 'Add new brand'}
            </button>
          </div>
        </aside>

        {/* ── Mobile brand picker (horizontal scroll) ──────────────────── */}
        <div className="md:hidden flex gap-2 px-4 py-2 overflow-x-auto border-b border-border/60 bg-surface/40 shrink-0">
          {brands.map((b) => (
            <button
              key={b.id}
              type="button"
              onClick={() => void loadBrand(b)}
              className={cn(
                'shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all whitespace-nowrap',
                b.id === activeBrandId && !isCreatingNew
                  ? 'bg-accent text-white border-accent'
                  : 'bg-surface border-border text-charcoal'
              )}
            >
              {b.name}
            </button>
          ))}
          <button
            type="button"
            onClick={handleNewBrand}
            className={cn(
              'shrink-0 px-3 py-1.5 rounded-full text-xs font-semibold border transition-all whitespace-nowrap',
              isCreatingNew
                ? 'bg-accent text-white border-accent'
                : 'border-dashed border-border text-muted'
            )}
          >
            + Add brand
          </button>
        </div>

        {/* ── Main form area ───────────────────────────────────────────── */}
        <form
          id="brand-kit-form"
          onSubmit={handleSubmit(onSubmit)}
          className="flex-1 min-w-0 overflow-y-auto px-6 md:px-8 lg:px-10 py-6 md:py-8 space-y-8"
        >
          {/* Creating-new banner */}
          {isCreatingNew && (
            <div className="rounded-xl bg-accent/8 border border-accent/25 px-4 py-3 flex items-center gap-3">
              <span className="text-accent text-lg">✦</span>
              <p className="text-sm text-charcoal">
                <strong>Creating a new brand.</strong> Fill in the details below and click <strong>Create brand</strong> to save.
              </p>
            </div>
          )}

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
                    Target industries for each campaign are set when you create a brief.
                  </p>
                </div>
              </SectionBlock>

              <SectionBlock
                step="04"
                title="Logos"
                description="Burned onto every generated creative: light mark on dark areas, dark mark on bright corners (auto-detected)."
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
                    disabled={!activeBrand}
                    disabledHint={!activeBrand ? 'Save brand first' : undefined}
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
                    disabled={!activeBrand}
                    disabledHint={!activeBrand ? 'Save brand first' : undefined}
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
              {isCreatingNew ? 'Create brand' : 'Save changes'}
            </Button>
          </div>
        </form>
      </div>
    </div>
  )
}
