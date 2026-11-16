'use client'

import React, { useMemo, useState } from 'react'
import toast from 'react-hot-toast'
import Topbar from '@/components/layout/Topbar'
import Card from '@/components/ui/Card'
import Button from '@/components/ui/Button'
import Input from '@/components/ui/Input'
import TextArea from '@/components/ui/TextArea'
import Select from '@/components/ui/Select'
import Badge from '@/components/ui/Badge'
import { useApi } from '@/hooks/useApi'
import { assetsApi, brandsApi, emailTemplatesApi, type EmailLayoutBase } from '@/lib/api'
import EmailImageFitter from '@/components/email/EmailImageFitter'
import { buildEmailHtml } from '@/lib/emailTemplateHtml'
import { timeAgo } from '@/lib/utils'
import type { Brand, EmailTemplate, EmailTemplateContent } from '@/types'

const EMAIL_TYPES = [
  { value: 'promotional', label: 'Promotional offer' },
  { value: 'newsletter', label: 'Newsletter' },
  { value: 'product_launch', label: 'Product launch' },
  { value: 'abandoned_cart', label: 'Abandoned cart' },
  { value: 'lead_nurture', label: 'Lead nurture' },
  { value: 'announcement', label: 'Event / announcement' },
]

const IMAGE_MODELS = [
  { value: 'openai-gpt-image-2.6-sunburst', label: 'GPT Image 2.6 Sunburst' },
  { value: 'openai-gpt-image-2', label: 'GPT Image 2' },
  { value: 'openai-gpt-image-1.5', label: 'GPT Image 1.5' },
  { value: 'openai-gpt-image-1-mini', label: 'GPT Image 1 Mini' },
]

const HERO_MODES = [
  { value: 'generate_from_layout', label: 'Generate hero matching layout reference' },
  { value: 'use_layout_image', label: 'Use uploaded layout image as hero' },
  { value: 'generate', label: 'Generate hero (ignore layout image)' },
]

const emptyForm = {
  brand_id: '', campaign_name: '', email_type: 'promotional', audience: '', offer: '',
  landing_page_url: '', notes: '', image_model: 'openai-gpt-image-2.6-sunburst',
  use_layout_base: true, hero_mode: 'generate_from_layout' as const,
}

