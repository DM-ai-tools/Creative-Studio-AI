import api from './api'

export type LandingPageReference = {
  id: string
  file_name: string
  file_url: string
  width: number
  height: number
}

export type LandingPageAdAsset = {
  asset_id: string
  variant_id: string
  brief_id?: string
  slide_index: number
  role: string
  headline: string
  supporting_copy: string
  cta_text: string
  width: number
  height: number
  preview_url: string
  download_url: string
}

export type LandingPageAdJob = {
  id: string
  created_at?: string
  updated_at?: string
  brief_id?: string | null
  status: 'queued' | 'fetching_page' | 'analysing_page' | 'planning' | 'generating' | 'completed' | 'partial' | 'failed'
  phase: string
  request?: { landing_page_url?: string; user_prompt?: string; image_model?: string }
  error?: string | null
  warnings?: string[]
  progress?: { completed_assets: number; total_assets: number }
  analysis?: {
    title?: string
    description?: string
    final_url?: string
    headings?: string[]
    evidence?: Array<{ id: string; text?: string; excerpt?: string; kind?: string; type?: string }>
    brand?: { name?: string; primary_color?: string; secondary_color?: string; logo_url?: string }
  }
  resolved_brief?: {
    format: string
    ratio: string
    width: number
    height: number
    asset_count: number
    platform: string
    no_humans: boolean
  }
  assets?: LandingPageAdAsset[]
  download_all_url?: string | null
}

export const landingPageAdsApi = {
  uploadReferences: async (files: File[], brandId?: string) => {
    const form = new FormData()
    files.forEach((file) => form.append('files', file))
    if (brandId) form.append('brand_id', brandId)
    return api.post<LandingPageReference[]>('/landing-page-ads/references', form).then((r) => r.data)
  },
  createJob: (payload: {
    landing_page_url: string
    user_prompt: string
    reference_asset_ids: string[]
    brand_id?: string
    image_model: string
  }) => api.post<LandingPageAdJob>('/landing-page-ads/jobs', payload).then((r) => r.data),
  getJob: (jobId: string) => api.get<LandingPageAdJob>(`/landing-page-ads/jobs/${jobId}`).then((r) => r.data),
  listJobs: () => api.get<LandingPageAdJob[]>('/landing-page-ads/jobs').then((r) => r.data),
  revise: (jobId: string, payload: { user_prompt: string; target_slide_indexes: number[] }) =>
    api.post<LandingPageAdJob>(`/landing-page-ads/jobs/${jobId}/revisions`, payload).then((r) => r.data),
}
