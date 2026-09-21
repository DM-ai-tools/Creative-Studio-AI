'use client'

import React, { useCallback, useEffect, useRef, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import { assetsApi, generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { assetUrl } from '@/lib/utils'
import type { Asset, BriefReferenceImage } from '@/types'

const MAX_REFERENCE_IMAGES = 5

type ReferenceImagesPanelProps = {
  brandId?: string
  brandName?: string
  industry?: string
  niche?: string
  productName?: string
  selected: BriefReferenceImage[]
  onChange: (refs: BriefReferenceImage[]) => void
  onExactProductChange?: (enabled: boolean) => void
}

function analysisFromAsset(asset: Asset): BriefReferenceImage['analysis'] {
  const meta = asset.metadata ?? {}
  const analysis = meta.analysis
  if (analysis && typeof analysis === 'object') {
    return analysis as BriefReferenceImage['analysis']
  }
  return undefined
}

export default function ReferenceImagesPanel({
  brandId,
  brandName,
  industry,
  niche,
  productName,
  selected,
  onChange,
  onExactProductChange,
}: ReferenceImagesPanelProps) {
  const [library, setLibrary] = useState<Asset[]>([])
  const [loadingLibrary, setLoadingLibrary] = useState(false)
  const [showLibrary, setShowLibrary] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [productSource, setProductSource] = useState('')
  const [fetchingProduct, setFetchingProduct] = useState(false)
  const [exactProduct, setExactProduct] = useState(false)
  const persistLock = useRef(false)

  const loadLibrary = useCallback(async () => {
    if (!brandId) {
      setLibrary([])
      return
    }
    setLoadingLibrary(true)
    try {
      const rows = await assetsApi.list({
        brand_id: brandId,
        asset_type: 'reference_image',
      })
      setLibrary(rows)
    } catch (err: unknown) {
      console.error('Failed to load brand reference images', err)
      toast.error('Could not load Brand Kit reference images')
      setLibrary([])
    } finally {
      setLoadingLibrary(false)
    }
  }, [brandId])

  useEffect(() => {
    setShowLibrary(false)
    setLibrary([])
  }, [brandId])

  useEffect(() => {
    if (showLibrary) void loadLibrary()
  }, [showLibrary, loadLibrary])

  const persistPending = useCallback(async () => {
    if (!brandId || persistLock.current) return
    const pending = selected.filter((r) => r.pendingFile && !r.asset_id)
    if (!pending.length) return

    persistLock.current = true
    setUploading(true)
    try {
      const updated: BriefReferenceImage[] = [...selected]
      for (const ref of pending) {
        if (!ref.pendingFile) continue
        const result = await generationApi.analyzeReferenceImage(ref.pendingFile, {
          brand_id: brandId,
          brand_name: brandName,
          niche,
        })
        const idx = updated.findIndex(
          (r) => r.pendingFile === ref.pendingFile || r.localPreview === ref.localPreview,
        )
        if (idx < 0) continue
        if (ref.localPreview?.startsWith('blob:')) {
          URL.revokeObjectURL(ref.localPreview)
        }
        updated[idx] = {
          asset_id: result.asset_id ?? undefined,
          file_url: result.file_url || ref.file_url,
          analysis: result.analysis,
          summary: result.summary,
        }
      }
      onChange(updated.filter((r) => r.file_url || r.asset_id).slice(0, MAX_REFERENCE_IMAGES))
      await loadLibrary()
      toast.success('Reference images saved to Brand Kit')
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Could not save reference images to Brand Kit'))
    } finally {
      setUploading(false)
      persistLock.current = false
    }
  }, [brandId, brandName, niche, selected, onChange, loadLibrary])

  useEffect(() => {
    if (!brandId) return
    if (!selected.some((r) => r.pendingFile && !r.asset_id)) return
    void persistPending()
  }, [brandId])

  const isSelected = (key: string) =>
    selected.some((r) => (r.asset_id && r.asset_id === key) || r.file_url === key)

  const toggleLibraryAsset = (asset: Asset) => {
    const key = asset.id || asset.file_url
    if (isSelected(key)) {
      onChange(
        selected.filter((r) => r.asset_id !== asset.id && r.file_url !== asset.file_url),
      )
      return
    }
    if (selected.length >= MAX_REFERENCE_IMAGES) {
      toast.error(`Maximum ${MAX_REFERENCE_IMAGES} reference images`)
      return
    }
    const analysis = analysisFromAsset(asset)
    onChange([
      ...selected,
      {
        asset_id: asset.id,
        file_url: asset.file_url,
        analysis,
        summary:
          (typeof asset.metadata?.summary === 'string' ? asset.metadata.summary : '') ||
          analysis?.summary ||
          asset.file_name,
      },
    ])
  }

  const removeSelected = (ref: BriefReferenceImage) => {
    if (ref.localPreview?.startsWith('blob:')) {
      URL.revokeObjectURL(ref.localPreview)
    }
    onChange(
      selected.filter(
        (r) =>
          r !== ref &&
          (ref.asset_id ? r.asset_id !== ref.asset_id : r.file_url !== ref.file_url),
      ),
    )
  }

  const handleFiles = async (files: FileList | null) => {
    if (!files?.length) return
    const slots = MAX_REFERENCE_IMAGES - selected.length
    if (slots <= 0) {
      toast.error(`Maximum ${MAX_REFERENCE_IMAGES} reference images`)
      return
    }

    setUploading(true)
    try {
      const added: BriefReferenceImage[] = []
      for (const file of Array.from(files).slice(0, slots)) {
        if (brandId) {
          const result = await generationApi.analyzeReferenceImage(file, {
            brand_id: brandId,
            brand_name: brandName,
            niche,
          })
          if (!result.file_url && !result.analysis) continue
          added.push({
            asset_id: result.asset_id ?? undefined,
            file_url: result.file_url || '',
            analysis: result.analysis,
            summary: result.summary,
          })
        } else {
          const preview = URL.createObjectURL(file)
          const result = await generationApi.analyzeReferenceImage(file, {
            brand_name: brandName,
            niche,
          })
          added.push({
            file_url: preview,
            localPreview: preview,
            pendingFile: file,
            analysis: result.analysis,
            summary: result.summary,
          })
          toast('Select a brand below — we will save these to Brand Kit automatically', {
            icon: 'ℹ️',
          })
        }
      }
      if (added.length) {
        onChange([...selected, ...added].slice(0, MAX_REFERENCE_IMAGES))
        if (brandId) {
          await loadLibrary()
          toast.success(`Added ${added.length} reference image(s) to Brand Kit`)
        } else {
          toast.success(`Added ${added.length} reference image(s) for this brief`)
        }
      }
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Could not analyze reference image'))
    } finally {
      setUploading(false)
    }
  }

  const handleProductSource = async () => {
    if (!brandId) {
      toast.error('Select a brand before fetching a product')
      return
    }
    if (!productSource.trim()) {
      toast.error('Paste a product URL or slug first')
      return
    }
    setFetchingProduct(true)
    try {
      const result = await generationApi.fetchProductReference({
        source: productSource.trim(),
        brand_id: brandId,
        brand_name: brandName,
        niche,
      })
      const fileUrl = result.file_url || ''
      if (!fileUrl) throw new Error('No product image was returned')
      if (selected.length >= MAX_REFERENCE_IMAGES) {
        toast.error(`Maximum ${MAX_REFERENCE_IMAGES} reference images`)
        return
      }
      onChange([
        ...selected,
        {
          asset_id: result.asset_id ?? undefined,
          file_url: fileUrl,
          analysis: result.analysis,
          summary: result.summary || result.analysis?.product_description,
          is_product_reference: true,
          product_reference_context: {
            brand_id: brandId,
            industry: industry?.trim() || '',
            niche: niche?.trim() || '',
            product_name: productName?.trim() || '',
          },
        },
      ].slice(0, MAX_REFERENCE_IMAGES))
      setProductSource('')
      toast.success('Exact product image saved to this brand')
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Could not fetch product image'))
    } finally {
      setFetchingProduct(false)
    }
  }

  const previewUrl = (ref: BriefReferenceImage) => {
    if (ref.localPreview) return ref.localPreview
    return assetUrl(ref.file_url)
  }

  return (
    <div className="rounded-xl border border-dashed border-accent/40 bg-white/60 p-4 space-y-3">
      <div>
        <p className="text-xs font-bold text-navy uppercase tracking-wide">
          Reference images <span className="font-normal normal-case text-mid">(optional)</span>
        </p>
        <p className="text-[11px] text-mid mt-1">
          Product shots or ad examples — AI reads colours, product, and style. When a brand is
          selected, uploads are saved to <strong>Brand Kit → Reference image library</strong>. Up to{' '}
          {MAX_REFERENCE_IMAGES} images.
        </p>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
          multiple
          disabled={uploading || selected.length >= MAX_REFERENCE_IMAGES}
          onChange={(e) => {
            void handleFiles(e.target.files)
            e.target.value = ''
          }}
          className="block min-w-0 flex-1 text-xs text-mid file:mr-3 file:rounded-full file:border file:border-accent/40 file:bg-white file:px-3.5 file:py-2 file:text-xs file:font-semibold file:text-charcoal hover:file:bg-accent/10"
        />
        {uploading && (
          <span className="text-xs text-mid animate-pulse">Analyzing…</span>
        )}
      </div>

      {brandId && (
        <div className="rounded-lg border border-accent/25 bg-accent/5 p-3 space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-wide text-navy">
            Product URL or slug (optional)
          </p>
          <div className="flex flex-col sm:flex-row gap-2">
            <input
              value={productSource}
              onChange={(event) => setProductSource(event.target.value)}
              placeholder="Paste product page URL or product slug"
              className="min-w-0 flex-1 rounded-lg border border-border bg-white px-3 py-2 text-xs text-charcoal"
              disabled={fetchingProduct}
            />
            <Button
              type="button"
              size="sm"
              variant="outline"
              isLoading={fetchingProduct}
              onClick={() => void handleProductSource()}
            >
              Fetch product image
            </Button>
          </div>
          <label className="flex items-center gap-2 text-[11px] text-charcoal">
            <input
              type="checkbox"
              checked={exactProduct}
              onChange={(event) => {
                const enabled = event.target.checked
                setExactProduct(enabled)
                onExactProductChange?.(enabled)
              }}
              className="accent-accent"
            />
            Use this exact product image in generated ads
          </label>
        </div>
      )}

      {selected.length > 0 && (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-5 gap-3">
          {selected.map((ref, idx) => {
            const url = previewUrl(ref)
            const palette = ref.analysis?.color_palette ?? []
            const savedToKit = Boolean(ref.asset_id && ref.file_url?.startsWith('/files/'))
            return (
              <div
                key={ref.asset_id || ref.file_url || `ref-${idx}`}
                className="rounded-lg border border-border bg-white p-2 space-y-1"
              >
                {url ? (
                  <img
                    src={url}
                    alt=""
                    className="w-full h-20 object-cover rounded-md border border-border/60"
                  />
                ) : null}
                <p className="text-[10px] text-charcoal line-clamp-2">
                  {ref.summary || ref.analysis?.product_description || 'Reference'}
                </p>
                {savedToKit ? (
                  <p className="text-[9px] text-teal-700 font-semibold">In Brand Kit</p>
                ) : ref.pendingFile ? (
                  <p className="text-[9px] text-amber-700">Pending brand save…</p>
                ) : null}
                {palette.length > 0 && (
                  <div className="flex gap-1">
                    {palette.slice(0, 4).map((c) => (
                      <span
                        key={c}
                        className="w-4 h-4 rounded-full border border-border shrink-0"
                        style={{ background: c }}
                        title={c}
                      />
                    ))}
                  </div>
                )}
                <button
                  type="button"
                  className="text-[10px] text-red-600 hover:underline"
                  onClick={() => removeSelected(ref)}
                >
                  Remove
                </button>
              </div>
            )
          })}
        </div>
      )}

      {brandId && (
        <div className="space-y-2">
          <button
            type="button"
            className="text-[10px] font-semibold uppercase tracking-wide text-accent hover:underline"
            onClick={() => setShowLibrary((current) => !current)}
          >
            {showLibrary ? 'Hide stored reference images' : 'Show stored reference images'}
          </button>
          {showLibrary && (
            <>
              <p className="text-[10px] font-semibold uppercase tracking-wide text-muted">
                {loadingLibrary ? 'Loading selected brand library…' : 'Selected brand library'}
                {!loadingLibrary && library.length ? ` · ${library.length} saved` : ''}
              </p>
              {library.length === 0 && !loadingLibrary ? (
                <p className="text-[11px] text-mid">
                  No saved references for this brand yet — uploads above appear here automatically.
                </p>
              ) : (
                <div className="flex flex-wrap gap-2">
                  {library.map((asset) => {
                    const active = isSelected(asset.id || asset.file_url)
                    const thumb = assetUrl(asset.file_url)
                    return (
                      <button
                        key={asset.id}
                        type="button"
                        onClick={() => toggleLibraryAsset(asset)}
                        className={`rounded-lg border p-1 transition-all ${
                          active
                            ? 'border-accent ring-2 ring-accent/30'
                            : 'border-border hover:border-accent/40'
                        }`}
                        title={asset.file_name}
                      >
                        {thumb ? (
                          <img
                            src={thumb}
                            alt=""
                            className="w-14 h-14 object-cover rounded-md"
                          />
                        ) : (
                          <span className="w-14 h-14 flex items-center justify-center text-[10px] text-mid">
                            img
                          </span>
                        )}
                      </button>
                    )
                  })}
                </div>
              )}
            </>
          )}
        </div>
      )}

      {!brandId && (
        <p className="text-[11px] text-amber-800 bg-amber-50 border border-amber-200 rounded-lg px-3 py-2">
          <strong>Select a brand</strong> in Brand source below first — then uploads are stored in
          Brand Kit for every future brief.
        </p>
      )}
    </div>
  )
}
