export interface User {
  id: string
  email: string
  full_name: string
  role: 'admin' | 'member' | 'viewer'
  tenant_id: string | null
  is_active: boolean
  is_verified: boolean
  avatar_url?: string | null
  created_at: string
}

export interface Tenant {
  id: string
  name: string
  slug: string
  plan: 'starter' | 'pro' | 'enterprise'
  is_active: boolean
  settings: Record<string, unknown>
  created_at: string
}

export interface Brand {
  id: string
  tenant_id: string
  name: string
  industry: string
  language: string
  voice_rules: Record<string, unknown>
  forbidden_words: string[]
  logo_url?: string | null
  primary_color?: string | null
  secondary_color?: string | null
  created_at: string
  updated_at: string
}

export interface BrandKit {
  id: string
  brand_id: string
  name: string
  colors: Record<string, unknown>
  fonts: Record<string, unknown>
  logo_variations: Record<string, unknown>
  guidelines_url?: string | null
  created_at: string
  updated_at: string
}

export type BriefStatus = 'DRAFT' | 'PENDING' | 'RUNNING' | 'READY' | 'PARTIAL' | 'FAILED' | 'EXPORTED'
export type VariantStatus = 'PENDING' | 'GENERATING' | 'READY' | 'FAILED' | 'APPROVED' | 'REJECTED' | 'EXPORTED'
export type ComplianceStatus = 'PENDING' | 'PASSED' | 'FAILED' | 'WARNING'
export type AdFormat = 'static' | 'reel' | 'video' | 'carousel'

export interface VariantSummary {
  id: string
  format: AdFormat
  hook: string
  status: VariantStatus
  compliance_status: ComplianceStatus
  performance_score?: number | null
}

export interface Brief {
  id: string
  tenant_id: string
  brand_id: string
  created_by?: string | null
  title: string
  objective: string
  target_audience: string
  formats: AdFormat[]
  ad_copy_tone: string
  cta: string
  product_name: string
  key_benefits: Record<string, unknown>
  status: BriefStatus
  variant_count: number
  completed_variants: number
  variants?: VariantSummary[]
  created_at: string
  updated_at: string
}

export interface GenerationModelOption {
  id: string
  label: string
  provider_model: string
  modality: string
  provider?: string | null
}

export interface MetaStatus {
  configured: boolean
  connected: boolean
  app_id?: string | null
  ad_account_id?: string | null
  graph_api_version: string
  auth_mode: string
  profile?: Record<string, unknown> | null
  ad_accounts?: Record<string, unknown>[]
  message?: string | null
}

export interface MetaExportResponse {
  status: string
  auth_mode: string
  campaign_name: string
  ad_set_name?: string | null
  variant_ids: string[]
  ad_account_id?: string | null
  message: string
}

export interface GenerationCatalog {
  copy_models: GenerationModelOption[]
  image_models: GenerationModelOption[]
  video_models: GenerationModelOption[]
  heygen_avatar_options?: CatalogOption[]
  heygen_avatar_featured?: CatalogOption[]
  heygen_voice_options?: CatalogOption[]
  higgsfield_voice_options?: CatalogOption[]
  objectives: CatalogOption[]
  placements: CatalogOption[]
  creative_formats: CatalogOption[]
  hook_frameworks: CatalogOption[]
  cta_options: CatalogOption[]
  tone_options: CatalogOption[]
  pipeline_steps: string[]
  estimate: {
    cost_per_variant_usd: number
    seconds_per_variant: number
  }
}

export interface CatalogOption {
  id: string
  label: string
  gender?: string | null
}

export interface AvatarScriptLine {
  start: string
  end: string
  text: string
}

export interface AvatarScriptValidation {
  id: string
  label: string
  status: 'ok' | 'warn'
}

export interface AvatarScriptResult {
  lines: AvatarScriptLine[]
  full_script: string
  word_count: number
  estimated_seconds: number
  words_per_second: number
  model_id: string
  model_label: string
  validations: AvatarScriptValidation[]
}

