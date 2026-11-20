import axios, { AxiosInstance, AxiosError } from 'axios'
import { authStorage } from './auth'
import type {
  AdminClient, AdminStats, AdminUsage, Asset, AvatarScriptResult, BrandFacts, IcpImagePlanResult, IcpScriptResult, ModelSuggestion, PerformanceStatsContext, PricingConfig, PricingRates, SeedanceCreditsCheck, UsageAllowance,
  SuggestAdAnglesResult, StrategyParseResult, WebsiteBrandFetchResult,
  StatsImageExtractionResult, StrategyPreviewResult, ReferenceImageAnalysisResult,
  WebsiteScriptResult, Brand, BrandKit, Brief, DashboardStats, FatigueAlert,
  GenerationCatalog, GenerationModelOption, MetaExportResponse, MetaStatus, PerformanceMetric, TokenResponse,
  TopPerformer, User, Variant, EmailTemplate, CreativeStudioScriptPlan, CreativeStudioEndCardResult, CreativeStudioStillResult, CreativeStudioStillLogoResult, CreativeStudioInsertsResult,
} from '@/types'

const API_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

const api: AxiosInstance = axios.create({
  baseURL: API_URL,
  headers: { 'Content-Type': 'application/json' },
})

api.interceptors.request.use((config) => {
  const token = authStorage.getAccessToken()
  if (token) config.headers.Authorization = `Bearer ${token}`
  // Let the browser set multipart boundary; a bare "multipart/form-data" header breaks uploads.
  if (config.data instanceof FormData) {
    if (typeof config.headers.delete === 'function') {
      config.headers.delete('Content-Type')
    } else {
      delete config.headers['Content-Type']
    }
  }
  return config
})

