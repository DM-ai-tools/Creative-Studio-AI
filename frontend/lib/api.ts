import axios, { AxiosInstance, AxiosError } from 'axios'
import { authStorage } from './auth'
import type {
  Asset, AvatarScriptResult, Brand, BrandKit, Brief, DashboardStats,
  FatigueAlert, GenerationCatalog, MetaExportResponse,
  MetaStatus, PerformanceMetric, TokenResponse,
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
  list: () => api.get<Brand[]>('/brands').then((r) => r.data),

  get: (id: string) => api.get<Brand>(`/brands/${id}`).then((r) => r.data),

  create: (data: Partial<Brand>) => api.post<Brand>('/brands', data).then((r) => r.data),

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
    return api
      .post<Brand>(`/brands/${brandId}/logo`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },

  uploadLogoOnLight: (brandId: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<BrandKit>(`/brands/${brandId}/logo/on-light`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      .then((r) => r.data)
  },
}

// ── Briefs ────────────────────────────────────────────────────────────────────
export const briefsApi = {
  list: (params?: { status?: string; limit?: number; offset?: number }) =>
    api.get<Brief[]>('/briefs', { params }).then((r) => r.data),

  get: (id: string) => api.get<Brief>(`/briefs/${id}`).then((r) => r.data),

  create: (data: Partial<Brief>) => api.post<Brief>('/briefs', data).then((r) => r.data),

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
      .post<{ message: string; variants_created: number }>(`/briefs/${id}/generate`, data, {
        timeout: 3_900_000,
      })
      .then((r) => r.data),

  uploadScriptPdf: (id: string, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api
      .post<{ character_count: number; preview: string; filename: string }>(
        `/briefs/${id}/script-pdf`,
        form,
        { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 120_000 }
      )
      .then((r) => r.data)
  },

  clearScriptPdf: (id: string) => api.delete<Brief>(`/briefs/${id}/script-pdf`).then((r) => r.data),
}

// ── Variants ──────────────────────────────────────────────────────────────────
export const variantsApi = {
  list: (params?: { brief_id?: string; status?: string; compliance_status?: string }) =>
    api.get<Variant[]>('/variants', { params, timeout: 60_000 }).then((r) => r.data),

  get: (id: string) => api.get<Variant>(`/variants/${id}`).then((r) => r.data),

  update: (id: string, data: Partial<Variant>) =>
    api.put<Variant>(`/variants/${id}`, data).then((r) => r.data),

  approve: (id: string) => api.post<Variant>(`/variants/${id}/approve`).then((r) => r.data),

  reject: (id: string) => api.post<Variant>(`/variants/${id}/reject`).then((r) => r.data),

  regenerate: (id: string) => api.post<Variant>(`/variants/${id}/regenerate`).then((r) => r.data),

  delete: (id: string) => api.delete(`/variants/${id}`),

  getFatigueAlerts: () =>
    api.get<FatigueAlert[]>('/variants/fatigue-alerts').then((r) => r.data),
}

// ── Assets ────────────────────────────────────────────────────────────────────
export const assetsApi = {
  upload: (file: File, variantId?: string, assetType: string = 'image') => {
    const form = new FormData()
    form.append('file', file)
    if (variantId) form.append('variant_id', variantId)
    form.append('asset_type', assetType)
    return api
      .post<Asset>('/assets/upload', form, { headers: { 'Content-Type': 'multipart/form-data' } })
      .then((r) => r.data)
  },

  list: (params?: { variant_id?: string; asset_type?: string }) =>
    api.get<Asset[]>('/assets', { params }).then((r) => r.data),

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
  getCatalog: () =>
    api.get<GenerationCatalog>('/generation/catalog', { timeout: 45_000 }).then((r) => r.data),

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
    purpose?: 'avatar_script' | 'brief_notes' | 'visual_cues'
  }) =>
    api
      .post<AvatarScriptResult>('/generation/avatar-script', data, { timeout: 120_000 })
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

  updateRole: (userId: string, role: string) =>
    api.put<User>(`/admin/users/${userId}/role`, null, { params: { role } }).then((r) => r.data),

  deactivateUser: (userId: string) => api.delete(`/admin/users/${userId}`),

  getStats: () => api.get('/admin/stats').then((r) => r.data),
}

export default api
