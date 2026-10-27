'use client'

import React, { useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { patchApiCache } from '@/lib/apiCache'
import {
  persistWebsiteBrandFromFetch,
  summarizeBrandFacts,
} from '@/lib/persistWebsiteBrandFetch'
import type { Brand, WebsiteBrandFetchResult } from '@/types'

type BrandSetupMode = 'manual' | 'website'

type WebsiteBrandFetchBlockProps = {
  brands: Brand[]
  industryOverride?: string
  onBrandSaved: (brand: Brand) => void | Promise<void>
}

export default function WebsiteBrandFetchBlock({
  brands,
  industryOverride,
  onBrandSaved,
}: WebsiteBrandFetchBlockProps) {
  const [mode, setMode] = useState<BrandSetupMode>('manual')
  const [websiteUrl, setWebsiteUrl] = useState('')
  const [fetching, setFetching] = useState(false)
  const [preview, setPreview] = useState<WebsiteBrandFetchResult | null>(null)

  const handleFetch = async () => {
    const url = websiteUrl.trim()
    if (url.length < 4) {
      toast.error('Enter a website URL first')
      return
    }
    setFetching(true)
    setPreview(null)
    try {
      const result = await generationApi.fetchBrandFromUrl({ url })
      setPreview(result)

      const { brand: savedBrand, created } = await persistWebsiteBrandFromFetch(result, url, {
        brands,
        industryOverride,
      })

      patchApiCache<Brand[]>('brands', (current) => {
        const prior = current ?? brands
        const idx = prior.findIndex((b) => b.id === savedBrand.id)
        if (idx >= 0) {
          const next = [...prior]
          next[idx] = { ...prior[idx], ...savedBrand }
          return next
        }
        return [...prior, savedBrand]
      })

      await onBrandSaved(savedBrand)
      setMode('manual')
      setPreview(null)
      setWebsiteUrl(result.source_url || url)

      toast.success(
        created ? `Saved to Brand Kit: ${savedBrand.name}` : `Updated Brand Kit: ${savedBrand.name}`
      )

      const factsSummary = summarizeBrandFacts(result.brand_facts)
      if (factsSummary) {
        toast.success(`Brand facts ready — ${factsSummary.slice(0, 120)}`)
      }
      if (result.warning) toast(result.warning, { icon: '⚠️' })
    } catch (err) {
      toast.error(extractApiError(err) || 'Could not fetch brand from website')
    } finally {
      setFetching(false)
    }
  }

  return (
    <div className="space-y-3 pb-2 border-b border-border/50">
      <p className="text-xs font-bold text-navy uppercase tracking-wide">Brand source</p>
      <div className="flex flex-wrap gap-2">
        {(
          [
            { id: 'manual' as const, label: 'Brand Kit' },
            { id: 'website' as const, label: 'Website URL' },
          ] as const
        ).map((opt) => (
          <button
            key={opt.id}
            type="button"
            onClick={() => setMode(opt.id)}
            className={`px-3.5 py-2 text-xs font-semibold rounded-full border transition-all ${
              mode === opt.id
                ? 'border-accent/50 bg-accent/10 text-charcoal'
                : 'border-border text-mid hover:border-accent/30'
            }`}
          >
            {opt.label}
          </button>
        ))}
      </div>

      {mode === 'website' ? (
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row gap-2 items-stretch sm:items-end">
            <div className="flex-1">
              <Input
                label="Website URL"
                placeholder="https://yourbrand.com"
                value={websiteUrl}
                onChange={(e) => setWebsiteUrl(e.target.value)}
              />
            </div>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="shrink-0 mb-0.5"
              isLoading={fetching}
              onClick={() => void handleFetch()}
            >
              Fetch brand
            </Button>
          </div>
          <p className="text-[11px] text-mid leading-relaxed">
            Fetches colours, logo, services, locations, reviews &amp; rates with Firecrawl, then saves
            into this Brand Kit (logo, palette, fonts, and verified facts for ACCC-safe copy).
          </p>
          {preview && (
            <div className="rounded-xl border border-accent/25 bg-accent/5 p-3 flex flex-wrap items-center gap-3">
              {preview.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={preview.logo_url}
                  alt={preview.brand_name}
                  className="h-10 w-10 object-contain rounded-lg bg-white border border-border"
                />
              ) : (
                <div className="h-10 w-10 rounded-lg bg-white border border-border" />
              )}
              <div className="min-w-0 flex-1">
                <p className="text-sm font-bold text-charcoal truncate">{preview.brand_name}</p>
                <p className="text-[11px] text-mid">Saving to Brand Kit…</p>
              </div>
              <div className="flex items-center gap-1.5">
                <span
                  className="w-6 h-6 rounded-full border border-border"
                  style={{ background: preview.primary_color }}
                  title="Primary"
                />
                <span
                  className="w-6 h-6 rounded-full border border-border"
                  style={{ background: preview.secondary_color }}
                  title="Secondary"
                />
              </div>
            </div>
          )}
        </div>
      ) : (
        <p className="text-[11px] text-mid">
          Edit the selected brand below, or switch to <strong>Website URL</strong> to import logo,
          colours, and facts from a site.
        </p>
      )}
    </div>
  )
}