export interface IcpScriptResult {
  icp_text: string
  script: AvatarScriptResult
}

export interface WebsiteScriptResult {
  script: AvatarScriptResult
  page_title: string
  page_description: string
  framework_name: string
  framework_description: string
  url: string
}

export interface PerformanceMetricItem {
  label: string
  value: string
}

/** ROAS / ROI / conversion stats extracted from a dashboard screenshot */
export interface PerformanceStatsContext {
  industry: string
  campaign_type: string
  headline_stat: string
  roas: string
  roi: string
  conversions: string
  clicks: string
  purchases_sales: string
  revenue: string
  conversion_value: string
  cost: string
  cost_per_conversion: string
  conv_value_per_cost: string
  lead_forms: string
  timeline: string
  growth_story: string
  metrics: PerformanceMetricItem[]
  script_proof_lines: string[]
  summary_for_script: string
}

export interface StatsImageExtractionResult {
  stats: PerformanceStatsContext
  filename: string
}

export interface BodyOutlineSection {
  section: string
  duration_hint: string
  talking_points: string
}

export interface HaloStrategy {
  hook: string
  agitate: string
  lift: string
  offer: string
}

export interface StrategyPreviewResult {
  campaign_name: string
  brand_name: string
  product_name: string
  offer: string
  target_audience: string
  ad_copy_tone: string
  cta: string
  target_seconds: number
  objective: string
  hook_frameworks: string[]
  competitors: string[]
  website_url: string
  framework_name: string
  framework_description: string
  framework_structure: string[]
  icp_text: string
  icp_fields: Record<string, string>
  hook_options: string[]
  body_outline: BodyOutlineSection[]
  halo_strategy: HaloStrategy
  competitor_positioning: string
  differentiation_points: string[]
}

export interface ModelSuggestion {
  image_model: string
  image_reason: string
  video_model: string
  video_reason: string
  copy_model: string
  copy_reason: string
}

export interface Variant {
  id: string
  brief_id: string
  brand_id: string
  tenant_id: string
  format: AdFormat
  hook: string
  headline: string
  body_copy: string
  cta: string
  hashtags: string[]
  ai_model: string
  generation_params?: Record<string, unknown>
  status: VariantStatus
  compliance_status: ComplianceStatus
  compliance_notes: Record<string, unknown>
  performance_score?: number | null
  created_at: string
  updated_at: string
}

export interface Asset {
  id: string
  tenant_id: string
  variant_id?: string | null
  brand_id?: string | null
  file_name: string
  file_url: string
  file_type: string
  file_size: number
  asset_type: string
  width?: number | null
  height?: number | null
  created_at: string
}

export interface PerformanceMetric {
  id: string
  variant_id: string
  date: string
  impressions: number
  clicks: number
  conversions: number
  spend: number
  revenue: number
  roas: number
  ctr: number
  cpm: number
  frequency: number
  reach: number
  meta_ad_id?: string | null
  created_at: string
}

export interface PerformanceRollup {
  id: string
  variant_id: string
  roas_7d: number
  roas_personal_best: number
  roas_30d: number
  frequency_7d: number
  is_fatigued: boolean
  status: string
  last_synced_at?: string | null
  updated_at: string
}

export interface DashboardStats {
  active_variants: number
  avg_roas_7d: number
  brand_safety_pass_rate: number
  fatigued_count: number
}

export interface TokenResponse {
  access_token: string
  refresh_token: string
  token_type: string
  user: User
}

export interface FatigueAlert {
  variant_id: string
  hook: string
  format: AdFormat
  roas_personal_best: number
  roas_7d: number
  drop_pct: number
  frequency_7d: number
  status: string
}

export interface TopPerformer {
  variant_id: string
  hook: string
  format: AdFormat
  roas_7d: number
  status: string
}

export interface ApiError {
  detail: string
}
