export interface User {
  id: string
  email: string
  full_name: string
  role: 'admin' | 'member' | 'viewer'
  product_scope?: string | null
  tenant_id: string | null
  tenant_name?: string | null
  is_active: boolean
  is_verified: boolean
  avatar_url?: string | null
  last_login_at?: string | null
  created_at: string
  brief_count?: number | null
  variant_count?: number | null
}

export interface AdminStats {
  is_platform_admin: boolean
  clients: number
  users: number
  users_today: number
  users_this_week: number
  briefs: number
  variants: number
  brands: number
  storage_bytes: number
  storage_mb: number
}

export interface AdminClient {
  id: string
  name: string
  slug: string
  plan: string
  is_active: boolean
  user_count: number
  brand_count: number
  brief_count: number
  variant_count: number
  created_at: string
  last_activity_at?: string | null
}

export interface UsageAllowance {
  user_id: string
  email: string
  full_name: string
  role: 'admin' | 'member' | 'viewer'
  tenant_id?: string | null
  exempt: boolean
  limit_usd: number
  period_spend_usd: number
  remaining_usd?: number | null
  lifetime_spend_usd: number
  limit_reached: boolean
  period_started_at?: string | null
  last_reset_at?: string | null
  reset_count: number
}

export interface EmailTemplateContent {
  brand_name: string
  logo_url?: string | null
  primary_color: string
  secondary_color: string
  background_color: string
  surface_color: string
  text_color: string
  eyebrow: string
  headline: string
  body: string
  cta_text: string
  cta_url: string
  hero_url?: string | null
  footer_text: string
  show_logo: boolean
  show_hero: boolean
  layout_reference_url?: string | null
  layout_html_snippet?: string | null
}

export interface EmailTemplate {
  id: string
  brand_id?: string | null
  campaign_name: string
  email_type: string
  status: string
  subject: string
  preheader: string
  content: EmailTemplateContent
  created_at?: string | null
  updated_at?: string | null
}

export interface UsageBucket {
  name: string
  calls: number
  tokens: number
  credits: number
  cost_usd: number
  failed: number
}

export interface UsageEventRow {
  id: string
  provider: string
  model: string
  operation: string
  prompt_tokens: number
  completion_tokens: number
  total_tokens: number
  credits: number
  cost_usd: number
  cost_estimated?: boolean
  success: boolean
  error?: string | null
  client?: string | null
  created_at?: string | null
  media_url?: string | null
  variant_url?: string | null
}

export interface UsageDailyPoint {
  date: string
  total: number
  [model: string]: number | string
}

export interface SeedanceUsageClip {
  id: string
  task_id?: string | null
  model: string
  tokens: number
  cost_usd: number
  cost_usd_low: number
  cost_usd_high: number
  cost_estimated: boolean
  resolution?: string | null
  resolution_inferred?: boolean
  duration_seconds?: number | null
  recovered?: boolean
  client?: string | null
  created_at?: string | null
  media_url?: string | null
  variant_url?: string | null
}

export interface SeedanceUsageModelRow {
  model: string
  clips: number
  failed: number
  tokens: number
  cost_usd: number
  cost_usd_low: number
  cost_usd_high: number
}

export interface SeedanceUsageSummary {
  successful_clips: number
  failed_calls: number
  total_tokens: number
  cost_usd: number
  cost_usd_low: number
  cost_usd_high: number
  pricing_note: string
  by_model: SeedanceUsageModelRow[]
  recent_clips: SeedanceUsageClip[]
}

export interface SeedanceCreditsCheck {
  checked_at: string
  configured: boolean
  status: 'ok' | 'no_credits' | 'not_configured' | 'auth_error' | 'connection_error' | 'error'
  message: string
  task_history?: {
    total_tasks: number
    recent_succeeded: number
    recent_failed: number
    recent_billing_failures: number
  } | null
  models: Array<{
    catalog_id: string
    label: string
    api_model: string
    billing_status: string
    message: string
    probe_task_id?: string | null
  }>
  probe_note?: string | null
}

/** A screen or graphic the planner wants drawn as a picture and shown over the video. */
export interface CreativeStudioStill {
  id: string
  scene: number
  label: string
  start: number
  end: number
  duration: number
  image_prompt: string
}

/** Result of drawing one still with GPT Image 2 or Seedream. */
export interface CreativeStudioStillResult {
  url: string
  model: string
  provider?: string | null
  credits_estimate?: number | null
  note?: string | null
}

/** Where the brand logo sits inside a drawn picture. */
export type CreativeStudioLogoCorner = 'top_left' | 'top_right' | 'bottom_left' | 'bottom_right'

/** A drawn picture with the brand logo placed inside it. */
export interface CreativeStudioStillLogoResult {
  url: string
  source_url: string
  corner: CreativeStudioLogoCorner
  /** Brightness of the picture under the logo. */
  background: 'light' | 'dark'
  /** Which version of the logo was used. */
  logo_version: string
  warnings: string[]
}

