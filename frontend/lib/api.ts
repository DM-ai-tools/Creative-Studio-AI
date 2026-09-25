import axios, { AxiosInstance, AxiosError } from 'axios'
import { authStorage } from './auth'
import type {
  AdminClient, AdminStats, AdminUsage, Asset, AvatarScriptResult, BrandFacts, IcpImagePlanResult, IcpScriptResult, ModelSuggestion, PerformanceStatsContext,
  SuggestAdAnglesResult, StrategyParseResult, WebsiteBrandFetchResult,
  StatsImageExtractionResult, StrategyPreviewResult, ReferenceImageAnalysisResult,
  WebsiteScriptResult, Brand, BrandKit, Brief, DashboardStats, FatigueAlert,
  GenerationCatalog, GenerationModelOption, MetaExportResponse, MetaStatus, PerformanceMetric, TokenResponse,
  TopPerformer, User, Variant,
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
    negative_prompt?: string
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
        credits_estimate?: number | null
        duration_warning?: string | null
        note?: string | null
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
        credits_estimate?: number | null
        duration_warning?: string | null
        note?: string | null
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
      }>(`/generation/creative-studio/jobs/${encodeURIComponent(jobId)}`, {
        timeout: 30_000,
      })
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

  creativeStudioModels: () =>
    api
      .get<{
        configured: boolean
        chat_models?: GenerationModelOption[]
        default_chat_model?: string | null
        image_model_default?: string | null
        video_model_default?: string | null
        image_models: GenerationModelOption[]
        video_models: GenerationModelOption[]
        message?: string | null
      }>('/generation/creative-studio/models', { timeout: 20_000 })
      .then((r) => r.data),

  creativeStudioChat: (data: {
    messages: { role: 'user' | 'assistant'; content: string }[]
    mode?: 'auto' | 'ask' | 'generate'
    chat_model?: string
    duration_seconds?: number
    aspect?: string
    resolution?: string
    sound_on?: boolean
    attachment_urls?: string[]
    brand_name?: string
    product_name?: string
    action?:
      | 'continue'
      | 'generate_image'
      | 'regenerate_image'
      | 'approve_next'
      | 'generate_video'
      | 'generate_storyboard'
    image_prompt?: string
    video_prompt?: string
    approved_image_url?: string
    product_reference_url?: string
    logo_reference_url?: string
    additional_reference_urls?: string[]
    reference_assets?: { url: string; role: 'product' | 'logo' | 'scene' | 'character' | 'reference' }[]
    storyboard_image_urls?: string[]
    image_model?: string
    revision_notes?: string
    phase?: string
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
        error?: string | null
      }>('/generation/creative-studio/chat', data, { timeout: 120_000 })
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

  getStats: () => api.get<AdminStats>('/admin/stats').then((r) => r.data),

  getUsage: () => api.get<AdminUsage>('/admin/usage').then((r) => r.data),
}

export default api
