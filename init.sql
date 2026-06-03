-- CreativeStudio AI — Initial Database Schema
-- Run manually: psql -U creativestudioai -d creativestudioai -f init.sql

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Tenants (organisations / accounts)
CREATE TABLE IF NOT EXISTS tenants (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        TEXT NOT NULL,
    slug        TEXT NOT NULL UNIQUE,
    plan        TEXT NOT NULL DEFAULT 'starter' CHECK (plan IN ('starter','pro','enterprise')),
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    settings    JSONB NOT NULL DEFAULT '{}',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Users
CREATE TABLE IF NOT EXISTS users (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id       UUID REFERENCES tenants(id) ON DELETE CASCADE,
    email           TEXT NOT NULL UNIQUE,
    hashed_password TEXT NOT NULL,
    full_name       TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'member' CHECK (role IN ('admin','member','viewer')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    is_verified     BOOLEAN NOT NULL DEFAULT FALSE,
    avatar_url      TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_users_tenant ON users(tenant_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- Brands
CREATE TABLE IF NOT EXISTS brands (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name                TEXT NOT NULL,
    industry            TEXT NOT NULL DEFAULT 'general',
    language            TEXT NOT NULL DEFAULT 'English',
    voice_rules         JSONB NOT NULL DEFAULT '{}',
    forbidden_words     TEXT[] NOT NULL DEFAULT '{}',
    logo_url            TEXT,
    primary_color       TEXT DEFAULT '#0F1B3D',
    secondary_color     TEXT DEFAULT '#00C2A8',
    profile_vector_id   UUID,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_brands_tenant ON brands(tenant_id);

-- Brand Kits
CREATE TABLE IF NOT EXISTS brand_kits (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brand_id        UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    name            TEXT NOT NULL DEFAULT 'Default Kit',
    colors          JSONB NOT NULL DEFAULT '{}',
    fonts           JSONB NOT NULL DEFAULT '{}',
    logo_variations JSONB NOT NULL DEFAULT '{}',
    guidelines_url  TEXT,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_brand_kits_brand ON brand_kits(brand_id);

-- Briefs
CREATE TABLE IF NOT EXISTS briefs (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    brand_id            UUID NOT NULL REFERENCES brands(id) ON DELETE CASCADE,
    created_by          UUID REFERENCES users(id),
    title               TEXT NOT NULL,
    objective           TEXT NOT NULL DEFAULT '',
    target_audience     TEXT NOT NULL DEFAULT '',
    formats             TEXT[] NOT NULL DEFAULT '{}',
    ad_copy_tone        TEXT NOT NULL DEFAULT 'Professional',
    cta                 TEXT NOT NULL DEFAULT 'Shop Now',
    product_name        TEXT NOT NULL DEFAULT '',
    key_benefits        JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'DRAFT'
                        CHECK (status IN ('DRAFT','PENDING','RUNNING','READY','PARTIAL','FAILED','EXPORTED')),
    variant_count       INTEGER NOT NULL DEFAULT 0,
    completed_variants  INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_briefs_tenant ON briefs(tenant_id);
CREATE INDEX IF NOT EXISTS idx_briefs_brand ON briefs(brand_id);
CREATE INDEX IF NOT EXISTS idx_briefs_status ON briefs(status);

-- Variants
CREATE TABLE IF NOT EXISTS variants (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    brief_id            UUID NOT NULL REFERENCES briefs(id) ON DELETE CASCADE,
    brand_id            UUID NOT NULL REFERENCES brands(id),
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    format              TEXT NOT NULL CHECK (format IN ('static','reel','video','carousel')),
    hook                TEXT NOT NULL DEFAULT '',
    headline            TEXT NOT NULL DEFAULT '',
    body_copy           TEXT NOT NULL DEFAULT '',
    cta                 TEXT NOT NULL DEFAULT '',
    hashtags            TEXT[] NOT NULL DEFAULT '{}',
    ai_model            TEXT NOT NULL DEFAULT 'claude',
    generation_params   JSONB NOT NULL DEFAULT '{}',
    status              TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (status IN ('PENDING','GENERATING','READY','FAILED','APPROVED','REJECTED','EXPORTED')),
    compliance_status   TEXT NOT NULL DEFAULT 'PENDING'
                        CHECK (compliance_status IN ('PENDING','PASSED','FAILED','WARNING')),
    compliance_notes    JSONB NOT NULL DEFAULT '{}',
    performance_score   NUMERIC(5,2),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_variants_brief ON variants(brief_id);
CREATE INDEX IF NOT EXISTS idx_variants_tenant ON variants(tenant_id);
CREATE INDEX IF NOT EXISTS idx_variants_status ON variants(status);
CREATE INDEX IF NOT EXISTS idx_variants_compliance ON variants(compliance_status);

-- Assets (uploaded files + generated media)
CREATE TABLE IF NOT EXISTS assets (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    variant_id  UUID REFERENCES variants(id) ON DELETE SET NULL,
    brand_id    UUID REFERENCES brands(id) ON DELETE SET NULL,
    file_name   TEXT NOT NULL,
    file_path   TEXT NOT NULL,
    file_url    TEXT NOT NULL,
    file_type   TEXT NOT NULL,
    file_size   BIGINT NOT NULL DEFAULT 0,
    asset_type  TEXT NOT NULL DEFAULT 'image'
                CHECK (asset_type IN ('image','video','copy','thumbnail','logo','guideline')),
    width       INTEGER,
    height      INTEGER,
    duration_seconds NUMERIC(8,2),
    metadata    JSONB NOT NULL DEFAULT '{}',
    created_by  UUID REFERENCES users(id),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_assets_tenant ON assets(tenant_id);
CREATE INDEX IF NOT EXISTS idx_assets_variant ON assets(variant_id);

-- Performance Metrics (daily granularity per variant)
CREATE TABLE IF NOT EXISTS performance_metrics (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    variant_id  UUID NOT NULL REFERENCES variants(id) ON DELETE CASCADE,
    tenant_id   UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    date        DATE NOT NULL,
    impressions INTEGER NOT NULL DEFAULT 0,
    clicks      INTEGER NOT NULL DEFAULT 0,
    conversions INTEGER NOT NULL DEFAULT 0,
    spend       NUMERIC(12,2) NOT NULL DEFAULT 0,
    revenue     NUMERIC(12,2) NOT NULL DEFAULT 0,
    roas        NUMERIC(8,4) NOT NULL DEFAULT 0,
    ctr         NUMERIC(8,6) NOT NULL DEFAULT 0,
    cpm         NUMERIC(10,4) NOT NULL DEFAULT 0,
    frequency   NUMERIC(8,4) NOT NULL DEFAULT 0,
    reach       INTEGER NOT NULL DEFAULT 0,
    meta_ad_id  TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (variant_id, date)
);
CREATE INDEX IF NOT EXISTS idx_perf_variant ON performance_metrics(variant_id);
CREATE INDEX IF NOT EXISTS idx_perf_tenant ON performance_metrics(tenant_id);
CREATE INDEX IF NOT EXISTS idx_perf_date ON performance_metrics(date);

-- Performance Rollups (aggregated summary per variant)
CREATE TABLE IF NOT EXISTS performance_rollups (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    variant_id          UUID NOT NULL UNIQUE REFERENCES variants(id) ON DELETE CASCADE,
    tenant_id           UUID NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    roas_7d             NUMERIC(8,4) NOT NULL DEFAULT 0,
    roas_personal_best  NUMERIC(8,4) NOT NULL DEFAULT 0,
    roas_30d            NUMERIC(8,4) NOT NULL DEFAULT 0,
    frequency_7d        NUMERIC(8,4) NOT NULL DEFAULT 0,
    is_fatigued         BOOLEAN NOT NULL DEFAULT FALSE,
    passed              INTEGER NOT NULL DEFAULT 0,
    checked             INTEGER NOT NULL DEFAULT 0,
    status              TEXT NOT NULL DEFAULT 'ACTIVE'
                        CHECK (status IN ('ACTIVE','PAUSED','ARCHIVED')),
    last_synced_at      TIMESTAMPTZ,
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_rollups_tenant ON performance_rollups(tenant_id);
CREATE INDEX IF NOT EXISTS idx_rollups_fatigued ON performance_rollups(is_fatigued);

-- Auto-update updated_at trigger
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN NEW.updated_at = NOW(); RETURN NEW; END;
$$ LANGUAGE plpgsql;

DO $$ DECLARE t TEXT;
BEGIN
  FOR t IN SELECT unnest(ARRAY['tenants','users','brands','brand_kits','briefs','variants'])
  LOOP
    EXECUTE format('DROP TRIGGER IF EXISTS trg_updated_at ON %I', t);
    EXECUTE format('CREATE TRIGGER trg_updated_at BEFORE UPDATE ON %I FOR EACH ROW EXECUTE FUNCTION update_updated_at()', t);
  END LOOP;
END $$;
