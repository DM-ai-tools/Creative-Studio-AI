'use client'

import Link from 'next/link'
import React, { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { z } from 'zod'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import TextArea from '@/components/ui/TextArea'
import Select from '@/components/ui/Select'
import Combobox from '@/components/ui/Combobox'
import { useApi } from '@/hooks/useApi'
import { brandsApi, briefsApi } from '@/lib/api'
import type { AdFormat } from '@/types'

const TONE_OPTIONS = [
  { value: 'Professional', label: 'Professional' },
  { value: 'Casual', label: 'Casual & Friendly' },
  { value: 'Bold', label: 'Bold & Direct' },
  { value: 'Urgent', label: 'Urgent & Compelling' },
  { value: 'Warm', label: 'Warm & Empathetic' },
]

const FORMAT_OPTIONS = [
  { value: 'static', label: 'Static Image' },
  { value: 'reel', label: 'Reel' },
  { value: 'video', label: 'Video' },
  { value: 'carousel', label: 'Carousel' },
]

const schema = z.object({
  brand_id: z.string().min(1, 'Select a brand'),
  title: z.string().min(3, 'Title required'),
  objective: z.string().min(10, 'Objective required'),
  target_audience: z.string().min(5, 'Target audience required'),
  formats: z.array(z.string()).min(1, 'Select at least one format'),
  ad_copy_tone: z.string().min(2, 'Enter a tone for the ad copy'),
  cta: z.string().min(2, 'CTA required'),
  product_name: z.string().min(2, 'Product name required'),
})
type FormData = z.infer<typeof schema>

interface BriefFormProps {
  onSuccess(): void
  onCancel(): void
  defaultBrandId?: string
}

export default function BriefForm({ onSuccess, onCancel, defaultBrandId }: BriefFormProps) {
  const { data: brands } = useApi(() => brandsApi.list(), [])

  const { register, handleSubmit, watch, setValue, formState: { errors, isSubmitting } } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: { formats: [], ad_copy_tone: '', brand_id: defaultBrandId ?? '' },
  })

  useEffect(() => {
    if (defaultBrandId) setValue('brand_id', defaultBrandId)
  }, [defaultBrandId, setValue])

  const selectedFormats = watch('formats')

  const toggleFormat = (fmt: string) => {
    const current = selectedFormats ?? []
    setValue(
      'formats',
      current.includes(fmt) ? current.filter((f) => f !== fmt) : [...current, fmt],
      { shouldValidate: true }
    )
  }

  const onSubmit = async (data: FormData) => {
    try {
      const brief = await briefsApi.create({
        brand_id: data.brand_id,
        title: data.title,
        objective: data.objective,
        target_audience: data.target_audience,
        formats: data.formats as AdFormat[],
        ad_copy_tone: data.ad_copy_tone.trim(),
        cta: data.cta,
        product_name: data.product_name,
        key_benefits: {},
      })
      toast.success('Brief created!')
      onSuccess()
    } catch {
      toast.error('Failed to create brief')
    }
  }

  const brandOptions = (brands ?? []).map((b) => ({ value: b.id, label: b.name }))
  const hasBrands = brandOptions.length > 0

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {!hasBrands && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">
          No brands are available for this workspace yet. Create one in{' '}
          <Link href="/brand-kit" className="font-semibold text-mint hover:underline">
            Brand Kit
          </Link>{' '}
          or finish onboarding first.
        </div>
      )}
      <Select
        label="Brand"
        options={brandOptions}
        placeholder={hasBrands ? 'Select a brand' : 'No brands available'}
        disabled={!hasBrands}
        error={errors.brand_id?.message}
        {...register('brand_id')}
      />
      <Input label="Brief Title" placeholder="Spring Roast Launch" error={errors.title?.message} {...register('title')} />
      <Input label="Product Name" placeholder="Ethiopian Single Origin" error={errors.product_name?.message} {...register('product_name')} />
      <TextArea
        label="Campaign Objective"
        placeholder="Drive subscription sign-ups for our coffee delivery service..."
        rows={2}
        error={errors.objective?.message}
        {...register('objective')}
      />
      <TextArea
        label="Target Audience"
        placeholder="Coffee enthusiasts aged 25-45, health-conscious, premium lifestyle..."
        rows={2}
        error={errors.target_audience?.message}
        {...register('target_audience')}
      />

      <div>
        <label className="block text-xs font-bold text-navy uppercase tracking-wide mb-2">Ad Formats</label>
        <div className="flex flex-wrap gap-2">
          {FORMAT_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              type="button"
              onClick={() => toggleFormat(opt.value)}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
                selectedFormats?.includes(opt.value)
                  ? 'bg-mint text-navy border-mint'
                  : 'bg-white text-mid border-border hover:border-mint'
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
        {errors.formats && <p className="mt-1 text-xs text-red-500">{errors.formats.message}</p>}
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Combobox
          label="Tone"
          placeholder="e.g. Professional, casual & friendly, bold and direct…"
          hint="Type any tone"
          options={TONE_OPTIONS}
          error={errors.ad_copy_tone?.message}
          {...register('ad_copy_tone')}
        />
        <Input label="Call to Action" placeholder="Shop Now" error={errors.cta?.message} {...register('cta')} />
      </div>

      <div className="flex gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} className="flex-1">Cancel</Button>
        <Button type="submit" variant="primary" isLoading={isSubmitting} disabled={!hasBrands} className="flex-1">Create Brief</Button>
      </div>
    </form>
  )
}
