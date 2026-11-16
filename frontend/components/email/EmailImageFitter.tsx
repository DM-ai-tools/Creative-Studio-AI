'use client'

import React, { useMemo, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import TextArea from '@/components/ui/TextArea'
import Select from '@/components/ui/Select'
import Badge from '@/components/ui/Badge'
import { emailTemplatesApi, type EmailImportAnalysis, type EmailImportImage, type EmailImportSlot } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import type { Brand } from '@/types'

type Props = {
  brands: Brand[]
  imageModels: { value: string; label: string }[]
  defaultImageModel: string
}

type Result =
  | { status: 'working' }
  | { status: 'error'; error: string }
  | ({ status: 'done' } & EmailImportImage)

const ROLE_LABEL: Record<string, string> = {
  hero: 'Hero', banner: 'Banner', product: 'Product', content: 'Picture',
  logo: 'Logo', icon: 'Icon', tracking: 'Tracking', other: 'Other',
}
const ROLE_BADGE: Record<string, 'green' | 'blue' | 'gray' | 'amber'> = {
  hero: 'green', banner: 'green', product: 'blue', content: 'blue', logo: 'amber', icon: 'gray', tracking: 'gray', other: 'gray',
}
const MAX_PARALLEL = 2

function absoluteMediaUrl(url?: string | null) {
  if (!url) return null
  if (/^https?:\/\//i.test(url)) return url
  const path = url.startsWith('/') ? url : `/${url}`
  const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
  return `${api.replace(/\/api\/v1$/, '')}${path}`
}

const escapeHtml = (value: string) =>
  value.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/'/g, '&#039;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

export default function EmailImageFitter({ brands, imageModels, defaultImageModel }: Props) {
  const fileInput = useRef<HTMLInputElement>(null)
  const [html, setHtml] = useState('')
  const [fileName, setFileName] = useState('')
  const [analysis, setAnalysis] = useState<EmailImportAnalysis | null>(null)
  const [analyzing, setAnalyzing] = useState(false)
  const [picked, setPicked] = useState<Record<string, boolean>>({})
  const [descriptions, setDescriptions] = useState<Record<string, string>>({})
  const [results, setResults] = useState<Record<string, Result>>({})
  const [brandId, setBrandId] = useState('')
  const [campaignName, setCampaignName] = useState('')
  const [notes, setNotes] = useState('')
  const [imageModel, setImageModel] = useState(defaultImageModel)
  const [running, setRunning] = useState(false)
  const [exported, setExported] = useState<{ html: string; warnings: string[] } | null>(null)
  const [exporting, setExporting] = useState(false)
  const [previewMode, setPreviewMode] = useState<'desktop' | 'mobile'>('desktop')

  const slots = analysis?.slots ?? []
  const pickedIds = slots.filter((s) => picked[s.id]).map((s) => s.id)
  const doneIds = slots.filter((s) => results[s.id]?.status === 'done').map((s) => s.id)

  const reset = () => {
    setAnalysis(null); setPicked({}); setDescriptions({}); setResults({}); setExported(null)
  }

  const loadFile = async (file: File) => {
    try {
      const text = await file.text()
      setHtml(text)
      setFileName(file.name)
      reset()
      toast.success(`${file.name} loaded — now click “Find image spots”`)
    } catch {
      toast.error('Could not read that file')
    }
  }

  const analyze = async () => {
    if (html.trim().length < 10) return toast.error('Upload or paste an HTML email first')
    setAnalyzing(true)
    try {
      const data = await emailTemplatesApi.analyzeImport(html)
      reset()
      setAnalysis(data)
      setPicked(Object.fromEntries(data.slots.map((s) => [s.id, s.replaceable])))
      if (!data.slot_count) toast('No images found in this email.')
    } catch (err) {
      toast.error(extractApiError(err, 'Could not read this email'))
    } finally {
      setAnalyzing(false)
    }
  }

  const generateOne = async (slot: EmailImportSlot) => {
    setResults((r) => ({ ...r, [slot.id]: { status: 'working' } }))
    try {
      const image = await emailTemplatesApi.generateImportImage({
        brand_id: brandId || null,
        campaign_name: campaignName,
        slot_id: slot.id,
        role: slot.role,
        width: slot.plan_width,
        height: slot.plan_height,
        description: descriptions[slot.id] ?? '',
        alt: slot.alt,
        context_text: slot.context_text,
        notes,
        image_model: imageModel,
      })
      setResults((r) => ({ ...r, [slot.id]: { status: 'done', ...image } }))
      setExported(null) // the previous final email no longer matches
    } catch (err) {
      setResults((r) => ({ ...r, [slot.id]: { status: 'error', error: extractApiError(err, 'Image generation failed') } }))
    }
  }

  const generateSelected = async () => {
    const queue = slots.filter((s) => picked[s.id])
    if (!queue.length) return toast.error('Tick at least one image spot')
    setRunning(true)
    try {
      let next = 0
      const worker = async () => {
        while (next < queue.length) {
          const slot = queue[next++]
          await generateOne(slot)
        }
      }
      await Promise.all(Array.from({ length: Math.min(MAX_PARALLEL, queue.length) }, worker))
    } finally {
      setRunning(false)
    }
  }

  const buildFinal = async () => {
    const replacements: Record<string, string> = {}
    for (const slot of slots) {
      const r = results[slot.id]
      if (picked[slot.id] && r?.status === 'done') replacements[slot.id] = r.url
    }
    if (!Object.keys(replacements).length) return toast.error('Generate at least one picture first')
    setExporting(true)
    try {
      const out = await emailTemplatesApi.exportImport(html, replacements)
      setExported({ html: out.html, warnings: out.warnings })
      if (out.skipped.length) toast.error(`${out.skipped.length} picture(s) could not be placed`)
      else toast.success('Final email ready')
    } catch (err) {
      toast.error(extractApiError(err, 'Could not build the final email'))
    } finally {
      setExporting(false)
    }
  }

  // The preview loads images from the app server directly; the exported file uses public addresses.
  const previewHtml = useMemo(() => {
    if (!exported) return ''
    let out = exported.html
    for (const r of Object.values(results)) {
      if (r.status !== 'done') continue
      const local = absoluteMediaUrl(r.url)
      if (local && r.absolute_url && local !== r.absolute_url) out = out.split(escapeHtml(r.absolute_url)).join(escapeHtml(local))
    }
    return out
  }, [exported, results])

  const download = () => {
    if (!exported) return
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([exported.html], { type: 'text/html;charset=utf-8' }))
    link.download = fileName ? fileName.replace(/\.html?$/i, '') + '-new-images.html' : 'email-new-images.html'
    link.click()
    URL.revokeObjectURL(link.href)
  }
  const copy = async () => {
    if (!exported) return
    await navigator.clipboard.writeText(exported.html)
    toast.success('Email HTML copied')
  }

  const sizeLabel = (s: EmailImportSlot) =>
    `${s.plan_width} × ${s.plan_height}px${s.size_assumed ? ' (assumed)' : ''}`

  return (
    <Card
      title="Use your own email template"
      subtitle="Upload your HTML email. We find each image spot, generate a picture that fits it exactly, and give your email back with only the pictures changed."
    >
      <div className="space-y-5">
        {/* 1. Upload */}
        <div className="grid gap-4 lg:grid-cols-[minmax(260px,1fr)_minmax(0,2fr)]">
          <div className="space-y-2">
            <label className="block text-[11px] font-semibold text-mid">1. Your email (.html)</label>
            <input
              ref={fileInput}
              type="file"
              accept=".html,.htm,text/html"
              className="block w-full text-xs text-mid"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) void loadFile(f) }}
            />
            <p className="text-[11px] leading-relaxed text-muted">
              Export it from Mailchimp, Klaviyo, HubSpot or your designer. Your text, layout, links, merge tags
              (like {'{{first_name}}'}) and unsubscribe block are never changed.
            </p>
          </div>
          <div className="space-y-2">
            <TextArea
              value={html}
              onChange={(e) => { setHtml(e.target.value); reset() }}
              placeholder="…or paste the email HTML here"
              className="min-h-[96px] font-mono text-[10px]"
            />
            <div className="flex items-center gap-3">
              <Button onClick={analyze} isLoading={analyzing} disabled={html.trim().length < 10}>Find image spots</Button>
              {html ? <span className="text-[11px] text-muted">{html.length.toLocaleString()} characters{fileName ? ` · ${fileName}` : ''}</span> : null}
            </div>
          </div>
        </div>

        {analysis && (
          <>
            {/* 2. Choose */}
            <div className="rounded-xl border border-border bg-light/50 p-3 text-xs text-charcoal">
              Found <strong>{analysis.slot_count}</strong> image spot{analysis.slot_count === 1 ? '' : 's'};{' '}
              <strong>{analysis.replaceable_count}</strong> look like pictures AI can replace. Logos, icons and tracking pixels are
              left alone unless you tick them.
              {analysis.merge_tags.length > 0 && (
                <div className="mt-1 text-muted">Merge tags kept exactly as written: {analysis.merge_tags.join('  ')}</div>
              )}
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <Select
                label="Brand (colours & name)"
                value={brandId}
                onChange={(e) => setBrandId(e.target.value)}
                placeholder="No brand"
                options={brands.map((b) => ({ value: b.id, label: b.name }))}
              />
              <Input label="Campaign (optional)" value={campaignName} onChange={(e) => setCampaignName(e.target.value)} placeholder="Summer sale" />
              <Select label="Image model" value={imageModel} onChange={(e) => setImageModel(e.target.value)} options={imageModels} />
              <Input label="Art direction (all pictures)" value={notes} onChange={(e) => setNotes(e.target.value)} placeholder="Bright, natural light, no people" />
            </div>

            <div className="overflow-x-auto rounded-xl border border-border">
              <table className="w-full text-xs">
                <thead>
                  <tr className="bg-light">
                    {['Replace', '#', 'Now', 'Spot', 'What should the picture show?', 'New picture'].map((h) => (
                      <th key={h} className="border-b border-border px-3 py-2 text-left text-[10px] font-bold uppercase tracking-wide text-mid">{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {slots.map((slot, i) => {
                    const r = results[slot.id]
                    return (
                      <tr key={slot.id} className="border-b border-border align-top">
                        <td className="px-3 py-2.5">
                          <input
                            type="checkbox"
                            checked={!!picked[slot.id]}
                            onChange={(e) => setPicked({ ...picked, [slot.id]: e.target.checked })}
                            aria-label={`Replace image ${i + 1}`}
                          />
                        </td>
                        <td className="px-3 py-2.5 font-semibold text-navy">{i + 1}</td>
                        <td className="px-3 py-2.5">
                          {/^https?:/i.test(slot.src) ? (
                            // eslint-disable-next-line @next/next/no-img-element
                            <img src={slot.src} alt="" className="h-14 w-24 rounded border border-border bg-white object-contain" />
                          ) : (
                            <div className="flex h-14 w-24 items-center justify-center rounded border border-dashed border-border text-[10px] text-muted">
                              {slot.is_inline_data ? 'embedded' : 'no preview'}
                            </div>
                          )}
                        </td>
                        <td className="px-3 py-2.5 space-y-1">
                          <Badge variant={ROLE_BADGE[slot.role] ?? 'gray'} size="xs">{ROLE_LABEL[slot.role] ?? slot.role}</Badge>
                          <div className="tabular-nums text-mid">{sizeLabel(slot)}</div>
                          {slot.kind === 'background' && <div className="text-[10px] text-muted">background image</div>}
                          {slot.reason && <div className="max-w-[160px] text-[10px] text-muted">{slot.reason}</div>}
                        </td>
                        <td className="px-3 py-2.5">
                          <input
                            className="w-full min-w-[200px] rounded-md border border-border bg-white px-2 py-1.5 text-xs"
                            placeholder={slot.alt || slot.context_text || 'Describe the picture (optional)'}
                            value={descriptions[slot.id] ?? ''}
                            onChange={(e) => setDescriptions({ ...descriptions, [slot.id]: e.target.value })}
                          />
                        </td>
                        <td className="px-3 py-2.5">
                          {!r ? <span className="text-muted">—</span>
                            : r.status === 'working' ? <span className="text-mid">Generating…</span>
                            : r.status === 'error' ? (
                              <div className="space-y-1">
                                <div className="max-w-[200px] text-[11px] text-red-600">{r.error}</div>
                                <Button size="xs" variant="outline" onClick={() => void generateOne(slot)}>Try again</Button>
                              </div>
                            ) : (
                              <div className="space-y-1">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img src={absoluteMediaUrl(r.url) ?? ''} alt="" className="h-14 w-24 rounded border border-border object-cover" />
                                <div className="text-[10px] text-muted">{r.width}×{r.height}px · {(r.file_size / 1024).toFixed(0)} KB</div>
                                <Button size="xs" variant="outline" disabled={running} onClick={() => void generateOne(slot)}>Regenerate</Button>
                              </div>
                            )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <Button onClick={generateSelected} isLoading={running} disabled={!pickedIds.length}>
                Generate {pickedIds.length} picture{pickedIds.length === 1 ? '' : 's'}
              </Button>
              <Button variant="secondary" onClick={buildFinal} isLoading={exporting} disabled={running || !doneIds.length}>
                Build final email
              </Button>
              <span className="text-[11px] text-muted">Each picture uses image credits. Nothing is generated until you click.</span>
            </div>
          </>
        )}

        {/* 3. Result */}
        {exported && (
          <div className="space-y-3">
            {exported.warnings.map((w) => (
              <div key={w} className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">{w}</div>
            ))}
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="flex gap-2">
                <Button onClick={download}>Download HTML</Button>
                <Button variant="outline" onClick={copy}>Copy HTML</Button>
              </div>
              <div className="flex rounded-lg border border-border p-0.5">
                {(['desktop', 'mobile'] as const).map((mode) => (
                  <button
                    key={mode}
                    onClick={() => setPreviewMode(mode)}
                    className={`rounded-md px-2.5 py-1 text-[11px] capitalize ${previewMode === mode ? 'bg-charcoal text-white' : 'text-muted'}`}
                  >
                    {mode}
                  </button>
                ))}
              </div>
            </div>
            <div className="min-h-[520px] overflow-auto rounded-xl border border-border bg-[#e8e8e8] p-3">
              <iframe
                title="Final email preview"
                srcDoc={previewHtml}
                sandbox=""
                className="mx-auto block h-[640px] border-0 bg-white shadow-lg"
                style={{ width: previewMode === 'mobile' ? 390 : '100%', maxWidth: previewMode === 'desktop' ? 720 : 390 }}
              />
            </div>
          </div>
        )}
      </div>
    </Card>
  )
}
