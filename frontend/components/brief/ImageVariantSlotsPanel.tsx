'use client'

import React, { useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import {
  downloadAllImageVariantsExcel,
  downloadImageVariantExcel,
  type ImageVariantExportContext,
} from '@/lib/exportImageVariantExcel'
import {
  IMAGE_USE_CASES,
  IMAGE_USE_CASE_GROUPS,
  PRODUCT_FOCUS_OPTIONS,
  isCarouselSlot,
  isLastCarouselCard,
  labelForUseCase,
  type ImageVariantSlot,
  type ProductFocusId,
} from '@/lib/imageUseCases'
import { labelForAngle } from '@/lib/adAngles'
import type { CatalogOption } from '@/types'

type Props = {
  slots: ImageVariantSlot[]
  onChange(slots: ImageVariantSlot[]): void
  generatingIndex: number | null
  onGenerateSlot(index: number): void
  onGenerateAll(): void
  generatingAll?: boolean
  campaignOffer?: string
  onCampaignOfferChange?: (value: string) => void
  campaignHook?: string
  campaignHeadline?: string
  campaignCta?: string
  onCampaignHookChange?: (value: string) => void
  onCampaignHeadlineChange?: (value: string) => void
  onCampaignCtaChange?: (value: string) => void
  formats?: string[]
  angleOptions?: CatalogOption[]
  exportContext?: ImageVariantExportContext
  /** Product/model names scraped from brand website — optional picker per variant. */
  catalogProducts?: string[]
  /** Campaign-level shot style — applies to every variant when generating. */
  productFocus?: ProductFocusId | ''
  onProductFocusChange?: (value: ProductFocusId | '') => void
}

function formatGenerationTime(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: 'medium',
      timeStyle: 'short',
    })
  } catch {
    return iso
  }
}

