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
  labelForUseCase,
  type ImageVariantSlot,
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
  angleOptions?: CatalogOption[]
  exportContext?: ImageVariantExportContext
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
  angleOptions,
  exportContext,
}: Props) {
  const [openPicker, setOpenPicker] = useState<number | null>(null)

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
            Plans are built from your <strong>industry</strong>, <strong>niche</strong>, and{' '}
            <strong>brand</strong> (ICP + HALO). Each variant gets its own ad angle, use case, hook,
            message, CTA, and prompt. Change <strong>Target Variants</strong> in step 1 to add or
            remove slots.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2 shrink-0">
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

      <div className="rounded-xl border border-border bg-white px-4 py-3">
        <Input
          label="Offer"
          placeholder="e.g. Free Meta ads audit this week"
          value={campaignOffer}
          onChange={(e) => onCampaignOfferChange?.(e.target.value)}
        />
        <p className="text-[10px] text-mid mt-1">
          Used when generating AI plans — each variant can also have its own offer below.
        </p>
      </div>

      {slots.map((slot, index) => {
        const busy = generatingIndex === index || Boolean(generatingAll)
        const pickerOpen = openPicker === index
        return (
          <div key={index} className="space-y-1">
          <div
            className="rounded-2xl border-2 border-border bg-surface p-4 space-y-3 shadow-sm"
          >
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-bold text-navy">
                Variant {index + 1}
                {slot.ad_angle ? (
                  <span className="ml-2 text-[10px] font-semibold text-accent normal-case">
                    {labelForAngle(slot.ad_angle, angleOptions)}
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

            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              <Input
                label="Hook on image"
                placeholder="e.g. Is your Meta spend leaking?"
                value={slot.hook}
                onChange={(e) => updateSlot(index, { hook: e.target.value })}
              />
              <Input
                label="Message / headline on image"
                placeholder="e.g. Free Meta ads audit this week"
                value={slot.message}
                onChange={(e) => updateSlot(index, { message: e.target.value })}
              />
            </div>
            <Input
              label="CTA on image (this variant)"
              placeholder="e.g. Book Consultation, Get Free Audit, Claim Pilot"
              value={slot.cta}
              onChange={(e) => updateSlot(index, { cta: e.target.value })}
            />
            <p className="text-[10px] text-mid -mt-1">
              Hook, headline, and CTA are burned into this variant&apos;s image only — each variant
              should use a different CTA when it fits the angle.
            </p>

            <Input
              label="Offer (caption)"
              placeholder="e.g. I’m tired of guessing. I want proof that this actually works. Claim the free review and get next steps."
              value={slot.offer}
              onChange={(e) => updateSlot(index, { offer: e.target.value })}
            />

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
