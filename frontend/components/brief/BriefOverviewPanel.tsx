'use client'

import React from 'react'
import Card from '@/components/ui/Card'
import { labelForAngle } from '@/lib/adAngles'
import { labelForUseCase } from '@/lib/imageUseCases'
import type { Brand, Brief, CatalogOption } from '@/types'

type ImageVariantStored = {
  use_cases?: string[]
  hook?: string
  message?: string
  image_hook?: string
  image_headline?: string
  cta?: string
  offer?: string
  prompt?: string
  reasoning?: string
  ad_angle?: string
}

function Field({ label, value }: { label: string; value?: React.ReactNode }) {
  if (value == null || value === '' || value === '—') return null
  return (
    <div className="min-w-0">
      <p className="text-[10px] font-bold uppercase tracking-wide text-mid mb-0.5">{label}</p>
      <div className="text-sm text-charcoal break-words whitespace-pre-wrap">{value}</div>
    </div>
  )
}

function Chip({ children }: { children: React.ReactNode }) {
  return (
    <span className="inline-flex items-center rounded-full border border-border bg-surface px-2.5 py-1 text-[11px] font-semibold text-charcoal">
      {children}
    </span>
  )
}

type Props = {
  brief: Brief
  brand?: Brand | null
  angleOptions?: CatalogOption[]
}

export default function BriefOverviewPanel({ brief, brand, angleOptions }: Props) {
  const kb = (brief.key_benefits ?? {}) as Record<string, unknown>
  const audience = (kb.audience as Record<string, string> | undefined) || {}
  const mediaType = String(kb.media_type || '')
  const industry = String(kb.industry || '')
  const niche = String(kb.niche || '')
  const offer = String(kb.offer || '')
  const notes = String(kb.notes || '')
  const websiteUrl = String(kb.website_url || '')
  const aspect = String(kb.image_aspect_ratio || '')
  const icpText = String(kb.image_icp_text || '')
  const frameworks = Array.isArray(kb.hook_frameworks)
    ? (kb.hook_frameworks as string[])
    : []
  const placements = Array.isArray(kb.placements) ? (kb.placements as string[]) : []
  const imageVariants = Array.isArray(kb.image_variants)
    ? (kb.image_variants as ImageVariantStored[])
    : []

  const isImage = mediaType === 'image' || (brief.formats ?? []).every(
    (f) => f === 'static' || f === 'carousel'
  )

  return (
    <div className="space-y-4">
      <Card title="Brief overview" subtitle="Everything saved for this campaign">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          <Field label="Title" value={brief.title} />
          <Field label="Brand" value={brand?.name} />
          <Field label="Objective" value={brief.objective} />
          <Field label="Industry" value={industry || undefined} />
          <Field label="Niche" value={niche || undefined} />
          <Field
            label="Media"
            value={isImage ? 'Image' : mediaType === 'video' ? 'Video' : undefined}
          />
          <Field label="Formats" value={(brief.formats ?? []).join(', ') || undefined} />
          <Field label="Aspect ratio" value={aspect || undefined} />
          <Field label="Target variants" value={String(brief.variant_count || kb.target_variant_count || '')} />
          <Field label="CTA" value={brief.cta || undefined} />
          <Field label="Tone" value={brief.ad_copy_tone || undefined} />
          <Field label="Product" value={brief.product_name || undefined} />
          <Field label="Offer" value={offer || undefined} />
          <Field label="Website" value={websiteUrl || undefined} />
          <Field
            label="Audience"
            value={
              brief.target_audience ||
              [audience.audience_type, audience.geography, audience.age_range, audience.languages]
                .filter(Boolean)
                .join(' · ') ||
              undefined
            }
          />
          {placements.length > 0 && (
            <div className="sm:col-span-2 lg:col-span-3">
              <p className="text-[10px] font-bold uppercase tracking-wide text-mid mb-1.5">
                Placements
              </p>
              <div className="flex flex-wrap gap-1.5">
                {placements.map((p) => (
                  <Chip key={p}>{p}</Chip>
                ))}
              </div>
            </div>
          )}
          {brand && (brand.primary_color || brand.logo_url) && (
            <div className="sm:col-span-2 lg:col-span-3 flex flex-wrap items-center gap-3">
              <p className="text-[10px] font-bold uppercase tracking-wide text-mid w-full">
                Brand kit
              </p>
              {brand.logo_url ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={brand.logo_url}
                  alt={brand.name}
                  className="h-10 w-10 object-contain rounded-lg border border-border bg-white"
                />
              ) : null}
              {brand.primary_color ? (
                <span
                  className="w-7 h-7 rounded-full border border-border"
                  style={{ background: brand.primary_color }}
                  title={brand.primary_color}
                />
              ) : null}
              {brand.secondary_color ? (
                <span
                  className="w-7 h-7 rounded-full border border-border"
                  style={{ background: brand.secondary_color }}
                  title={brand.secondary_color}
                />
              ) : null}
            </div>
          )}
        </div>
        {notes ? (
          <div className="mt-4 pt-4 border-t border-border">
            <Field label="Notes" value={notes} />
          </div>
        ) : null}
      </Card>

      {frameworks.length > 0 && (
        <Card title="Ad angles" subtitle="Selected for this campaign">
          <div className="flex flex-wrap gap-2">
            {frameworks.map((id) => (
              <Chip key={id}>{labelForAngle(id, angleOptions)}</Chip>
            ))}
          </div>
        </Card>
      )}

      {icpText ? (
        <Card title="ICP" subtitle="Ideal customer profile used for creatives">
          <p className="text-sm text-charcoal whitespace-pre-wrap leading-relaxed">{icpText}</p>
        </Card>
      ) : null}

      {imageVariants.length > 0 && (
        <Card
          title={`Image variants (${imageVariants.length})`}
          subtitle="Saved hooks, messages, CTAs, and prompts"
        >
          <div className="space-y-4">
            {imageVariants.map((slot, i) => (
              <div
                key={i}
                className="rounded-xl border border-border bg-surface/60 p-4 space-y-2"
              >
                <div className="flex flex-wrap items-center gap-2">
                  <p className="text-sm font-bold text-navy">Variant {i + 1}</p>
                  {slot.ad_angle ? (
                    <Chip>{labelForAngle(slot.ad_angle, angleOptions)}</Chip>
                  ) : null}
                </div>
                {(slot.use_cases?.length ?? 0) > 0 && (
                  <div className="flex flex-wrap gap-1.5">
                    {slot.use_cases!.map((uc) => (
                      <Chip key={uc}>{labelForUseCase(uc)}</Chip>
                    ))}
                  </div>
                )}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <Field label="Hook (post)" value={slot.hook} />
                  <Field label="Headline (post)" value={slot.message} />
                  <Field label="On-image hook" value={slot.image_hook} />
                  <Field label="On-image headline" value={slot.image_headline} />
                  <Field label="CTA on image" value={slot.cta} />
                  <Field label="Offer" value={slot.offer} />
                </div>
                {slot.prompt ? (
                  <Field label="Image prompt" value={slot.prompt} />
                ) : (
                  <p className="text-[11px] text-mid italic">No prompt saved yet</p>
                )}
                {slot.reasoning ? <Field label="Reasoning" value={slot.reasoning} /> : null}
              </div>
            ))}
          </div>
        </Card>
      )}
    </div>
  )
}
