'use client'

import React, { useCallback, useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import Button from '@/components/ui/Button'
import { assetsApi, generationApi } from '@/lib/api'
import { extractApiError } from '@/lib/apiErrors'
import { assetUrl } from '@/lib/utils'
import type { Asset, ReferenceImageAnalysis } from '@/types'

type ReferenceImagesGalleryProps = {
  brandId: string | null | undefined
  brandName?: string
}

function summaryFromAsset(asset: Asset): string {
  const meta = asset.metadata ?? {}
  if (typeof meta.summary === 'string' && meta.summary.trim()) return meta.summary.trim()
  const analysis = meta.analysis as ReferenceImageAnalysis | undefined
  if (analysis?.summary) return analysis.summary
  if (analysis?.product_description) return analysis.product_description
  return asset.file_name
}

function paletteFromAsset(asset: Asset): string[] {
  const meta = asset.metadata ?? {}
  const analysis = meta.analysis as ReferenceImageAnalysis | undefined
  return Array.isArray(analysis?.color_palette) ? analysis.color_palette : []
}

export default function ReferenceImagesGallery({
  brandId,
  brandName,
}: ReferenceImagesGalleryProps) {
  const [items, setItems] = useState<Asset[]>([])
  const [loading, setLoading] = useState(false)
  const [uploading, setUploading] = useState(false)

  const load = useCallback(async () => {
    if (!brandId) {
      setItems([])
      return
    }
    setLoading(true)
    try {
      const rows = await assetsApi.list({
        brand_id: brandId,
        asset_type: 'reference_image',
      })
      setItems(rows)
    } catch {
      toast.error('Could not load reference images')
      setItems([])
    } finally {
      setLoading(false)
    }
  }, [brandId])

  useEffect(() => {
    void load()
  }, [load])

  const handleUpload = async (files: FileList | null) => {
    if (!files?.length || !brandId) return
    setUploading(true)
    try {
      for (const file of Array.from(files)) {
        await generationApi.analyzeReferenceImage(file, {
          brand_id: brandId,
          brand_name: brandName,
        })
      }
      await load()
      toast.success('Reference image saved')
    } catch (err: unknown) {
      toast.error(extractApiError(err, 'Upload failed'))
    } finally {
      setUploading(false)
    }
  }

  const handleDelete = async (asset: Asset) => {
    if (!confirm('Remove this reference image from Brand Kit?')) return
    try {
      await assetsApi.delete(asset.id)
      setItems((prev) => prev.filter((a) => a.id !== asset.id))
      toast.success('Removed')
    } catch {
      toast.error('Could not delete')
    }
  }

  if (!brandId) {
    return (
      <p className="text-sm text-mid">
        Select a brand to manage reference images for AI generation.
      </p>
    )
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <input
          type="file"
          accept="image/jpeg,image/png,image/webp,.jpg,.jpeg,.png,.webp"
          multiple
          disabled={uploading}
          onChange={(e) => {
            void handleUpload(e.target.files)
            e.target.value = ''
          }}
          className="text-xs text-mid file:mr-3 file:rounded-full file:border file:border-accent/40 file:bg-white file:px-3.5 file:py-2 file:text-xs file:font-semibold file:text-charcoal hover:file:bg-accent/10"
        />
        {uploading && <span className="text-xs text-mid">Analyzing…</span>}
        <Button type="button" size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
          Refresh
        </Button>
      </div>

      {loading ? (
        <p className="text-sm text-mid">Loading reference images…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-mid">
          No reference images yet. Upload product shots or ad examples — AI will read colours and style
          for future image briefs.
        </p>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {items.map((asset) => {
            const url = assetUrl(asset.file_url)
            const palette = paletteFromAsset(asset)
            return (
              <div
                key={asset.id}
                className="rounded-xl border border-border bg-white overflow-hidden shadow-sm"
              >
                {url ? (
                  <div className="relative aspect-video w-full bg-surface-elevated">
                    <img
                      src={url}
                      alt=""
                      className="absolute inset-0 w-full h-full object-cover"
                    />
                  </div>
                ) : (
                  <div className="aspect-video w-full bg-surface-elevated" />
                )}
                <div className="p-3 space-y-2">
                  <p className="text-xs text-charcoal line-clamp-2">{summaryFromAsset(asset)}</p>
                  {palette.length > 0 && (
                    <div className="flex flex-wrap gap-1">
                      {palette.slice(0, 6).map((c) => (
                        <span
                          key={c}
                          className="w-5 h-5 rounded-full border border-border"
                          style={{ background: c }}
                          title={c}
                        />
                      ))}
                    </div>
                  )}
                  <button
                    type="button"
                    className="text-xs text-red-600 hover:underline"
                    onClick={() => void handleDelete(asset)}
                  >
                    Delete
                  </button>
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
