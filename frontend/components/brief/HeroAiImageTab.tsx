'use client'

import React, { useEffect, useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import { generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { assetUrl } from '@/lib/utils'
import { variantsApi } from '@/lib/api'
import type { Brand } from '@/types'

type Props = {
  brandName?: string
  industry?: string
  niche?: string
  productName?: string
  imageModel?: string
  brandId?: string
  brands?: Brand[]
  onBrandChange?: (brandId: string) => void
  logoUrl?: string | null
  logoOnLightUrl?: string | null
  briefTitle?: string
}

export default function HeroAiImageTab({
  brandName = '',
  industry = '',
  niche = '',
  productName = '',
  imageModel = 'openai-gpt-image-2',
  brandId = '',
  brands = [],
  onBrandChange,
  logoUrl,
  logoOnLightUrl,
  briefTitle = 'Hero AI Image',
}: Props) {
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const [hook, setHook] = useState('')
  const [headline, setHeadline] = useState('')
  const [heroIndustry, setHeroIndustry] = useState(industry)
  const [heroNiche, setHeroNiche] = useState(niche)
  const [brandSearch, setBrandSearch] = useState(brandName)
  const [busy, setBusy] = useState<'prompt' | 'image' | null>(null)
  const [saving, setSaving] = useState(false)
  const [prompt, setPrompt] = useState('')
  const [result, setResult] = useState<{ image_url: string; hook: string; headline: string; prompt: string } | null>(null)
  const matchingBrands = useMemo(() => {
    const query = brandSearch.trim().toLowerCase()
    if (!query) return []
    return brands.filter((brand) => brand.name.toLowerCase().includes(query))
  }, [brandSearch, brands])

  useEffect(() => {
    if (brandName) setBrandSearch(brandName)
  }, [brandName])

  const handleFile = (next: File | null) => {
    if (preview) URL.revokeObjectURL(preview)
    setFile(next)
    setPreview(next ? URL.createObjectURL(next) : '')
    setResult(null)
  }

  const generatePrompt = async () => {
    if (!file) {
      toast.error('Upload an image first')
      return
    }
    setBusy('prompt')
    try {
      const response = await generationApi.generateHeroAiImage(file, {
        brand_name: brandName,
        industry: heroIndustry,
        niche: heroNiche,
        product_name: productName,
        hook,
        headline,
        model: imageModel,
        logo_url: logoUrl || '',
        logo_on_light_url: logoOnLightUrl || '',
        generate_image: false,
      })
      setHook(response.hook)
      setHeadline(response.headline)
      setPrompt(response.prompt)
      setResult(null)
      toast.success('Prompt ready — review or edit the copy before generating')
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Could not generate Hero AI Image'))
    } finally {
      setBusy(null)
    }
  }

  const generateImage = async () => {
    if (!file) {
      toast.error('Upload an image first')
      return
    }
    if (!prompt.trim()) {
      toast.error('Generate the prompt first')
      return
    }
    setBusy('image')
    try {
      const response = await generationApi.generateHeroAiImage(file, {
        brand_name: brandName,
        industry: heroIndustry,
        niche: heroNiche,
        product_name: productName,
        hook,
        headline,
        model: imageModel,
        logo_url: logoUrl || '',
        logo_on_light_url: logoOnLightUrl || '',
        prompt,
        generate_image: true,
      })
      setHook(response.hook)
      setHeadline(response.headline)
      setPrompt(response.prompt)
      setResult(response)
      toast.success('Final Hero AI Image ready')
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Could not generate Hero AI Image'))
    } finally {
      setBusy(null)
    }
  }

  const saveToVariants = async () => {
    if (!result?.image_url || !brandId) {
      toast.error('Select a brand before saving to Variants')
      return
    }
    setSaving(true)
    try {
      await variantsApi.createFromMedia({
        media_url: result.image_url,
        media_mode: 'image',
        model: imageModel,
        prompt: `${result.hook}\n${result.headline}`,
        brand_id: brandId,
        brief_title: briefTitle,
        product_name: productName,
      })
      toast.success('Hero image saved to Variants')
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Could not save Hero image to Variants'))
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="w-full max-w-[1200px] mx-auto p-6 md:p-8 space-y-5">
      <div className="rounded-xl border border-accent/30 bg-accent/5 p-5 space-y-2">
        <h2 className="text-lg font-bold text-charcoal">Hero AI Image</h2>
        <p className="text-xs text-mid">
          Upload a product or hero image. AI uses your brand, industry, and niche to generate copy.
          Edit the copy before generating; GPT Image 2 renders the final hook and headline as part of the ad design.
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="lg:col-span-2 rounded-xl border border-border bg-white p-4 space-y-4">
          <p className="text-xs font-bold uppercase tracking-wide text-navy">Brand context</p>
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="relative text-xs text-mid">
              Brand
              <input
                value={brandSearch}
                onChange={(event) => {
                  const value = event.target.value
                  setBrandSearch(value)
                  if (value.trim().toLowerCase() !== brandName.trim().toLowerCase()) {
                    onBrandChange?.('')
                  }
                }}
                placeholder="Type brand name to search"
                className="mt-1 w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-charcoal"
              />
              {brandSearch.trim() &&
                matchingBrands.length > 0 &&
                (!brandId || brandSearch.trim().toLowerCase() !== brandName.trim().toLowerCase()) && (
                  <div className="absolute z-20 left-0 right-0 top-full mt-1 max-h-48 overflow-y-auto rounded-lg border border-border bg-white shadow-lg">
                    {matchingBrands.map((brand) => (
                      <button
                        key={brand.id}
                        type="button"
                        className="block w-full px-3 py-2 text-left text-sm text-charcoal hover:bg-accent/10"
                        onClick={() => {
                          setBrandSearch(brand.name)
                          onBrandChange?.(brand.id)
                        }}
                      >
                        {brand.name}
                      </button>
                    ))}
                  </div>
                )}
              {brandSearch.trim() && matchingBrands.length === 0 && !brandId && (
                <p className="mt-1 text-[11px] text-mid">No matching brand found.</p>
              )}
            </div>
            <label className="text-xs text-mid">
              Industry
              <input
                value={heroIndustry}
                onChange={(event) => setHeroIndustry(event.target.value)}
                placeholder="e.g. fitness, ecommerce, tailoring"
                className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
              />
            </label>
            <label className="text-xs text-mid">
              Niche
              <input
                value={heroNiche}
                onChange={(event) => setHeroNiche(event.target.value)}
                placeholder="e.g. boxing beginners, wedding couples"
                className="mt-1 w-full rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
              />
            </label>
          </div>
          <div className="flex items-center gap-3 text-xs text-mid">
            {logoUrl ? (
              <img src={assetUrl(logoUrl) || logoUrl} alt={`${brandName} logo`} className="h-10 max-w-32 object-contain rounded border border-border bg-white p-1" />
            ) : null}
            <span>
              {logoUrl
                ? `Brand Kit logo for ${brandName || 'selected brand'} will be composited into the final image.`
                : 'Select a brand with a Brand Kit logo to place the logo on the final image.'}
            </span>
          </div>
        </div>

        <div className="rounded-xl border border-border bg-white p-4 space-y-4">
          <label className="text-xs font-bold uppercase tracking-wide text-navy">
            Upload hero image
          </label>
          <input
            type="file"
            accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
            onChange={(event) => handleFile(event.target.files?.[0] || null)}
            className="block w-full text-xs text-mid file:mr-3 file:rounded-full file:border file:border-accent/40 file:bg-white file:px-3.5 file:py-2 file:text-xs file:font-semibold"
          />
          {preview && (
            <img src={preview} alt="Uploaded hero preview" className="w-full max-h-80 object-contain rounded-lg border border-border" />
          )}
          <p className="text-[11px] text-mid">
            Product image, service image, or campaign hero visual. The uploaded subject remains the primary visual source.
          </p>
        </div>

        <div className="rounded-xl border border-border bg-white p-4 space-y-4">
          <label className="block text-xs font-bold uppercase tracking-wide text-navy">
            On-image copy
          </label>
          <textarea
            value={hook}
            onChange={(event) => setHook(event.target.value)}
            placeholder="Hook — leave blank and AI will generate one from the image and brand"
            rows={3}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
          />
          <textarea
            value={headline}
            onChange={(event) => setHeadline(event.target.value)}
            placeholder="Headline — leave blank and AI will generate one from the image and brand"
            rows={3}
            className="w-full rounded-lg border border-border px-3 py-2 text-sm text-charcoal"
          />
          <Button type="button" variant="outline" isLoading={busy === 'prompt'} onClick={() => void generatePrompt()}>
            Generate Prompt First
          </Button>
          <Button
            type="button"
            variant="primary"
            isLoading={busy === 'image'}
            disabled={!prompt.trim() || busy !== null}
            onClick={() => void generateImage()}
          >
            Generate Final Image
          </Button>
          {prompt && (
            <div className="rounded-lg border border-sky-200 bg-sky-50 p-3">
              <p className="text-[10px] font-bold uppercase tracking-wide text-sky-900">Generated prompt</p>
              <p className="mt-1 whitespace-pre-wrap text-xs text-sky-950">{prompt}</p>
            </div>
          )}
        </div>
      </div>

      {result && (
        <div className="rounded-xl border border-accent/30 bg-white p-4 space-y-3">
          <p className="text-xs font-bold uppercase tracking-wide text-navy">Final image</p>
          <img src={assetUrl(result.image_url) || result.image_url} alt="Generated Hero AI Image" className="max-w-full rounded-lg border border-border" />
          <p className="text-xs text-mid">
            Hook: <strong>{result.hook}</strong>
            <br />
            Headline: <strong>{result.headline}</strong>
          </p>
          <Button type="button" variant="outline" isLoading={saving} onClick={() => void saveToVariants()}>
            Save to Variants
          </Button>
        </div>
      )}
    </div>
  )
}