function absoluteMediaUrl(url?: string | null) {
  if (!url) return null
  if (/^https?:\/\//i.test(url)) return url
  const path = url.startsWith('/') ? url : `/${url}`
  const api = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'
  return `${api.replace(/\/api\/v1$/, '')}${path}`
}

export default function EmailTemplatesPage() {
  const [form, setForm] = useState(emptyForm)
  const [draft, setDraft] = useState<EmailTemplate | null>(null)
  const [generating, setGenerating] = useState(false)
  const [saving, setSaving] = useState(false)
  const [previewMode, setPreviewMode] = useState<'desktop' | 'mobile'>('desktop')
  const { data: brands, isLoading: brandsLoading } = useApi(() => brandsApi.list(), [], { cacheKey: 'email-template-brands' })
  const { data: history, isLoading: historyLoading, refetch: refetchHistory } = useApi(
    () => emailTemplatesApi.list(), [], { cacheKey: 'email-template-history', ttlMs: 10_000 }
  )
  const { data: layoutBase, refetch: refetchLayoutBase } = useApi(
    () => emailTemplatesApi.getLayoutBase(), [], { cacheKey: 'email-layout-base', ttlMs: 30_000 }
  )
  const [layoutLabel, setLayoutLabel] = useState('Email layout base')
  const [layoutHtml, setLayoutHtml] = useState('')
  const [layoutImageUrl, setLayoutImageUrl] = useState<string | null>(null)
  const [layoutAssetId, setLayoutAssetId] = useState<string | null>(null)
  const [savingLayout, setSavingLayout] = useState(false)
  const previewHtml = useMemo(() => draft ? buildEmailHtml(draft, {
    hero: absoluteMediaUrl(draft.content.hero_url), logo: absoluteMediaUrl(draft.content.logo_url),
  }) : '', [draft])

  const patchContent = (patch: Partial<EmailTemplateContent>) => setDraft((current) =>
    current ? { ...current, content: { ...current.content, ...patch } } : current)

  React.useEffect(() => {
    const base = layoutBase as EmailLayoutBase | undefined
    if (!base) return
    if (base.label) setLayoutLabel(base.label)
    if (base.layout_html) setLayoutHtml(base.layout_html)
    setLayoutImageUrl(base.layout_image_url ?? null)
    setLayoutAssetId(base.layout_asset_id ?? null)
  }, [layoutBase])

  const uploadLayoutImage = async (file: File) => {
    try {
      const asset = await assetsApi.upload(file, undefined, 'email_layout')
      setLayoutImageUrl(asset.file_url)
      setLayoutAssetId(asset.id)
      toast.success('Layout reference image uploaded')
    } catch {
      toast.error('Could not upload layout image')
    }
  }

  const uploadLayoutHtml = async (file: File) => {
    try {
      const text = await file.text()
      setLayoutHtml(text.slice(0, 200_000))
      toast.success('HTML template loaded — save layout base to persist')
    } catch {
      toast.error('Could not read HTML file')
    }
  }

  const saveLayoutBase = async () => {
    setSavingLayout(true)
    try {
      await emailTemplatesApi.saveLayoutBase({
        label: layoutLabel,
        layout_image_url: layoutImageUrl,
        layout_asset_id: layoutAssetId,
        layout_html: layoutHtml || null,
      })
      await refetchLayoutBase()
      toast.success('Email layout base saved to workspace')
    } catch {
      toast.error('Could not save layout base')
    } finally {
      setSavingLayout(false)
    }
  }

  const generate = async () => {
    if (!form.campaign_name.trim()) return toast.error('Enter a campaign name')
    setGenerating(true)
    try {
      const result = await emailTemplatesApi.generate({
        ...form,
        brand_id: form.brand_id || null,
        landing_page_url: form.landing_page_url.trim() || null,
        use_layout_base: form.use_layout_base,
        hero_mode: form.hero_mode,
      })
      setDraft(result)
      await refetchHistory()
      toast.success('Email template generated')
    } catch (error: unknown) {
      const detail = (error as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail
      toast.error(typeof detail === 'string' ? detail : 'Email generation failed')
    } finally { setGenerating(false) }
  }

  const save = async () => {
    if (!draft) return
    setSaving(true)
    try {
      const updated = await emailTemplatesApi.update(draft.id, {
        campaign_name: draft.campaign_name, email_type: draft.email_type, subject: draft.subject,
        preheader: draft.preheader, content: draft.content,
      })
      setDraft(updated)
      await refetchHistory()
      toast.success('Draft saved')
    } catch { toast.error('Could not save draft') } finally { setSaving(false) }
  }

  const downloadHtml = () => {
    if (!draft) return
    const link = document.createElement('a')
    link.href = URL.createObjectURL(new Blob([previewHtml], { type: 'text/html;charset=utf-8' }))
    link.download = `${draft.campaign_name.toLowerCase().replace(/[^a-z0-9]+/g, '-') || 'email-template'}.html`
    link.click()
    URL.revokeObjectURL(link.href)
  }
  const copyHtml = async () => { if (draft) { await navigator.clipboard.writeText(previewHtml); toast.success('Responsive HTML copied') } }
  const openDraft = (item: EmailTemplate) => {
    setDraft(item)
    setForm((current) => ({ ...current, brand_id: item.brand_id || '', campaign_name: item.campaign_name, email_type: item.email_type }))
  }

  return (
    <div>
      <Topbar title="Email Templates" subtitle="Generate branded hero visuals, edit responsive content and export production-ready HTML" />
      <div className="p-5 space-y-4">
        <EmailImageFitter
          brands={(brands ?? []) as Brand[]}
          imageModels={IMAGE_MODELS}
          defaultImageModel={emptyForm.image_model}
        />

        <Card title="Email layout base (workspace)" subtitle="Upload a mock or HTML shell — saved for all campaigns (Creative Studio asset library)">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="space-y-2">
              <Input label="Layout label" value={layoutLabel} onChange={(e) => setLayoutLabel(e.target.value)} placeholder="Newsletter shell" />
              <label className="block text-[11px] font-semibold text-mid">Layout mock image (PNG/JPG)</label>
              <input
                type="file"
                accept="image/*"
                className="block w-full text-xs text-mid"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadLayoutImage(f) }}
              />
              {layoutImageUrl ? (
                <img src={absoluteMediaUrl(layoutImageUrl) ?? layoutImageUrl} alt="Layout reference" className="max-h-28 rounded-lg border border-border object-contain" />
              ) : (
                <p className="text-[11px] text-muted">No layout image yet.</p>
              )}
            </div>
            <div className="space-y-2">
              <label className="block text-[11px] font-semibold text-mid">Optional HTML template (.html)</label>
              <input
                type="file"
                accept=".html,text/html"
                className="block w-full text-xs text-mid"
                onChange={(e) => { const f = e.target.files?.[0]; if (f) void uploadLayoutHtml(f) }}
              />
              <TextArea
                value={layoutHtml.slice(0, 4000)}
                onChange={(e) => setLayoutHtml(e.target.value)}
                placeholder="Paste HTML or upload a file — colours are sampled for new emails"
                className="min-h-[120px] font-mono text-[10px]"
              />
              {layoutHtml.length > 4000 ? <p className="text-[10px] text-muted">Showing first 4k chars of {layoutHtml.length.toLocaleString()} saved.</p> : null}
            </div>
            <div className="flex flex-col justify-end gap-2">
              <Button onClick={saveLayoutBase} isLoading={savingLayout}>Save layout base</Button>
              {layoutBase?.updated_at ? <p className="text-[10px] text-muted">Last saved {timeAgo(layoutBase.updated_at)}</p> : null}
            </div>
          </div>
        </Card>

        <div className="grid grid-cols-1 xl:grid-cols-[340px_minmax(360px,0.85fr)_minmax(440px,1.15fr)] gap-4 items-start">
          <Card title="1. Campaign setup" subtitle="Hero from your layout base or GPT Image; copy stays editable HTML">
            <div className="space-y-3">
              <Select label="Brand" value={form.brand_id} disabled={brandsLoading} onChange={(e) => setForm({ ...form, brand_id: e.target.value })} placeholder="Select a brand (optional)" options={(brands ?? []).map((brand: Brand) => ({ value: brand.id, label: brand.name }))} />
              <Input label="Campaign name" value={form.campaign_name} onChange={(e) => setForm({ ...form, campaign_name: e.target.value })} placeholder="Summer storage sale" />
              <Select label="Email type" value={form.email_type} onChange={(e) => setForm({ ...form, email_type: e.target.value })} options={EMAIL_TYPES} />
              <TextArea label="Audience" value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })} placeholder="Who should receive this email?" className="min-h-[78px]" />
              <TextArea label="Offer / message" value={form.offer} onChange={(e) => setForm({ ...form, offer: e.target.value })} placeholder="Offer, benefits, proof and deadline" className="min-h-[92px]" />
              <Input label="CTA landing-page URL" type="url" value={form.landing_page_url} onChange={(e) => setForm({ ...form, landing_page_url: e.target.value })} placeholder="https://example.com/offer" />
              <TextArea label="Creative notes" value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} placeholder="Visual direction, products, setting or exclusions" className="min-h-[76px]" />
              <Select label="Hero image model" value={form.image_model} onChange={(e) => setForm({ ...form, image_model: e.target.value })} options={IMAGE_MODELS} />
              <label className="flex items-center gap-2 text-xs text-charcoal">
                <input
                  type="checkbox"
                  checked={form.use_layout_base}
                  onChange={(e) => setForm({ ...form, use_layout_base: e.target.checked })}
                />
                Use saved email layout base
              </label>
              <Select
                label="Hero from layout"
                value={form.hero_mode}
                disabled={!form.use_layout_base}
                onChange={(e) => setForm({ ...form, hero_mode: e.target.value as typeof form.hero_mode })}
                options={HERO_MODES}
              />
              <Button className="w-full" size="lg" isLoading={generating} onClick={generate}>Generate email template</Button>
              <p className="text-[11px] leading-relaxed text-muted">The image contains no generated text. Headline, CTA and links remain readable, editable and clickable HTML.</p>
            </div>
          </Card>

          <Card title="2. Edit content" subtitle={draft ? `Saved draft · ${draft.campaign_name}` : 'Generate or open a draft'}>
            {!draft ? <div className="py-16 text-center text-sm text-muted">Your editable subject, copy, CTA and brand colours will appear here.</div> : (
              <div className="space-y-3">
                <Input label="Campaign name" value={draft.campaign_name} onChange={(e) => setDraft({ ...draft, campaign_name: e.target.value })} />
                <Input label="Subject line" value={draft.subject} onChange={(e) => setDraft({ ...draft, subject: e.target.value })} />
                <Input label="Preview text" value={draft.preheader} onChange={(e) => setDraft({ ...draft, preheader: e.target.value })} />
                <Input label="Eyebrow" value={draft.content.eyebrow} onChange={(e) => patchContent({ eyebrow: e.target.value })} />
                <TextArea label="Headline" value={draft.content.headline} onChange={(e) => patchContent({ headline: e.target.value })} className="min-h-[76px]" />
                <TextArea label="Body copy" value={draft.content.body} onChange={(e) => patchContent({ body: e.target.value })} className="min-h-[130px]" />
                <div className="grid grid-cols-2 gap-3">
                  <Input label="CTA text" value={draft.content.cta_text} onChange={(e) => patchContent({ cta_text: e.target.value })} />
                  <Input label="CTA URL" value={draft.content.cta_url} onChange={(e) => patchContent({ cta_url: e.target.value })} />
                </div>
                <div className="grid grid-cols-2 gap-3">
                  <Input label="Primary colour" type="color" value={draft.content.primary_color} onChange={(e) => patchContent({ primary_color: e.target.value })} className="px-2" />
                  <Input label="CTA colour" type="color" value={draft.content.secondary_color} onChange={(e) => patchContent({ secondary_color: e.target.value })} className="px-2" />
                </div>
                <div className="flex flex-wrap gap-4 rounded-xl border border-border bg-light/50 p-3 text-xs text-charcoal">
                  <label className="flex items-center gap-2"><input type="checkbox" checked={draft.content.show_logo} onChange={(e) => patchContent({ show_logo: e.target.checked })} /> Show logo</label>
                  <label className="flex items-center gap-2"><input type="checkbox" checked={draft.content.show_hero} onChange={(e) => patchContent({ show_hero: e.target.checked })} /> Show hero image</label>
                </div>
                <Input label="Footer text" value={draft.content.footer_text} onChange={(e) => patchContent({ footer_text: e.target.value })} />
                <div className="flex flex-wrap gap-2 pt-1">
                  <Button onClick={save} isLoading={saving}>Save draft</Button>
                  <Button variant="outline" onClick={copyHtml}>Copy HTML</Button>
                  <Button variant="secondary" onClick={downloadHtml}>Download HTML</Button>
                </div>
              </div>
            )}
          </Card>

          <Card title="3. Live preview" subtitle="Responsive table layout with inline email-safe styles" action={<div className="flex rounded-lg border border-border p-0.5"><button onClick={() => setPreviewMode('desktop')} className={`rounded-md px-2.5 py-1 text-[11px] ${previewMode === 'desktop' ? 'bg-charcoal text-white' : 'text-muted'}`}>Desktop</button><button onClick={() => setPreviewMode('mobile')} className={`rounded-md px-2.5 py-1 text-[11px] ${previewMode === 'mobile' ? 'bg-charcoal text-white' : 'text-muted'}`}>Mobile</button></div>}>
            <div className="rounded-xl border border-border bg-[#e8e8e8] p-3 min-h-[640px] overflow-auto">
              {draft ? <iframe title="Email preview" srcDoc={previewHtml} className="mx-auto block h-[620px] bg-white border-0 shadow-lg transition-all" style={{ width: previewMode === 'mobile' ? 390 : '100%', maxWidth: previewMode === 'desktop' ? 720 : 390 }} sandbox="allow-popups" /> : <div className="flex h-[610px] items-center justify-center text-center text-sm text-muted">Generate or open an email draft to preview it.</div>}
            </div>
          </Card>
        </div>

        <Card title="Saved email history" subtitle="Drafts persist across refreshes and can be edited or exported again" padding={false}>
          <div className="overflow-x-auto"><table className="w-full text-xs">
            <thead><tr className="bg-light">{['Campaign', 'Type', 'Subject', 'Updated', 'Status', 'Action'].map((head) => <th key={head} className="border-b border-border px-4 py-2 text-left text-[10px] font-bold uppercase tracking-wide text-mid">{head}</th>)}</tr></thead>
            <tbody>{historyLoading ? <tr><td colSpan={6} className="px-4 py-8 text-center text-muted">Loading drafts…</td></tr> : (history ?? []).length === 0 ? <tr><td colSpan={6} className="px-4 py-8 text-center text-muted">No email templates yet.</td></tr> : (history ?? []).map((item: EmailTemplate) => <tr key={item.id} className="border-b border-border hover:bg-light/50"><td className="px-4 py-3 font-semibold text-navy">{item.campaign_name}</td><td className="px-4 py-3 text-mid">{EMAIL_TYPES.find((type) => type.value === item.email_type)?.label ?? item.email_type}</td><td className="max-w-[360px] truncate px-4 py-3 text-mid">{item.subject}</td><td className="px-4 py-3 text-lt">{item.updated_at ? timeAgo(item.updated_at) : '—'}</td><td className="px-4 py-3"><Badge variant="green">{item.status}</Badge></td><td className="px-4 py-3"><Button size="sm" variant="outline" onClick={() => openDraft(item)}>Open</Button></td></tr>)}</tbody>
          </table></div>
        </Card>
      </div>
    </div>
  )
}