api.interceptors.response.use(
  (res) => res,
  async (error: AxiosError) => {
    if (error.response?.status === 401) {
      const refresh = authStorage.getRefreshToken()
      if (refresh) {
        try {
          const res = await axios.post<TokenResponse>(`${API_URL}/auth/refresh`, { refresh_token: refresh })
          authStorage.setTokens(res.data.access_token, res.data.refresh_token)
          if (error.config) {
            error.config.headers.Authorization = `Bearer ${res.data.access_token}`
            return api.request(error.config)
          }
        } catch {
          authStorage.clear()
          if (typeof window !== 'undefined') window.location.href = '/login'
        }
      } else {
        authStorage.clear()
        if (typeof window !== 'undefined') window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

// ── Auth ──────────────────────────────────────────────────────────────────────
export const authApi = {
  register: (data: { email: string; password: string; full_name: string; tenant_name: string }) =>
    api.post<TokenResponse>('/auth/register', data).then((r) => r.data),

  login: (data: { email: string; password: string }) =>
    api.post<TokenResponse>('/auth/login', data).then((r) => r.data),

  refresh: (refresh_token: string) =>
    api.post<TokenResponse>('/auth/refresh', { refresh_token }).then((r) => r.data),

  getMe: () => api.get<User>('/auth/me').then((r) => r.data),

  logout: () => api.post('/auth/logout').then((r) => r.data),
}

// ── Brands ────────────────────────────────────────────────────────────────────
export const brandsApi = {
  list: () => api.get<Brand[]>('/brands/').then((r) => r.data),

  get: (id: string) => api.get<Brand>(`/brands/${id}`).then((r) => r.data),

  create: (data: Partial<Brand>) => api.post<Brand>('/brands/', data).then((r) => r.data),

  update: (id: string, data: Partial<Brand>) =>
    api.put<Brand>(`/brands/${id}`, data).then((r) => r.data),

  delete: (id: string) => api.delete(`/brands/${id}`),

  getKit: (brandId: string) =>
    api.get<BrandKit>(`/brands/${brandId}/kit`).then((r) => r.data),

  createKit: (brandId: string, data: Partial<BrandKit>) =>
    api.post<BrandKit>(`/brands/${brandId}/kit`, data).then((r) => r.data),

  updateKit: (brandId: string, kitId: string, data: Partial<BrandKit>) =>
    api.put<BrandKit>(`/brands/${brandId}/kit/${kitId}`, data).then((r) => r.data),

  uploadLogo: (brandId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<Brand>(`/brands/${brandId}/logo`, form).then((r) => r.data)
  },

  uploadLogoOnLight: (brandId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<BrandKit>(`/brands/${brandId}/logo/on-light`, form).then((r) => r.data)
  },

  fetchSocialStyle: (
    brandId: string,
    data: { handle_or_url: string; platform?: string }
  ) =>
    api
      .post<{ brand_id: string; social_style_profile: import('@/types').SocialStyleProfile; message: string }>(
        `/brands/${brandId}/fetch-social-style`,
        data,
        { timeout: 120_000 }
      )
      .then((r) => r.data),

  fetchCompetitorSocial: (
    brandId: string,
    data: { handle_or_url: string; platform?: string; industry?: string; niche?: string }
  ) =>
    api
      .post<{
        brand_id: string
        competitor_insight: import('@/types').CompetitorSocialInsight
        competitor_social_insights: import('@/types').CompetitorSocialInsight[]
        message: string
      }>(`/brands/${brandId}/fetch-competitor-social`, data, { timeout: 120_000 })
      .then((r) => r.data),

  deleteCompetitorSocial: (
    brandId: string,
    params: { handle: string; platform?: string }
  ) =>
    api
      .delete<{
        brand_id: string
        competitor_social_insights: import('@/types').CompetitorSocialInsight[]
        message: string
      }>(`/brands/${brandId}/competitor-social`, { params })
      .then((r) => r.data),

  discoverCompetitors: (
    brandId: string,
    data: {
      handle_or_url?: string
      platform?: string
      industry?: string
      niche?: string
      geography?: string
    }
  ) =>
    api
      .post<{
        brand_id: string
        competitor_candidates: import('@/types').CompetitorCandidate[]
        message: string
      }>(`/brands/${brandId}/discover-competitors`, data, { timeout: 120_000 })
      .then((r) => r.data),
}

export type EmailLayoutBase = {
  label: string
  layout_image_url?: string | null
  layout_asset_id?: string | null
  layout_html?: string | null
  updated_at?: string | null
}

export type EmailImportSlot = {
  id: string
  kind: 'img' | 'background'
  src: string
  alt: string
  display_width: number | null
  display_height: number | null
  plan_width: number
  plan_height: number
  size_assumed: boolean
  aspect: number
  role: 'hero' | 'banner' | 'product' | 'content' | 'logo' | 'icon' | 'tracking' | 'other'
  replaceable: boolean
  reason: string | null
  context_text: string
  is_inline_data: boolean
}

export type EmailImportAnalysis = {
  slots: EmailImportSlot[]
  slot_count: number
  replaceable_count: number
  merge_tags: string[]
  html_length: number
}

export type EmailImportImage = {
  slot_id: string
  url: string
  absolute_url: string
  width: number
  height: number
  display_width: number
  display_height: number
  file_size: number
  prompt: string
}

export type EmailImportExport = {
  html: string
  applied: string[]
  skipped: { id: string; reason: string }[]
  warnings: string[]
}

export const emailTemplatesApi = {
  /** Find the image spots in the customer's own HTML email. Changes nothing. */
  analyzeImport: (html: string) =>
    api.post<EmailImportAnalysis>('/email-templates/import/analyze', { html }).then((r) => r.data),
  /** Generate one picture cropped to the exact shape of one image spot. */
  generateImportImage: (data: {
    brand_id?: string | null
    campaign_name?: string
    slot_id: string
    role: string
    width: number
    height: number
    description?: string
    alt?: string
    context_text?: string
    notes?: string
    image_model: string
  }) => api.post<EmailImportImage>('/email-templates/import/generate-image', data, { timeout: 300_000 }).then((r) => r.data),
  /** The customer's HTML with only the chosen image addresses swapped. */
  exportImport: (html: string, replacements: Record<string, string>) =>
    api.post<EmailImportExport>('/email-templates/import/export', { html, replacements }).then((r) => r.data),
  list: () => api.get<EmailTemplate[]>('/email-templates').then((r) => r.data),
  get: (id: string) => api.get<EmailTemplate>(`/email-templates/${id}`).then((r) => r.data),
  getLayoutBase: () => api.get<EmailLayoutBase>('/email-templates/layout-base').then((r) => r.data),
  saveLayoutBase: (data: {
    label?: string
    layout_image_url?: string | null
    layout_asset_id?: string | null
    layout_html?: string | null
  }) => api.put<EmailLayoutBase>('/email-templates/layout-base', data).then((r) => r.data),
  generate: (data: {
    brand_id?: string | null
    campaign_name: string
    email_type: string
    audience: string
    offer: string
    landing_page_url?: string | null
    notes: string
    image_model: string
    use_layout_base?: boolean
    hero_mode?: 'generate_from_layout' | 'use_layout_image' | 'generate'
  }) => api.post<EmailTemplate>('/email-templates/generate', data, { timeout: 300_000 }).then((r) => r.data),
  update: (id: string, data: Pick<EmailTemplate, 'campaign_name' | 'email_type' | 'subject' | 'preheader' | 'content'>) =>
    api.put<EmailTemplate>(`/email-templates/${id}`, data).then((r) => r.data),
  delete: (id: string) => api.delete(`/email-templates/${id}`),
}

// ── Briefs ────────────────────────────────────────────────────────────────────
export const briefsApi = {
  list: (params?: { status?: string; limit?: number; offset?: number }) =>
    api.get<Brief[]>('/briefs/', { params }).then((r) => r.data),

  get: (id: string) => api.get<Brief>(`/briefs/${id}`).then((r) => r.data),

  create: (data: Partial<Brief>) => api.post<Brief>('/briefs/', data).then((r) => r.data),

  update: (id: string, data: Partial<Brief>) =>
    api.put<Brief>(`/briefs/${id}`, data).then((r) => r.data),

  delete: (id: string) => api.delete(`/briefs/${id}`),

  submit: (id: string) => api.post<Brief>(`/briefs/${id}/submit`).then((r) => r.data),

  generate: (
    id: string,
    data: {
      formats?: string[]
      count_per_format?: number
      ai_model?: string
      image_model?: string
      video_model?: string
      video_duration_seconds?: number
      heygen_avatar_id?: string
      heygen_voice_id?: string
      higgsfield_voice_preset?: string
      avatar_script?: string
      heygen_settings?: Record<string, unknown>
    }
  ) =>
    api
      .post<{ message: string; variants_created: number; status?: string }>(
        `/briefs/${id}/generate`,
        data,
        // Generation is background now; short timeout is fine — job continues on server.
        { timeout: 60_000 }
      )
      .then((r) => r.data),

  uploadScriptPdf: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<{ character_count: number; preview: string; filename: string }>(
        `/briefs/${id}/script-pdf`,
        form,
        { timeout: 120_000 }
      )
      .then((r) => r.data)
  },

  clearScriptPdf: (id: string) => api.delete<Brief>(`/briefs/${id}/script-pdf`).then((r) => r.data),
}

// ── Variants ──────────────────────────────────────────────────────────────────
export const variantsApi = {
  list: (params?: {
    brief_id?: string
    status?: string
    compliance_status?: string
    limit?: number
    offset?: number
  }) =>
    api.get<Variant[]>('/variants/', { params, timeout: 60_000 }).then((r) => r.data),

  get: (id: string) => api.get<Variant>(`/variants/${id}`).then((r) => r.data),

  update: (id: string, data: Partial<Variant>) =>
    api.put<Variant>(`/variants/${id}`, data).then((r) => r.data),

  approve: (id: string) => api.post<Variant>(`/variants/${id}/approve`).then((r) => r.data),

  reject: (id: string) => api.post<Variant>(`/variants/${id}/reject`).then((r) => r.data),

  regenerate: (id: string) => api.post<Variant>(`/variants/${id}/regenerate`).then((r) => r.data),

  /** Retry ONLY this variant's still image — does not regenerate siblings. */
  regenerateImage: (id: string, data?: { image_model?: string }) =>
    api
      .post<Variant>(`/variants/${id}/regenerate-image`, data ?? {}, { timeout: 30_000 })
      .then((r) => r.data),

  /** Put the Brand Kit logo on a finished still exactly at `corner` (no AI, no credits). */
  placeLogo: (id: string, corner: string, backing: '' | 'over' | 'plate' | 'bar' = '') =>
    api.post<Variant>(`/variants/${id}/place-logo`, { corner, backing }, { timeout: 60_000 }).then((r) => r.data),

  delete: (id: string) => api.delete(`/variants/${id}`),

  /** Save Creative Studio (or other) media URL into the Variants library. */
  createFromMedia: (data: {
    media_url: string
    media_mode?: 'image' | 'video' | 'storyboard'
    aspect?: string
    model?: string
    prompt?: string
    duration_seconds?: number | null
    seed_image_url?: string | null
    brief_id?: string | null
    brand_id?: string | null
    brief_title?: string | null
    product_name?: string
  }) =>
    api.post<Variant>('/variants/from-media', data, { timeout: 30_000 }).then((r) => r.data),

  getFatigueAlerts: () =>
    api.get<FatigueAlert[]>('/variants/fatigue-alerts').then((r) => r.data),
}

// ── Assets ────────────────────────────────────────────────────────────────────
export const assetsApi = {
  upload: (
    file: File,
    variantId?: string,
    assetType: string = 'image',
    brandId?: string,
  ) => {
    const form = new FormData()
    form.append('file', file)
    if (variantId) form.append('variant_id', variantId)
    form.append('asset_type', assetType)
    if (brandId) form.append('brand_id', brandId)
    return api.post<Asset>('/assets/upload', form).then((r) => r.data)
  },

  list: (params?: { variant_id?: string; brand_id?: string; asset_type?: string }) =>
    api.get<Asset[]>('/assets/', { params }).then((r) => r.data),

  registerGenerated: (data: {
    file_url: string
    brand_id?: string
    file_name?: string
    metadata?: Record<string, unknown>
  }) => api.post<Asset>('/assets/register-generated', data).then((r) => r.data),

  updateMetadata: (id: string, metadata: Record<string, unknown>) =>
    api.patch<Asset>(`/assets/${id}/metadata`, { metadata }).then((r) => r.data),

  delete: (id: string) => api.delete(`/assets/${id}`),
}

// ── Performance ───────────────────────────────────────────────────────────────
export const performanceApi = {
  getDashboardStats: () =>
    api.get<DashboardStats>('/performance/dashboard').then((r) => r.data),

  getTopPerformers: (limit = 10) =>
    api.get<TopPerformer[]>('/performance/top-performers', { params: { limit } }).then((r) => r.data),

  getFatigueAlerts: () =>
    api.get<FatigueAlert[]>('/performance/fatigue-alerts').then((r) => r.data),

  getVariantMetrics: (variantId: string, days = 30) =>
    api
      .get<PerformanceMetric[]>(`/performance/variants/${variantId}/metrics`, { params: { days } })
      .then((r) => r.data),
}

// ── Generation catalog ───────────────────────────────────────────────────────
export const generationApi = {
  getCatalog: (refresh = false) =>
    api
      .get<GenerationCatalog>('/generation/catalog', {
        timeout: 45_000,
        params: refresh ? { refresh: true } : undefined,
      })
      .then((r) => r.data),

  getVoices: () =>
    api
      .get<{ voices: { id: string; label: string; gender?: string | null; language?: string | null; preview_url?: string | null }[] }>('/generation/voices', { timeout: 20_000 })
      .then((r) => r.data.voices),

  previewVoice: (voiceId: string, text?: string) =>
    api
      .get<{ audio_url: string }>('/generation/voice-preview', {
        params: { voice_id: voiceId, ...(text ? { text } : {}) },
        timeout: 30_000,
      })
      .then((r) => r.data.audio_url),

  createPhotoAvatar: (photo: File, name: string) => {
    const form = new FormData()
    form.append('photo', photo)
    form.append('name', name)
    return api
      .post<{ photo_avatar_id: string; status: string; look_id: string | null; name: string }>(
        '/generation/photo-avatar',
        form,
        { timeout: 60_000 },
      )
      .then((r) => r.data)
  },

  getPhotoAvatarStatus: (photoAvatarId: string) =>
    api
      .get<{ photo_avatar_id: string; status: string; look_id: string | null; name: string; error?: string | null }>(
        `/generation/photo-avatar/${photoAvatarId}`,
        { timeout: 20_000 },
      )
      .then((r) => r.data),

  generateAvatarScript: (data: {
    script_prompt?: string
    product_name?: string
    offer?: string
    brand_name?: string
    target_audience?: string
    ad_copy_tone?: string
    cta?: string
    notes?: string
    target_seconds?: number
    avatar_label?: string
    voice_label?: string
    forbidden_words?: string[]
    variation?: 'default' | 'different_hook'
    purpose?: 'avatar_script' | 'brief_notes' | 'visual_cues' | 'scene_broll'
    performance_stats?: PerformanceStatsContext
    performance_stats_per_image?: PerformanceStatsContext[]
    source_script?: string
    stats_image_count?: number
    approved_script?: string
    scene_label?: string
    scene_custom?: string
  }) =>
    api
      .post<AvatarScriptResult>('/generation/avatar-script', data, { timeout: 120_000 })
      .then((r) => r.data),

  masterScriptPreview: (data: {
    avatar_script: string
    scene_broll_directions?: string
    target_seconds?: number
    performance_stats_per_image?: PerformanceStatsContext[]
  }) =>
    api
      .post<{
        beats: {
          start: string
          end: string
          spoken: string
          visual: string
          stat_image?: string | null
          stat_headline?: string | null
          stat_warning?: string | null
        }[]
        warnings: string[]
        ready: boolean
      }>('/generation/master-script-preview', data, { timeout: 30_000 })
      .then((r) => r.data),

  suggestModels: (data: {
    campaign_name?: string
    objective?: string
    formats?: string[]
    target_audience?: string
    offer?: string
    product_name?: string
    ad_copy_tone?: string
    cta?: string
    duration_seconds?: number
    brand_name?: string
  }) =>
    api
      .post<ModelSuggestion>('/generation/suggest-models', data, { timeout: 60_000 })
      .then((r) => r.data),

  generateStrategyPreview: (data: {
    campaign_name?: string
    brand_name?: string
    product_name?: string
    offer?: string
    target_audience?: string
    ad_copy_tone?: string
    cta?: string
    target_seconds?: number
    hook_frameworks?: string[]
    competitors?: string[]
    objective?: string
    placements?: string[]
    formats?: string[]
    website_url?: string
  }) =>
    api
      .post<StrategyPreviewResult>('/generation/strategy-preview', data, { timeout: 120_000 })
      .then((r) => r.data),

  generateWebsiteScript: (data: {
    url: string
    target_seconds?: number
    brand_name?: string
    product_name?: string
    offer?: string
    ad_copy_tone?: string
    cta?: string
    target_audience?: string
    avatar_label?: string
    voice_label?: string
    forbidden_words?: string[]
    variation?: 'default' | 'different_hook'
    performance_stats?: PerformanceStatsContext
    performance_stats_per_image?: PerformanceStatsContext[]
    stats_image_count?: number
  }) =>
    api
      .post<WebsiteScriptResult>('/generation/website-script', data, { timeout: 120_000 })
      .then((r) => r.data),

  extractStatsFromImage: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<StatsImageExtractionResult>('/generation/extract-stats-image', form, {
        timeout: 120_000,
      })
      .then((r) => r.data)
  },

  analyzeReferenceImage: (
    file: File,
    opts?: { brand_id?: string; brand_name?: string; niche?: string },
  ) => {
    const form = new FormData()
    form.append('file', file)
    if (opts?.brand_id) form.append('brand_id', opts.brand_id)
    if (opts?.brand_name) form.append('brand_name', opts.brand_name)
    if (opts?.niche) form.append('niche', opts.niche)
    return api
      .post<ReferenceImageAnalysisResult>('/generation/analyze-reference-image', form, {
        timeout: 120_000,
      })
      .then((r) => r.data)
  },

  fetchProductReference: (data: {
    source: string
    brand_id: string
    brand_name?: string
    niche?: string
  }) =>
    api
      .post<ReferenceImageAnalysisResult>('/generation/product-reference', data, {
        timeout: 120_000,
      })
      .then((r) => r.data),

  generateHeroAiImage: (
    file: File,
    data: {
      brand_name?: string
      industry?: string
      niche?: string
      product_name?: string
      hook?: string
      headline?: string
      model?: string
      logo_url?: string
      logo_on_light_url?: string
      prompt?: string
      generate_image?: boolean
    },
  ) => {
    const form = new FormData()
    form.append('file', file)
    Object.entries(data).forEach(([key, value]) => {
      if (value !== undefined && value !== '') form.append(key, String(value))
    })
    return api
      .post<{ image_url: string; hook: string; headline: string; prompt: string }>(
        '/generation/hero-ai-image',
        form,
        { timeout: 300_000 },
      )
      .then((r) => r.data)
  },

  previewImagePlan: (data: {
    brand_name?: string
    industry?: string
    product_name?: string
    offer?: string
    target_audience?: string
    ad_copy_tone?: string
    objective_id?: string
    cta?: string
    image_aspect_ratio?: string
    image_use_cases?: string[]
    image_prompt_override?: string
    notes?: string
    hook?: string
    headline?: string
    body_copy?: string
  }) =>
    api
      .post<{ use_cases: string[]; prompt: string; reasoning: string }>('/generation/preview-image-plan', data, { timeout: 60_000 })
      .then((r) => r.data),

  previewIcpImagePlan: (data: {
    campaign_name: string
    brand_id?: string
    brand_name?: string
    industry?: string
    niche?: string
    objective_id?: string
    cta?: string
    offer?: string
    geography?: string
    brand_facts?: BrandFacts | null
    image_aspect_ratio?: string
    hook_frameworks?: string[]
    variant_count?: number
    existing_hooks?: string[]
    existing_prompts?: string[]
    creative_format?: 'static' | 'carousel' | 'mixed' | string
    strategy_notes?: string
    product_focus?: string
    image_visual_style?: string
    primary_color?: string
    secondary_color?: string
    font_heading?: string
    font_body?: string
    social_style_profile?: import('@/types').SocialStyleProfile | null
    use_competitor_insights?: boolean
    competitor_social_insights?: import('@/types').CompetitorSocialInsight[] | null
    reference_images?: Array<{
      asset_id?: string
      file_url?: string
      analysis?: import('@/types').ReferenceImageAnalysis
      is_product_reference?: boolean
    }>
    exact_product_reference?: boolean
    strategy_variants?: Array<{
      id?: string
      format?: string
      ad_angle?: string
      scene?: string
      prompt?: string
      client_hook?: string
      client_message?: string
      carousel_index?: number
      carousel_total?: number
      carousel_group?: string
    }>
    llm_model?: string
  }) => {
    const count = Math.max(1, data.variant_count ?? 1)
    const timeout = Math.min(600_000, 120_000 + count * 20_000)
    return api
      .post<IcpImagePlanResult>('/generation/icp-image-plan', data, { timeout })
      .then((r) => r.data)
  },

  suggestAdAngles: (data: {
    campaign_name: string
    brand_name?: string
    industry?: string
    niche?: string
    objective_id?: string
    variant_count?: number
  }) =>
    api
      .post<SuggestAdAnglesResult>('/generation/suggest-ad-angles', data, { timeout: 90_000 })
      .then((r) => r.data),

  fetchBrandFromUrl: (data: { url: string }) =>
    api
      .post<WebsiteBrandFetchResult>('/generation/fetch-brand-from-url', data, { timeout: 120_000 })
      .then((r) => r.data),

  parseStrategyFile: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<StrategyParseResult>('/generation/parse-strategy', form, { timeout: 180_000 })
      .then((r) => r.data)
  },

  generateImagePrompt: (data: {
    product_name?: string
    brand_name?: string
    offer?: string
    target_audience?: string
    ad_copy_tone?: string
    image_use_cases?: string[]
    image_aspect_ratio?: string
    forbidden_words?: string[]
    user_prompt?: string
  }) =>
    api
      .post<{ prompt: string }>('/generation/image-prompt', data, { timeout: 60_000 })
      .then((r) => r.data),

  generateIcpScript: (data: {
    target_audience?: string
    offer?: string
    product_name?: string
    brand_name?: string
    ad_copy_tone?: string
    cta?: string
    target_seconds?: number
    avatar_label?: string
    voice_label?: string
    forbidden_words?: string[]
    variation?: 'default' | 'different_hook'
    performance_stats?: PerformanceStatsContext
    performance_stats_per_image?: PerformanceStatsContext[]
    stats_image_count?: number
    source_script?: string
  }) =>
    api
      .post<IcpScriptResult>('/generation/icp-script', data, { timeout: 180_000 })
      .then((r) => r.data),

  creativeStudioGenerate: (data: {
    media_mode: 'image' | 'video'
    model: string
    prompt: string
    duration_seconds?: number
    aspect?: string
    resolution?: string
    sound_on?: boolean
    speech_mode?: 'native_presenter' | 'external_voiceover'
    video_reference_mode?: 'reference' | 'edit'
    negative_prompt?: string
    brand_name?: string
    brand_id?: string
    brief_id?: string
  }) =>
    api
      .post<{
        status: string
        job_id?: string | null
        progress?: string | null
        url?: string | null
        model?: string | null
        provider?: string | null
        error?: string | null
        seed_image_url?: string | null
        duration_seconds?: number | null
        requested_duration_seconds?: number | null
        segment_count?: number | null
        continuity_chained?: boolean
        continuity_frame_count?: number | null
        partial?: boolean
        continuation_available?: boolean
        completed_segments?: number | null
        credits_estimate?: number | null
        duration_warning?: string | null
        note?: string | null
        production_id?: string | null
        production_report?: Record<string, unknown> | null
        quality_gate?: Record<string, unknown> | null
        retry_chapter_available?: boolean
        continuity_video_reference_url?: string | null
        credential_family?: string | null
        credential_fingerprint?: string | null
      }>('/generation/creative-studio', data, { timeout: 60_000 })
      .then((r) => r.data),

  creativeStudioJob: (jobId: string) =>
    api
      .get<{
        status: string
        audio_present?: boolean | null
        audio_warning?: string | null
        voiceover?: { status?: string; reason?: string; error?: string } | null
        provider_usage?: { task_id: string; total_tokens?: number | null; cost_usd?: number | null; cost_status: string }[] | null
        job_id?: string | null
        progress?: string | null
        url?: string | null
        model?: string | null
        provider?: string | null
        error?: string | null
        seed_image_url?: string | null
        duration_seconds?: number | null
        requested_duration_seconds?: number | null
        segment_count?: number | null
        continuity_chained?: boolean
        continuity_frame_count?: number | null
        partial?: boolean
        continuation_available?: boolean
        next_chapter_image_available?: boolean
        continuity_reference_url?: string | null
        staged_segment_paths?: string[] | null
        chapter_index?: number | null
        film_total_chapters?: number | null
        broll_index?: number | null
        broll_title?: string | null
        byteplus_url?: string | null
        trusted_video_model?: string | null
        completed_segments?: number | null
        credits_estimate?: number | null
        duration_warning?: string | null
        note?: string | null
        production_id?: string | null
        production_report?: Record<string, unknown> | null
        quality_gate?: Record<string, unknown> | null
        retry_chapter_available?: boolean
        continuity_video_reference_url?: string | null
        credential_family?: string | null
        credential_fingerprint?: string | null
        storyboard?: {
          id?: string
          index?: number
          title?: string
          url?: string | null
          image_prompt?: string
          overlays?: string[]
          status?: string
          error?: string | null
        }[]
        media_mode?: string | null
        asset_role?: string | null
        clone_mode?: boolean
        character_reference_url?: string | null
      }>(`/generation/creative-studio/jobs/${encodeURIComponent(jobId)}`, {
        timeout: 30_000,
      })
      .then((r) => r.data),

  creativeStudioContinueJob: (
    jobId: string,
    recovery?: {
      part_video_url?: string
      completed_segments?: number
      segment_count?: number
      payload?: Record<string, unknown>
      generated_duration_seconds?: number
      continuity_frame_count?: number
      cast_reference_url?: string
      continuity_reference_url?: string
      continuity_video_reference_url?: string
      credential_family?: string
      credential_fingerprint?: string
      production_id?: string
      next_prompt?: string
      next_reference_assets?: {
        url: string
        role: 'product' | 'logo' | 'scene' | 'character' | 'reference' | 'proof' | 'reference_video'
        name?: string
      }[]
      next_reference_mode?: 'continuity' | 'first_frame'
      next_seed_image_url?: string
    },
  ) =>
    api
      .post<{
        status: string
        job_id?: string | null
        progress?: string | null
        error?: string | null
      }>(
        `/generation/creative-studio/jobs/${encodeURIComponent(jobId)}/continue`,
        recovery || {},
        {
          timeout: 30_000,
        },
      )
      .then((r) => r.data),

  creativeStudioCancelJob: (jobId: string) =>
    api
      .post<{
        status: string
        job_id?: string | null
        progress?: string | null
        error?: string | null
      }>(`/generation/creative-studio/jobs/${encodeURIComponent(jobId)}/cancel`, {}, {
        timeout: 30_000,
      })
      .then((r) => r.data),

  creativeStudioNiches: () =>
    api
      .get<{ id: string; label: string }[]>('/generation/creative-studio/niches', {
        timeout: 15_000,
      })
      .then((r) => r.data),

  creativeStudioCloneScenes: () =>
    api
      .get<{
        categories: { id: string; label: string }[]
        scenes: { id: string; category: string; title: string; description: string }[]
      }>('/generation/creative-studio/clone-scenes', { timeout: 15_000 })
      .then((r) => r.data),

  creativeStudioModels: () =>
    api
      .get<{
        configured: boolean
        chat_models?: GenerationModelOption[]
        default_chat_model?: string | null
        image_model_default?: string | null
        video_model_default?: string | null
        image_models: GenerationModelOption[]
        /** GPT Image 2 + BytePlus Seedream stills for image-first workflow */
        still_models?: GenerationModelOption[]
        video_models: GenerationModelOption[]
        message?: string | null
      }>('/generation/creative-studio/models', { timeout: 20_000 })
      .then((r) => r.data),

  creativeStudioPdfReference: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<{
        name: string
        pdf_url: string
        page_count: number
        text: string
        pages: {
          page_number: number
          image_url: string
          width: number
          height: number
          text: string
        }[]
        visual_pages_truncated: boolean
      }>('/generation/creative-studio/pdf-reference', form, { timeout: 300_000 })
      .then((r) => r.data)
  },

  /** Script mode: read a Word/text script and compile the timed prompt Creative Studio already uses. */
  creativeStudioScriptPlan: (args: {
    file?: File | null
    scriptText?: string
    chatModel?: string
    videoModel?: string
    aspect?: string
    speechMode?: string
    brandId?: string
    brandName?: string
    productName?: string
    notes?: string
  }) => {
    const form = new FormData()
    if (args.file) form.append('file', args.file)
    form.append('script_text', args.scriptText || '')
    form.append('chat_model', args.chatModel || 'auto')
    form.append('video_model', args.videoModel || '')
    form.append('aspect', args.aspect || '9/16')
    form.append('speech_mode', args.speechMode || 'native_presenter')
    form.append('brand_id', args.brandId || '')
    form.append('brand_name', args.brandName || '')
    form.append('product_name', args.productName || '')
    form.append('notes', args.notes || '')
    return api
      .post<CreativeStudioScriptPlan>('/generation/creative-studio/script/plan', form, {
        timeout: 240_000,
      })
      .then((r) => r.data)
  },

  creativeStudioChat: (data: {
    messages: { role: 'user' | 'assistant'; content: string }[]
    mode?: 'auto' | 'ask' | 'generate'
    chat_model?: string
    duration_seconds?: number
    aspect?: string
    resolution?: string
    sound_on?: boolean
    speech_mode?: 'native_presenter' | 'external_voiceover'
    video_reference_mode?: 'reference' | 'edit'
    attachment_urls?: string[]
    brand_name?: string
    brand_id?: string
    brief_id?: string
    product_name?: string
    action?:
      | 'continue'
      | 'generate_image'
      | 'regenerate_image'
      | 'approve_next'
      | 'generate_video'
      | 'generate_storyboard'
      | 'generate_next_chapter_image'
      | 'generate_broll_image'
      | 'generate_all_broll'
      | 'regenerate_broll_image'
      | 'approve_broll'
      | 'approve_all_broll'
    image_prompt?: string
    video_prompt?: string
    approved_image_url?: string
    product_reference_url?: string
    logo_reference_url?: string
    additional_reference_urls?: string[]
    reference_assets?: { url: string; role: 'product' | 'logo' | 'scene' | 'character' | 'reference' | 'proof' | 'reference_video' }[]
    document_references?: {
      name: string
      pdf_url: string
      text: string
      page_image_urls: string[]
    }[]
    storyboard_image_urls?: string[]
    prompt_only_video?: boolean
    preserve_image_text?: boolean
    image_model?: string
    revision_notes?: string
    phase?: string
    video_model?: string
    session_id?: string
    chapter_index?: number
    continuity_style_url?: string
    accumulated_segment_paths?: string[]
    broll_index?: number
    approved_broll_url?: string
    approved_broll_byteplus_url?: string
    broll_board_approvals?: { index: number; url: string; byteplus_url?: string }[]
    clone_mode?: boolean
    clone_scene_id?: string
    clone_count?: number
  }) =>
    api
      .post<{
        assistant_message: string
        intent: string
        phase?: string | null
        suggested_actions?: string[]
        chat_model?: string | null
        image_model?: string | null
        video_model?: string | null
        job_id?: string | null
        status: string
        media_mode?: string | null
        model?: string | null
        image_prompt?: string | null
        video_prompt?: string | null
        approved_image_url?: string | null
        product_reference_url?: string | null
        storyboard_scenes?: {
          id?: string
          index?: number
          title?: string
          image_prompt?: string
          overlays?: string[]
        }[]
        duration_seconds?: number | null
        aspect?: string | null
        chapter_index?: number | null
        film_total_chapters?: number | null
        broll_index?: number | null
        error?: string | null
      }>('/generation/creative-studio/chat', data, { timeout: 120_000 })
      .then((r) => r.data),

  /** Burn captions and the brand logo onto a copy of a finished Creative Studio video. */
  creativeStudioFinishVideo: (data: {
    video_url: string
    script: string
    logo_url?: string | null
    logo_on_light_url?: string | null
    add_captions?: boolean
    add_logo?: boolean
  }) =>
    api
      .post<{
        url: string
        source_url: string
        captions_applied: boolean
        caption_count: number
        logo_applied: boolean
        width: number
        height: number
        duration_seconds: number
        warnings: string[]
      }>('/generation/creative-studio/finish-video', data, { timeout: 600_000 })
      .then((r) => r.data),

  /** Draw one still (a screen, page or graphic) with GPT Image 2 or Seedream. Uses one image generation. */
  creativeStudioStill: (data: {
    prompt: string
    model: string
    aspect?: string
    brand_id?: string
    brand_name?: string
    /** Corner kept empty in the picture for the logo. Empty or omitted = no logo. */
    logo_corner?: string
  }) =>
    api
      .post<CreativeStudioStillResult>('/generation/creative-studio/still', data, { timeout: 300_000 })
      .then((r) => r.data),

  /** Place the brand logo inside a drawn picture, in a chosen corner (no AI, no credits). */
  creativeStudioStillLogo: (data: {
    image_url: string
    corner: string
    logo_url?: string | null
    logo_on_light_url?: string | null
  }) =>
    api
      .post<CreativeStudioStillLogoResult>('/generation/creative-studio/still-logo', data, { timeout: 60_000 })
      .then((r) => r.data),

  /** Lay approved still pictures over a finished video at the given seconds (no AI, no credits). */
  creativeStudioInserts: (data: {
    video_url: string
    inserts: { image_url: string; start_seconds: number; duration_seconds: number }[]
    zoom?: boolean
  }) =>
    api
      .post<CreativeStudioInsertsResult>('/generation/creative-studio/inserts', data, { timeout: 600_000 })
      .then((r) => r.data),

  /** Lay the brand logo and exact call-to-action text over the last seconds of a finished video (no AI, no credits). */
  creativeStudioEndCard: (data: {
    video_url: string
    headline: string
    sublines?: string[]
    button_text?: string
    logo_url?: string | null
    button_hex?: string | null
    accent_hex?: string | null
    hold_seconds?: number
    preview?: boolean
  }) =>
    api
      .post<CreativeStudioEndCardResult>('/generation/creative-studio/end-card', data, { timeout: 600_000 })
      .then((r) => r.data),

  creativeStudioPrompt: (data: {
    niche: string
    media_mode?: 'image' | 'video'
    duration_seconds?: number
    style?: string
    genre?: string
    camera?: string
    aspect?: string
    product_name?: string
    brand_name?: string
    notes?: string
  }) =>
    api
      .post<{ prompt: string; niche: string }>('/generation/creative-studio/prompt', data, {
        timeout: 90_000,
      })
      .then((r) => r.data),
}

