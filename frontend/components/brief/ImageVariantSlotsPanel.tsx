'use client'

import React, { useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import { assetsApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { assetUrl } from '@/lib/utils'
import {
  downloadAllImageVariantsExcel,
  downloadImageVariantExcel,
  type ImageVariantExportContext,
} from '@/lib/exportImageVariantExcel'
import {
  IMAGE_ASPECT_RATIO_OPTIONS,
  IMAGE_USE_CASES,
  IMAGE_USE_CASE_GROUPS,
  PRODUCT_FOCUS_OPTIONS,
  effectiveVariantAspectRatio,
  isCarouselSlot,
  isLastCarouselCard,
  labelForUseCase,
  MAX_VARIANT_REFERENCE_IMAGES,
  normalizeProductFocus,
  productFocusSlotHint,
  variantReferenceImages,
  type ImageVariantSlot,
  type ProductFocusId,
  type VariantReferenceImage,
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
  /** OpenRouter LLM for variant prompt generation. */
  promptLlmModel?: string
  onPromptLlmModelChange?: (value: string) => void
  promptLlmOptions?: { value: string; label: string }[]
  promptLlmGroups?: { label: string; options: { value: string; label: string }[] }[]
  /** Campaign-level image ratio — used when a variant has no override. */
  defaultAspectRatio?: string
  /** Brand id for optional per-variant reference image upload. */
  brandId?: string
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
  promptLlmModel = '',
  onPromptLlmModelChange,
  promptLlmOptions = [],
  promptLlmGroups,
  defaultAspectRatio = '1:1',
  brandId,
}: Props) {
  const [openPicker, setOpenPicker] = useState<number | null>(null)
  const [editingSlots, setEditingSlots] = useState<Set<number>>(() => new Set(slots.map((_, i) => i)))
  const [uploadingRefIndex, setUploadingRefIndex] = useState<number | null>(null)
  const fileInputRefs = useRef<Record<number, HTMLInputElement | null>>({})
  const hasCarousel = slots.some((s) => isCarouselSlot(s, formats))

  const prevSlotCount = useRef(slots.length)
  useEffect(() => {
    if (slots.length > prevSlotCount.current) {
      setEditingSlots((prev) => {
        const next = new Set(prev)
        for (let i = prevSlotCount.current; i < slots.length; i++) next.add(i)
        return next
      })
    } else if (slots.length < prevSlotCount.current) {
      setEditingSlots((prev) => new Set(Array.from(prev).filter((i) => i < slots.length)))
    }
    prevSlotCount.current = slots.length
  }, [slots.length])

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

  const toggleEditing = (index: number) => {
    setEditingSlots((prev) => {
      const next = new Set(prev)
      if (next.has(index)) next.delete(index)
      else next.add(index)
      return next
    })
  }

  const handleReferenceUpload = async (index: number, files: FileList | File[]) => {
    if (!brandId) {
      toast.error('Select a brand before uploading reference images')
      return
    }
    const slot = slots[index]
    if (!slot) return
    const existing = variantReferenceImages(slot)
    const fileList = Array.from(files)
    const remaining = MAX_VARIANT_REFERENCE_IMAGES - existing.length
    if (remaining <= 0) {
      toast.error(`Maximum ${MAX_VARIANT_REFERENCE_IMAGES} reference images per variant`)
      return
    }
    const toUpload = fileList.slice(0, remaining)
    if (fileList.length > remaining) {
      toast(`Only ${remaining} more image${remaining === 1 ? '' : 's'} allowed — uploading first ${remaining}`, {
        icon: 'ℹ️',
      })
    }
    setUploadingRefIndex(index)
    try {
      const uploaded: VariantReferenceImage[] = []
      for (const file of toUpload) {
        const asset = await assetsApi.upload(file, undefined, 'reference_image', brandId)
        uploaded.push({ file_url: asset.file_url, asset_id: asset.id })
      }
      const nextRefs = [...existing, ...uploaded]
      updateSlot(index, {
        reference_images: nextRefs,
        reference_image_url: undefined,
        reference_image_asset_id: undefined,
      })
      toast.success(
        `${uploaded.length} reference image${uploaded.length === 1 ? '' : 's'} added to variant ${index + 1}`,
      )
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Could not upload reference image'))
    } finally {
      setUploadingRefIndex(null)
    }
  }

  const removeReferenceImage = (index: number, refIndex: number) => {
    const slot = slots[index]
    if (!slot) return
    const nextRefs = variantReferenceImages(slot).filter((_, i) => i !== refIndex)
    updateSlot(index, {
      reference_images: nextRefs.length ? nextRefs : undefined,
      reference_image_url: undefined,
      reference_image_asset_id: undefined,
    })
  }

  const clearReferenceImages = (index: number) => {
    updateSlot(index, {
      reference_images: undefined,
      reference_image_url: undefined,
      reference_image_asset_id: undefined,
    })
  }

  return (
    <div className="space-y-4">
      <div className="rounded-xl border border-sky-200 bg-sky-50 px-4 py-3 space-y-4">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div className="min-w-0 flex-1">
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

          <div className="w-full lg:w-auto lg:min-w-[min(100%,42rem)]">
            <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)_auto_auto] gap-x-3 gap-y-3 xl:items-end">
              <div className="flex flex-col gap-1 min-w-0">
                <label
                  htmlFor="variant-shot-style"
                  className="text-[9px] font-bold uppercase tracking-widest text-navy leading-none min-h-[11px]"
                >
                  Default shot style (override all)
                </label>
                <select
                  id="variant-shot-style"
                  value={productFocus || ''}
                  onChange={(e) =>
                    onProductFocusChange?.(e.target.value as ProductFocusId | '')
                  }
                  className="h-9 w-full rounded-lg border border-sky-400 bg-white px-2.5 text-xs font-semibold text-charcoal"
                >
                  {PRODUCT_FOCUS_OPTIONS.map((opt) => (
                    <option key={opt.value || 'auto'} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex flex-col gap-1 min-w-0">
                <label
                  htmlFor="variant-prompt-llm"
                  className="text-[9px] font-bold uppercase tracking-widest text-navy leading-none min-h-[11px]"
                >
                  Prompt LLM (OpenRouter)
                </label>
                <select
                  id="variant-prompt-llm"
                  value={promptLlmModel}
                  onChange={(e) => onPromptLlmModelChange?.(e.target.value)}
                  disabled={Boolean(generatingAll) || generatingIndex != null}
                  className="h-9 w-full rounded-lg border border-sky-400 bg-white px-2.5 text-xs font-semibold text-charcoal disabled:opacity-60"
                >
                  {promptLlmGroups?.length
                    ? promptLlmGroups.map((group) => (
                        <optgroup key={group.label} label={group.label}>
                          {group.options.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </optgroup>
                      ))
                    : promptLlmOptions.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                </select>
              </div>

              <div className="flex flex-col gap-1 sm:col-span-1 xl:col-span-1">
                <span
                  className="text-[9px] font-bold uppercase tracking-widest text-transparent select-none leading-none min-h-[11px] hidden xl:block"
                  aria-hidden="true"
                >
                  Actions
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={generatingIndex != null || Boolean(generatingAll)}
                  onClick={handleDownloadAll}
                  className="h-9 w-full xl:w-auto whitespace-nowrap rounded-lg px-3.5"
                >
                  Download all Excel
                </Button>
              </div>

              <div className="flex flex-col gap-1 sm:col-span-1 xl:col-span-1">
                <span
                  className="text-[9px] font-bold uppercase tracking-widest text-transparent select-none leading-none min-h-[11px] hidden xl:block"
                  aria-hidden="true"
                >
                  Actions
                </span>
                <Button
                  type="button"
                  size="sm"
                  variant="primary"
                  isLoading={Boolean(generatingAll)}
                  disabled={generatingIndex != null}
                  onClick={() => onGenerateAll()}
                  className="h-9 w-full xl:w-auto whitespace-nowrap rounded-lg px-3.5"
                >
                  Generate AI for all
                </Button>
              </div>
            </div>
          </div>
        </div>
      </div>
      {productFocus ? (
        <p className="text-[10px] text-sky-800 -mt-2">
          Override active — all variants will use this shot style unless a slot has its own selection.
        </p>
      ) : (
        <p className="text-[10px] text-mid -mt-2">
          Auto — AI picks shot style per variant. Choose a prompt LLM above (default: Claude Sonnet).
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
        const isEditing = editingSlots.has(index)
        const effectiveRatio = effectiveVariantAspectRatio(slot, defaultAspectRatio)
        const slotReferenceImages = variantReferenceImages(slot)
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
                {(() => {
                  const eff = slot.product_focus || productFocus || ''
                  if (eff === 'product_only') {
                    return (
                      <span className="ml-2 text-[10px] font-semibold text-sky-700 normal-case">
                        Catalog hero
                      </span>
                    )
                  }
                  if (eff === 'product_with_person') {
                    return (
                      <span className="ml-2 text-[10px] font-semibold text-teal-700 normal-case">
                        Product + person
                      </span>
                    )
                  }
                  if (eff === 'with_person') {
                    return (
                      <span className="ml-2 text-[10px] font-semibold text-violet-700 normal-case">
                        Person-led
                      </span>
                    )
                  }
                  if (slot.ad_angle) {
                    return (
                      <span className="ml-2 text-[10px] font-semibold text-accent normal-case">
                        {labelForAngle(slot.ad_angle, angleOptions)}
                      </span>
                    )
                  }
                  return null
                })()}
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
                  variant={isEditing ? 'outline' : 'primary'}
                  onClick={() => toggleEditing(index)}
                >
                  {isEditing ? 'Done' : 'Edit'}
                </Button>
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

            {!isEditing ? (
              <div className="rounded-xl border border-border/80 bg-white/70 px-3 py-2.5 space-y-2">
                <p className="text-sm text-charcoal line-clamp-2">
                  {slot.hook.trim() || slot.message.trim()
                    ? `${slot.hook.trim() || '—'} · ${slot.message.trim() || '—'}`
                    : 'No hook/headline yet — click Edit or Generate AI plan'}
                </p>
                <div className="flex flex-wrap items-center gap-2 text-[10px] text-mid">
                  <span>
                    Ratio: <strong className="text-charcoal">{effectiveRatio}</strong>
                    {slot.aspect_ratio_custom?.trim()
                      ? ' (custom)'
                      : slot.aspect_ratio?.trim()
                        ? ' (preset)'
                        : ' (campaign default)'}
                  </span>
                  {slotReferenceImages.length > 0 ? (
                    <span className="inline-flex items-center gap-1.5">
                      {slotReferenceImages.slice(0, 3).map((ref, ri) => {
                        const preview = assetUrl(ref.file_url)
                        return preview ? (
                          <img
                            key={`${ref.file_url}-${ri}`}
                            src={preview}
                            alt=""
                            className="h-8 w-8 rounded object-cover border border-border"
                          />
                        ) : null
                      })}
                      {slotReferenceImages.length} reference image
                      {slotReferenceImages.length !== 1 ? 's' : ''}
                    </span>
                  ) : null}
                </div>
              </div>
            ) : null}

            {isEditing ? (
            <>
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

            {/* Per-slot shot style — overrides the global default for this variant */}
            <div>
              <label className="block text-[10px] font-bold text-navy uppercase tracking-wide mb-1">
                Shot style (this variant)
              </label>
              <div className="flex items-center gap-2 flex-wrap">
                {PRODUCT_FOCUS_OPTIONS.map((opt) => {
                  const slotFocus = slot.product_focus ?? ''
                  const effectiveFocus = slotFocus !== '' ? slotFocus : (productFocus || '')
                  const isSlotSet = slotFocus !== ''
                  const isSelected = isSlotSet ? slotFocus === opt.value : (!productFocus && opt.value === '')
                  return (
                    <button
                      key={opt.value || 'auto'}
                      type="button"
                      onClick={() =>
                        updateSlot(index, {
                          product_focus: opt.value === '' && !productFocus
                            ? ''
                            : normalizeProductFocus(opt.value) || '',
                        })
                      }
                      className={`text-[10px] font-semibold px-2.5 py-1 rounded-full border transition-colors ${
                        isSelected
                          ? 'bg-sky-600 text-white border-sky-600'
                          : 'bg-white text-charcoal border-border hover:border-sky-400'
                      }`}
                    >
                      {opt.value === '' ? 'Auto' : opt.label.split(' — ')[0].split(' / ')[0].split(' +')[0]}
                    </button>
                  )
                })}
                {slot.product_focus ? (
                  <button
                    type="button"
                    onClick={() => updateSlot(index, { product_focus: '' })}
                    className="text-[10px] text-mid underline hover:text-charcoal"
                  >
                    Reset to default
                  </button>
                ) : null}
              </div>
              {(() => {
                const hint = productFocusSlotHint(
                  slot.product_focus || productFocus || ''
                )
                return hint ? (
                  <p className="mt-1 text-[10px] text-sky-700 italic">{hint}</p>
                ) : null
              })()}
            </div>

            <div>
              <label className="block text-[10px] font-bold text-navy uppercase tracking-wide mb-1">
                Ratio (this variant)
              </label>
              <select
                value={slot.aspect_ratio || ''}
                onChange={(e) =>
                  updateSlot(index, { aspect_ratio: e.target.value.trim() || undefined })
                }
                className="w-full rounded-lg border border-border bg-white px-3 py-2 text-sm text-charcoal"
              >
                <option value="">
                  Use campaign default ({defaultAspectRatio})
                </option>
                {IMAGE_ASPECT_RATIO_OPTIONS.map((opt) => (
                  <option key={opt.id} value={opt.id}>
                    {opt.label} — {opt.desc}
                  </option>
                ))}
              </select>
              <div className="mt-2 flex items-center gap-2">
                <label className="text-[10px] font-semibold text-navy shrink-0">
                  Custom ratio (optional):
                </label>
                <input
                  type="text"
                  placeholder="e.g. 3:4 or 1200x628"
                  value={slot.aspect_ratio_custom || ''}
                  onChange={(e) =>
                    updateSlot(index, {
                      aspect_ratio_custom: e.target.value.trim() || undefined,
                    })
                  }
                  className={`flex-1 rounded-lg border px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40 ${
                    slot.aspect_ratio_custom?.trim()
                      ? 'border-accent bg-accent/5'
                      : 'border-border bg-white'
                  }`}
                />
                {slot.aspect_ratio_custom?.trim() ? (
                  <button
                    type="button"
                    onClick={() => updateSlot(index, { aspect_ratio_custom: undefined })}
                    className="text-[10px] text-mid underline hover:text-charcoal shrink-0"
                  >
                    Clear
                  </button>
                ) : null}
              </div>
              <p className="mt-1 text-[10px] text-mid">
                Effective:{' '}
                <strong className="text-charcoal">{effectiveRatio}</strong>
                {slot.aspect_ratio_custom?.trim()
                  ? ' (custom override)'
                  : slot.aspect_ratio?.trim()
                    ? ' (preset override)'
                    : ' (campaign default)'}
              </p>
            </div>

            <div>
              <label className="block text-[10px] font-bold text-navy uppercase tracking-wide mb-1.5">
                Reference images (optional)
              </label>
              <p className="text-[10px] text-mid mb-2">
                Up to {MAX_VARIANT_REFERENCE_IMAGES} style or product references for this variant — merged
                with campaign references at generation time.
              </p>
              {slotReferenceImages.length > 0 ? (
                <div className="flex flex-wrap gap-2 mb-2">
                  {slotReferenceImages.map((ref, refIndex) => {
                    const preview = assetUrl(ref.file_url)
                    return (
                      <div key={`${ref.file_url}-${refIndex}`} className="relative group">
                        {preview ? (
                          <img
                            src={preview}
                            alt={`Reference ${refIndex + 1}`}
                            className="h-20 w-20 rounded-lg object-cover border border-border"
                          />
                        ) : (
                          <div className="h-20 w-20 rounded-lg border border-border bg-surface flex items-center justify-center text-[10px] text-mid px-1 text-center">
                            Image {refIndex + 1}
                          </div>
                        )}
                        <button
                          type="button"
                          onClick={() => removeReferenceImage(index, refIndex)}
                          className="absolute -top-1.5 -right-1.5 h-5 w-5 rounded-full bg-charcoal text-white text-xs leading-none opacity-90 hover:opacity-100"
                          title="Remove"
                        >
                          ×
                        </button>
                      </div>
                    )
                  })}
                </div>
              ) : null}
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  onClick={() => fileInputRefs.current[index]?.click()}
                  disabled={
                    uploadingRefIndex === index ||
                    !brandId ||
                    slotReferenceImages.length >= MAX_VARIANT_REFERENCE_IMAGES
                  }
                  isLoading={uploadingRefIndex === index}
                >
                  {slotReferenceImages.length
                    ? 'Add more reference images'
                    : 'Upload reference images'}
                </Button>
                {slotReferenceImages.length > 0 ? (
                  <button
                    type="button"
                    onClick={() => clearReferenceImages(index)}
                    className="text-[11px] text-mid underline hover:text-charcoal"
                  >
                    Remove all
                  </button>
                ) : null}
              </div>
              {slotReferenceImages.length > 0 ? (
                <p className="mt-1 text-[10px] text-mid">
                  {slotReferenceImages.length}/{MAX_VARIANT_REFERENCE_IMAGES} uploaded
                </p>
              ) : null}
              {!brandId ? (
                <p className="mt-1 text-[10px] text-amber-700">
                  Select a brand in step 2 to enable uploads.
                </p>
              ) : null}
              <input
                ref={(el) => {
                  fileInputRefs.current[index] = el
                }}
                type="file"
                accept="image/*"
                multiple
                className="hidden"
                onChange={(e) => {
                  const files = e.target.files
                  if (files?.length) void handleReferenceUpload(index, files)
                  e.target.value = ''
                }}
              />
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
            </>
            ) : null}
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