/** Result of laying still pictures over a video. */
export interface CreativeStudioInsertsResult {
  url: string
  source_url: string
  width: number
  height: number
  duration_seconds: number
  inserts: { start_seconds: number; end_seconds: number }[]
  warnings: string[]
}

/** What an end card should say, taken character for character from the script. */
export interface CreativeStudioEndCardSpec {
  headline: string
  sublines: string[]
  button_text: string
  start_seconds: number
  hold_seconds: number
  note: string
}

/** Result of adding (or previewing) an end card. */
export interface CreativeStudioEndCardResult {
  kind: 'preview' | 'video'
  url: string
  source_url: string
  width: number
  height: number
  duration_seconds: number
  start_seconds: number
  hold_seconds: number
  logo_applied: boolean
  theme: 'light' | 'dark'
  warnings: string[]
}

/** Result of Creative Studio "Script mode" planning (POST /generation/creative-studio/script/plan). */
export interface CreativeStudioScriptPlan {
  title: string
  global_style: string
  scenes: {
    index: number
    title: string
    start: number
    end: number
    duration_seconds: number
    duration_source: 'script' | 'estimated'
    /** Who speaks: a visible person, off-camera narration, or nobody. */
    speech: 'on_camera' | 'voiceover' | 'none'
    /** The scene's cut: a new shot every 2-4s. Empty for the empty-background call-to-action scene. */
    shots: { seconds: number; description: string }[]
    voiceover: string
    visual_direction: string
    on_screen_text: string[]
    reason: string
  }[]
  edit_list: {
    scene: number
    scene_title: string
    start: number
    end: number
    kind: string
    note: string
    /** For screens/graphics: a prompt for an image model to draw the picture (empty for other kinds). */
    image_prompt: string
  }[]
  /** Screens and graphics to draw as stills and lay over the video (each in its own window). */
  stills: CreativeStudioStill[]
  total_seconds: number
  edit_count: number
  warnings: string[]
  voice: {
    gender: '' | 'female' | 'male'
    accent: string
    source: 'script' | 'default'
    base_line: string
    prompt_line: string
  }
  /** Default prompt: no ON-SCREEN TEXT blocks (the pipeline would burn them into the video). */
  /** The noun that repeats across too many shots (the cut may feel repetitive), or null. */
  repetition: { word: string; count: number; total: number } | null
  canonical_prompt: string
  /** Same prompt with the script's on-screen text included, for people who want it added automatically. */
  canonical_prompt_with_text: string
  /** Text and timing for the closing end card, from the script's closing scene (null if none). */
  end_card: CreativeStudioEndCardSpec | null
  speech_mode: 'native_presenter' | 'external_voiceover'
  video_model: string
  clip_cap_seconds: number
  aspect: string
  script_chars: number
}

export interface AdminUsage {
  totals: {
    calls: number
    failed_calls: number
    prompt_tokens: number
    completion_tokens: number
    total_tokens: number
    video_tokens?: number
    credits: number
    cost_usd: number
  }
  by_provider: UsageBucket[]
  by_model: UsageBucket[]
  by_user?: (UsageBucket & { user_id?: string | null })[]
  by_media_type?: UsageBucket[]
  seedance?: SeedanceUsageSummary
  recent: UsageEventRow[]
  daily_cost?: UsageDailyPoint[]
  daily_requests?: UsageDailyPoint[]
  chart_models?: string[]
  period_days?: number
  period_custom?: boolean
  period_from?: string | null
  period_to?: string | null
  filter_user_id?: string | null
}

export interface PricingRates {
  /** USD per 1M completion tokens: model family -> resolution -> rate */
  seedance_per_m_tokens: Record<string, Record<string, { no_video: number; with_video: number }>>
  /** Used only when a Seedance row has no token count */
  seedance_fallback_usd_per_30s: number
  /** USD per 1M tokens, by model id */
  llm_per_m_tokens: Record<string, { input: number; output: number }>
  llm_default_per_m_tokens: { input: number; output: number }
  /** OpenAI image model id -> USD per image */
  image_usd_each: Record<string, number>
}