export default function ImageVariantSlotsPanel({
  slots,
  onChange,
  generatingIndex,
  onGenerateSlot,
  onGenerateAll,
  generatingAll,
  campaignOffer = '',
  onCampaignOfferChange,
  campaignHook = '',
  campaignHeadline = '',
  campaignCta = '',
  onCampaignHookChange,
  onCampaignHeadlineChange,
  onCampaignCtaChange,
  formats,
  angleOptions,
  exportContext,
  catalogProducts = [],
  productFocus = '',
  onProductFocusChange,
}: Props) {
  const [openPicker, setOpenPicker] = useState<number | null>(null)
  const hasCarousel = slots.some((s) => isCarouselSlot(s, formats))

  const hasVariantContent = (slot: ImageVariantSlot) =>
    Boolean(slot.hook.trim() || slot.message.trim() || slot.prompt.trim())

  const handleDownloadVariant = (index: number) => {
    const slot = slots[index]
    if (!slot || !hasVariantContent(slot)) {
      toast.error('Generate or fill in this variant before downloading.')
      return
    }
    downloadImageVariantExcel(slot, index, exportContext)
    toast.success(`Variant ${index + 1} downloaded (.xlsx)`)
  }

  const handleDownloadAll = () => {
    const filled = slots.filter(hasVariantContent)
    if (filled.length === 0) {
      toast.error('Generate or fill in at least one variant before downloading.')
      return
    }
    downloadAllImageVariantsExcel(slots, exportContext)
    toast.success(`${slots.length} variant${slots.length !== 1 ? 's' : ''} downloaded (.xlsx)`)
  }

  const updateSlot = (index: number, patch: Partial<ImageVariantSlot>) => {
    onChange(slots.map((s, i) => (i === index ? { ...s, ...patch } : s)))
  }

  const toggleUseCase = (index: number, id: string) => {
    const slot = slots[index]
    if (!slot) return
    const on = slot.use_cases.includes(id)
    updateSlot(index, {
      use_cases: on ? slot.use_cases.filter((x) => x !== id) : [...slot.use_cases, id],
    })
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="text-sm font-bold text-sky-900">
            {slots.length} image variant{slots.length !== 1 ? 's' : ''}
          </p>
          <p className="text-[11px] text-sky-800 mt-0.5 leading-relaxed max-w-xl">
            Slots stay empty until you click <strong>Generate AI for all</strong>. Static ads get
            hook + on-image CTA. Carousel cards are visual + short headline; the campaign CTA
            burns on the last card of each creative. Change <strong>Target Variants</strong> in step 1
            to add or remove slots.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
          <div className="flex flex-col gap-0.5 min-w-[220px]">
            <label className="text-[9px] font-bold uppercase tracking-widest text-navy">
              Shot style (all variants)
            </label>
            <select
              value={productFocus || ''}
              onChange={(e) =>
                onProductFocusChange?.(e.target.value as ProductFocusId | '')
              }
              className="rounded-lg border border-sky-400 bg-white px-2.5 py-1.5 text-xs font-semibold text-charcoal"
            >
              {PRODUCT_FOCUS_OPTIONS.map((opt) => (
                <option key={opt.value || 'auto'} value={opt.value}>
                  {opt.label}
                </option>
              ))}
            </select>
          </div>
          <Button
            type="button"
            size="sm"
            variant="outline"
            disabled={generatingIndex != null || Boolean(generatingAll)}
            onClick={handleDownloadAll}
          >
            Download all Excel
          </Button>
          <Button
            type="button"
            size="sm"
            variant="primary"
            isLoading={Boolean(generatingAll)}
            disabled={generatingIndex != null}
            onClick={() => onGenerateAll()}
          >
            Generate AI for all
          </Button>
        </div>
      </div>
      {productFocus ? (
        <p className="text-[10px] text-sky-800 -mt-2">
          {PRODUCT_FOCUS_OPTIONS.find((o) => o.value === productFocus)?.label ===
          'Product alone — catalog / studio hero'
            ? 'Every variant: product-only catalog hero — no people in frame.'
            : productFocus === 'with_person'
              ? 'Every variant: person/model with the product (e.g. kid on bike).'
              : null}
        </p>
      ) : (
        <p className="text-[10px] text-mid -mt-2">
          Shot style Auto — AI picks product-only vs with-person per variant.
        </p>
      )}

      <div className="rounded-xl border border-border bg-white px-4 py-3 space-y-3">
        {hasCarousel ? (
          <>
            <p className="text-xs font-bold text-navy uppercase tracking-wide">
              Carousel ad (campaign-level)
            </p>
            <p className="text-[11px] text-mid -mt-2">
              One story, one CTA. Cards below are visuals + short headlines — the CTA button
              burns on the last swipe card only.
            </p>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input
                label="Overall hook"
                placeholder="e.g. What happens at an Adoria consultation?"
                value={campaignHook}
                onChange={(e) => onCampaignHookChange?.(e.target.value)}
              />
              <Input
                label="Overall headline"
                placeholder="e.g. Four steps to a ring that feels hers"
                value={campaignHeadline}
                onChange={(e) => onCampaignHeadlineChange?.(e.target.value)}
              />
            </div>
            <Input
              label="Offer"
              placeholder="e.g. Free design consultation"
              value={campaignOffer}
              onChange={(e) => onCampaignOfferChange?.(e.target.value)}
            />
            <Input
              label="CTA (burned on the last card)"
              placeholder="e.g. Book a Consultation"
              value={campaignCta}
              onChange={(e) => onCampaignCtaChange?.(e.target.value)}
            />
          </>
        ) : (
          <>
            <Input
              label="Offer"
              placeholder="e.g. Free Meta ads audit this week"
              value={campaignOffer}
              onChange={(e) => onCampaignOfferChange?.(e.target.value)}
            />
            <p className="text-[10px] text-mid">
              Used when generating AI plans — each variant can also have its own offer below.
            </p>
          </>
        )}
      </div>

      {slots.map((slot, index) => {
        const busy = generatingIndex === index || Boolean(generatingAll)
        const pickerOpen = openPicker === index
        const carouselCard = isCarouselSlot(slot, formats)
        const lastCarousel = isLastCarouselCard(slot, index, slots, formats)
        return (
          <div key={index} className="space-y-1">
          <div
            className="rounded-2xl border-2 border-border bg-surface p-4 space-y-3 shadow-sm"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-bold text-navy">
                Variant {index + 1}
                {slot.format === 'carousel' && slot.carousel_total ? (
                  <span className="ml-2 text-[10px] font-semibold text-violet-700 normal-case">
                    {slot.carousel_group
                      ? `${slot.carousel_group.replace('creative-', 'Creative ')} · `
                      : ''}
                    Card {slot.carousel_index}/{slot.carousel_total}
                    {lastCarousel ? ' · CTA' : ''}
                  </span>
                ) : slot.format === 'carousel' ? (
                  <span className="ml-2 text-[10px] font-semibold text-violet-700 normal-case">
                    Carousel
                  </span>
                ) : slot.format === 'static' ? (
                  <span className="ml-2 text-[10px] font-semibold text-mid normal-case">
                    Static
                  </span>
                ) : null}
                {slot.ad_angle && productFocus !== 'product_only' ? (
                  <span className="ml-2 text-[10px] font-semibold text-accent normal-case">
                    {labelForAngle(slot.ad_angle, angleOptions)}
                  </span>
                ) : productFocus === 'product_only' ? (
                  <span className="ml-2 text-[10px] font-semibold text-sky-700 normal-case">
                    Catalog hero
                  </span>
                ) : null}
                {slot.prompt ? (
                  <span className="ml-2 text-teal-600 font-semibold text-[11px] normal-case">
                    ✓ Prompt ready
                  </span>
                ) : null}
              </p>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={busy || !hasVariantContent(slot)}
                  onClick={() => handleDownloadVariant(index)}
                >
                  Download Excel
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  isLoading={generatingIndex === index}
                  disabled={busy && generatingIndex !== index}
                  onClick={() => onGenerateSlot(index)}
                >
                  {slot.prompt ? 'Regenerate AI plan' : 'Generate AI plan'}
                </Button>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-[10px] font-bold text-navy uppercase tracking-wide">
                  Use case(s)
                </p>
                <button
                  type="button"
                  onClick={() => setOpenPicker(pickerOpen ? null : index)}
                  className="text-[11px] text-accent font-semibold underline"
                >
                  {pickerOpen ? 'Done' : 'Choose'}
                </button>
              </div>
              <div className="flex flex-wrap gap-1.5 min-h-[28px]">
                {slot.use_cases.length === 0 ? (
                  <p className="text-[11px] text-mid italic">
                    None yet — click Choose, or Generate AI plan
                  </p>
                ) : (
                  slot.use_cases.map((id) => (
                    <span
                      key={id}
                      className="inline-flex items-center gap-1 bg-violet-100 text-violet-800 text-[11px] font-semibold px-2.5 py-1 rounded-full border border-violet-300"
                    >
                      {labelForUseCase(id)}
                      <button
                        type="button"
                        onClick={() => toggleUseCase(index, id)}
                        className="ml-0.5 text-violet-400 hover:text-violet-700 font-bold leading-none"
                        title="Remove"
                      >
                        ×
                      </button>
                    </span>
                  ))
                )}
              </div>
              {pickerOpen && (
                <div className="mt-2 rounded-lg border border-violet-200 bg-white p-3 space-y-3">
                  {IMAGE_USE_CASE_GROUPS.map((group) => (
                    <div key={group}>
                      <p className="text-[9px] font-bold uppercase tracking-widest text-mid mb-1">
                        {group}
                      </p>
                      <div className="flex flex-wrap gap-1">
                        {IMAGE_USE_CASES.filter((u) => u.group === group).map((uc) => {
                          const on = slot.use_cases.includes(uc.id)
                          return (
                            <button
                              key={uc.id}
                              type="button"
                              onClick={() => toggleUseCase(index, uc.id)}
                              className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border transition-colors ${
                                on
                                  ? 'bg-violet-600 text-white border-violet-600'
                                  : 'bg-white text-charcoal border-border hover:border-violet-400'
                              }`}
                            >
                              {uc.label}
                            </button>
                          )
                        })}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div>
              <label className="block text-[10px] font-bold text-navy uppercase tracking-wide mb-1.5">
                Product / model (optional)
              </label>
              <input
                list={catalogProducts.length ? `product-models-${index}` : undefined}
                placeholder={
                  catalogProducts.length
                    ? 'Pick from site catalog or type a model name'
                    : 'e.g. NEO + 20 2026 — scrape website for suggestions'
                }
                value={slot.product_model || ''}
                onChange={(e) => updateSlot(index, { product_model: e.target.value })}
                className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-charcoal"
              />
              {catalogProducts.length > 0 ? (
                <datalist id={`product-models-${index}`}>
                  {catalogProducts.map((name) => (
                    <option key={name} value={name} />
                  ))}
                </datalist>
              ) : null}
            </div>

            {carouselCard ? (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input
                    label="Card headline (post)"
                    placeholder="e.g. Meet our jewellers"
                    value={slot.hook}
                    onChange={(e) => updateSlot(index, { hook: e.target.value })}
                  />
                  <Input
                    label="Card description (post)"
                    placeholder="e.g. Boutique welcome — the first step of the consult"
                    value={slot.message}
                    onChange={(e) => updateSlot(index, { message: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input
                    label="On-image hook (burned on photo)"
                    placeholder="e.g. Ready for something bespoke?"
                    value={slot.image_hook}
                    onChange={(e) => updateSlot(index, { image_hook: e.target.value })}
                  />
                  <Input
                    label="On-image headline (burned on photo)"
                    placeholder="e.g. Crafted for your story"
                    value={slot.image_headline}
                    onChange={(e) => updateSlot(index, { image_headline: e.target.value })}
                  />
                </div>
                {lastCarousel ? (
                  <Input
                    label="CTA on image (last card)"
                    placeholder="e.g. Book a Consultation"
                    value={slot.cta || campaignCta}
                    onChange={(e) => updateSlot(index, { cta: e.target.value })}
                  />
                ) : null}
                <p className="text-[10px] text-mid">
                  Every carousel card burns the on-image hook + headline onto the photo.
                  {lastCarousel
                    ? ' Last card also gets the CTA pill button.'
                    : ' No CTA button on this card — only on the last card of this creative.'}
                </p>
              </>
            ) : (
              <>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input
                    label="Hook (post — keep as is)"
                    placeholder="e.g. Your best clients are leaving for integrated solutions"
                    value={slot.hook}
                    onChange={(e) => updateSlot(index, { hook: e.target.value })}
                  />
                  <Input
                    label="Headline (post — keep as is)"
                    placeholder="e.g. Don't lose assets to firms offering lending + wealth together"
                    value={slot.message}
                    onChange={(e) => updateSlot(index, { message: e.target.value })}
                  />
                </div>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                  <Input
                    label="On-image hook (catchy, related)"
                    placeholder="e.g. Clients leaving for one-stop shops?"
                    value={slot.image_hook}
                    onChange={(e) => updateSlot(index, { image_hook: e.target.value })}
                  />
                  <Input
                    label="On-image headline (catchy, related)"
                    placeholder="e.g. Keep lending + wealth together"
                    value={slot.image_headline}
                    onChange={(e) => updateSlot(index, { image_headline: e.target.value })}
                  />
                </div>
                <Input
                  label="CTA on image (this variant)"
                  placeholder="e.g. Book Consultation, Get Free Audit, Claim Pilot"
                  value={slot.cta}
                  onChange={(e) => updateSlot(index, { cta: e.target.value })}
                />
                <p className="text-[10px] text-mid -mt-1">
                  Hook &amp; headline stay full for the post. On-image lines must be complete
                  phrases (never cut off on &quot;your / at / the&quot;).
                </p>
                <Input
                  label="Offer (caption / feed — not on image)"
                  placeholder="e.g. I’m tired of guessing. I want proof that this actually works. Claim the free review and get next steps."
                  value={slot.offer}
                  onChange={(e) => updateSlot(index, { offer: e.target.value })}
                />
              </>
            )}

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <p className="text-xs font-bold text-navy uppercase tracking-wide">
                  Image generation prompt
                </p>
                {slot.prompt ? (
                  <button
                    type="button"
                    onClick={() =>
                      updateSlot(index, { prompt: '', reasoning: '', generated_at: null })
                    }
                    className="text-[11px] text-mid underline hover:text-charcoal"
                  >
                    Clear
                  </button>
                ) : null}
              </div>
              <textarea
                rows={10}
                value={slot.prompt}
                onChange={(e) => updateSlot(index, { prompt: e.target.value })}
                placeholder="Describe the unique scene for this variant — lighting, subject, layout, and how the hook/message appear on the image…"
                className={`w-full min-h-[220px] rounded-xl border-2 px-4 py-3 text-sm text-charcoal placeholder:text-mid/50 focus:outline-none focus:ring-2 resize-y leading-relaxed transition-colors ${
                  slot.prompt
                    ? 'border-teal-400 bg-teal-50/30 focus:border-teal-500 focus:ring-teal-200'
                    : 'border-border bg-white focus:border-accent focus:ring-accent/20'
                }`}
              />
              {slot.reasoning ? (
                <p className="mt-1.5 text-[11px] text-violet-700 italic bg-violet-50/60 rounded-lg px-3 py-2">
                  &ldquo;{slot.reasoning}&rdquo;
                </p>
              ) : null}
            </div>
          </div>
          {slot.generated_at ? (
            <p className="text-[10px] text-mid text-right px-1">
              Generated {formatGenerationTime(slot.generated_at)}
            </p>
          ) : null}
          </div>
        )
      })}
    </div>
  )
}