// ── Meta Ads export ───────────────────────────────────────────────────────────
export const metaApi = {
  getStatus: () => api.get<MetaStatus>('/meta/status').then((r) => r.data),

  exportVariants: (data: {
    variant_ids: string[]
    campaign_name: string
    ad_set_name?: string
  }) =>
    api.post<MetaExportResponse>('/meta/export', data).then((r) => r.data),
}

// ── Admin ─────────────────────────────────────────────────────────────────────
export const adminApi = {
  listUsers: () => api.get<User[]>('/admin/users').then((r) => r.data),

  listClients: () => api.get<AdminClient[]>('/admin/clients').then((r) => r.data),

  updateRole: (userId: string, role: string) =>
    api.put<User>(`/admin/users/${userId}/role`, null, { params: { role } }).then((r) => r.data),

  deactivateUser: (userId: string) => api.delete(`/admin/users/${userId}`),

  setUserActive: (userId: string, active: boolean) =>
    api.put<User>(`/admin/users/${userId}/active`, null, { params: { active } }).then((r) => r.data),

  getStats: () => api.get<AdminStats>('/admin/stats').then((r) => r.data),

  getUsage: (params?: { days?: number; from?: string; to?: string; user_id?: string }) =>
    api.get<AdminUsage>('/admin/usage', { params }).then((r) => r.data),

    getUsageAllowances: () =>
      api.get<UsageAllowance[]>('/admin/usage-allowances').then((r) => r.data),

    resetUsageAllowance: (userId: string, note = '') =>
      api.post<UsageAllowance>(`/admin/users/${userId}/usage-allowance/reset`, { note }).then((r) => r.data),

  exportUsageReport: (params: { days?: number; from?: string; to?: string; user_id?: string }) =>
    api.get<Blob>('/admin/usage/export', {
      params,
      responseType: 'blob',
    }),

  exportUsageSummaryReport: (params: { days?: number; from?: string; to?: string; user_id?: string }) =>
    api.get<Blob>('/admin/usage/export/summary', {
      params,
      responseType: 'blob',
    }),

  checkSeedanceCredits: () =>
    api.post<SeedanceCreditsCheck>('/admin/seedance/check-credits').then((r) => r.data),

  getPricing: () => api.get<PricingConfig>('/admin/pricing').then((r) => r.data),

  /** Send {} to restore every default. */
  savePricing: (overrides: Partial<PricingRates>) =>
    api.put<PricingConfig>('/admin/pricing', overrides).then((r) => r.data),
}

export default api