export interface PricingConfig {
  defaults: PricingRates
  overrides: Partial<PricingRates>
  effective: PricingRates
  can_edit: boolean
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
  /** Estimated USD per image, or per second when cost_unit === 'second' */
  cost_usd?: number | null
  cost_unit?: 'image' | 'second' | string | null
  estimated_seconds?: number | null
  /** Provider-style credits (Higgsfield). Video = per second; image = per still. */
  credits?: number | null
  /** Max one-shot video length (seconds) without stitching. */
  max_duration_seconds?: number | null
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
  prompt_llm_models?: GenerationModelOption[]
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

export interface IcpImageVariantPlan {
  use_cases: string[]
  hook: string
  message: string
  /** Catchy related line burned onto the photo. */
  image_hook?: string
  /** Catchy related headline burned onto the photo. */
  image_headline?: string
  cta?: string
  offer: string
  prompt: string
  reasoning: string
  ad_angle?: string
}

export interface SuggestAdAnglesResult {
  suggested_angles: string[]
  reasoning: string
  icp_text?: string
  source?: 'ai' | 'rules' | string
}

export interface StrategyVariantPlan {
  id?: string
  format?: string
  ad_angle?: string
  use_cases?: string[]
  hook?: string
  message?: string
  image_hook?: string
  image_headline?: string
  cta?: string
  offer?: string
  prompt?: string
  reasoning?: string
  creative_type?: string
  carousel_index?: number | null
  carousel_total?: number | null
  carousel_group?: string | null
  /** Fashion retail: model + outfit photo only — feed copy stays off-image. */
  photo_only?: boolean
  /** Client-style retail promo ad (headline + offer on image). */
  retail_promo?: boolean
  aspect_ratio?: string
  product_name?: string
  post_type?: string
  design_notes?: string
  /** Per-variant shot style detected from the strategy document visual concept. */
  product_focus?: string
  /** The prompt is a complete designer brief read exactly from the file (kept as written, not expanded by AI). */
  prompt_complete?: boolean
}

export interface StrategyParseResult {
  brand_name: string
  industry: string
  niche: string
  geography: string
  age_range: string
  audience_type: string
  languages: string
  objective_id: string
  cta: string
  offer: string
  product_name: string
  ad_copy_tone: string
  placements: string[]
  formats: string[]
  hook_frameworks: string[]
  target_variant_count: number
  notes: string
  reasoning: string
  filename: string
  variants: StrategyVariantPlan[]
  image_aspect_ratio?: string
  creative_style?: string
}

export interface BrandFacts {
  services?: string[]
  products?: string[]
  service_areas?: string[]
  locations?: string[]
  offers?: string[]
  rates_or_pricing?: string[]
  reviews?: {
    rating?: number | null
    count?: number | null
    source?: string | null
    highlights?: string[]
  }
  credentials?: string[]
  years_in_business?: string | null
  phone?: string | null
  cta_phrases?: string[]
  unique_selling_points?: string[]
  do_not_claim?: string[]
  source_summary?: string
  confidence?: string
}

export interface SocialStyleVisualThemes {
  color_palette?: string[]
  layout_patterns?: string[]
  typography_style?: string
  image_composition?: string
  cta_style?: string
  mood?: string
  recurring_elements?: string[]
  avoid?: string[]
}

export interface SocialStyleProfile {
  platform?: string
  handle?: string
  profile_url?: string
  fetched_at?: string
  provider?: string
  post_count_analyzed?: number
  sample_image_urls?: string[]
  visual_themes?: SocialStyleVisualThemes | string[]
  caption_tone?: string
  content_mix?: string | Record<string, number>
  prompt_guidance?: string
  effective_primary_color?: string
  effective_secondary_color?: string
  aesthetic_mode?: 'gold_on_dark' | 'gold_on_white' | string
  post_summaries?: Array<{
    caption?: string
    post_type?: string
    image_url?: string
    design_notes?: string
  }>
}

export interface CompetitorSocialInsight {
  platform?: string
  handle?: string
  profile_url?: string
  fetched_at?: string
  provider?: string
  post_count_analyzed?: number
  content_mix?: Record<string, number>
  hook_patterns?: string[]
  format_patterns?: string[]
  posting_logic?: string
  caption_tone?: string
  prompt_guidance?: string
  post_summaries?: string[]
}

/** Suggested competitor — discovered but not yet post-analyzed */
export interface CompetitorCandidate {
  name?: string
  platform?: string
  handle?: string
  profile_url?: string
  reason?: string
  confidence?: string
  discovered_at?: string
  source?: string
  service_area?: string
}

export interface WebsiteBrandFetchResult {
  source_url: string
  brand_name: string
  industry: string
  niche?: string
  primary_color: string
  secondary_color: string
  font_heading?: string | null
  font_body?: string | null
  logo_url?: string | null
  page_title?: string
  description?: string
  provider?: string
  warning?: string | null
  brand_facts?: BrandFacts | null
}

export interface IcpImagePlanResult {
  icp_text: string
  variants: IcpImageVariantPlan[]
  campaign_hook?: string
  campaign_headline?: string
  campaign_cta?: string
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

export interface ReferenceImageAnalysis {
  color_palette?: string[]
  product_description?: string
  visual_themes?: Record<string, unknown>
  prompt_guidance?: string
  summary?: string
  [key: string]: unknown
}

export interface ReferenceImageAnalysisResult {
  file_url?: string | null
  asset_id?: string | null
  analysis: ReferenceImageAnalysis
  summary: string
  source_url?: string
  slug?: string
}

export interface BriefReferenceImage {
  asset_id?: string
  file_url: string
  analysis?: ReferenceImageAnalysis
  summary?: string
  is_product_reference?: boolean
  product_reference_context?: {
    brand_id?: string
    industry?: string
    niche?: string
    product_name?: string
  }
  /** Local blob preview when upload happened before brand was selected */
  localPreview?: string
  pendingFile?: File
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
  metadata?: Record<string, unknown>
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
  /** Null when no compliance checks have been recorded yet. */
  brand_safety_pass_rate: number | null
  brand_safety_checks?: number
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
