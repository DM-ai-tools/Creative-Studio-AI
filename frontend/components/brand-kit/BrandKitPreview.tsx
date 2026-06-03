'use client'

interface BrandKitPreviewProps {
  brandName: string
  industry: string
  logoUrl: string | null
  logoLightUrl: string | null
  primaryColor: string
  secondaryColor: string
  headingFont: string
  bodyFont: string
}

export default function BrandKitPreview({
  brandName,
  industry,
  logoUrl,
  logoLightUrl,
  primaryColor,
  secondaryColor,
  headingFont,
  bodyFont,
}: BrandKitPreviewProps) {
  const displayName = brandName.trim() || 'Your brand'
  const headingStyle = headingFont ? { fontFamily: headingFont } : undefined
  const bodyStyle = bodyFont ? { fontFamily: bodyFont } : undefined

  return (
    <div className="relative w-full overflow-hidden rounded-3xl border border-white/[0.08] bg-gradient-to-br from-[#1a1b1f] via-charcoal to-[#14151a] shadow-card">
      <div
        className="absolute inset-0 opacity-40 pointer-events-none"
        style={{
          background: `radial-gradient(ellipse 70% 80% at 85% 20%, ${primaryColor}55 0%, transparent 55%), radial-gradient(ellipse 50% 60% at 10% 90%, ${secondaryColor}33 0%, transparent 50%)`,
        }}
      />
      <div className="relative p-6 md:p-8 lg:p-10">
        <div className="flex flex-col lg:flex-row lg:items-center lg:justify-between gap-8">
          <div className="flex items-center gap-5 min-w-0">
            <div className="flex gap-3 shrink-0">
              <div className="w-[88px] h-[72px] rounded-2xl bg-black/40 border border-white/10 flex items-center justify-center p-3">
                {logoUrl ? (
                  <img src={logoUrl} alt="" className="max-h-full max-w-full object-contain" />
                ) : (
                  <span className="text-[10px] text-subtle text-center leading-tight">Dark logo</span>
                )}
              </div>
              <div className="w-[88px] h-[72px] rounded-2xl bg-white border border-white/20 flex items-center justify-center p-3">
                {logoLightUrl || logoUrl ? (
                  <img
                    src={logoLightUrl || logoUrl || ''}
                    alt=""
                    className="max-h-full max-w-full object-contain"
                  />
                ) : (
                  <span className="text-[10px] text-muted text-center leading-tight">Light logo</span>
                )}
              </div>
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-accent mb-1">Live preview</p>
              <h2 className="text-2xl md:text-3xl font-bold text-white tracking-tight truncate" style={headingStyle}>
                {displayName}
              </h2>
              <p className="text-sm text-subtle mt-1 truncate">{industry || 'Agency profile'}</p>
            </div>
          </div>

          <div className="flex items-center gap-4 shrink-0">
            <div className="text-right hidden sm:block">
              <p className="text-[10px] font-semibold text-subtle uppercase tracking-wider mb-2">Palette</p>
              <div className="flex gap-2 justify-end">
                <div className="text-center">
                  <div
                    className="w-12 h-12 rounded-xl border-2 border-white/20 shadow-lg"
                    style={{ backgroundColor: primaryColor }}
                  />
                  <p className="text-[10px] text-subtle mt-1 font-mono">{primaryColor}</p>
                </div>
                <div className="text-center">
                  <div
                    className="w-12 h-12 rounded-xl border-2 border-white/20 shadow-lg"
                    style={{ backgroundColor: secondaryColor }}
                  />
                  <p className="text-[10px] text-subtle mt-1 font-mono">{secondaryColor}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div
          className="mt-8 rounded-2xl bg-white/95 backdrop-blur p-5 md:p-6 grid md:grid-cols-[1fr_auto] gap-4 items-center"
          style={bodyStyle}
        >
          <div>
            <p className="text-[10px] font-bold text-muted uppercase tracking-wider mb-2">Ad mockup</p>
            <p className="text-lg font-bold text-charcoal" style={headingStyle}>
              Sample headline for {displayName}
            </p>
            <p className="text-sm text-muted mt-1 max-w-md">
              This is how your body copy and CTA could appear on a generated creative.
            </p>
          </div>
          <button
            type="button"
            className="px-6 py-2.5 rounded-xl text-sm font-bold text-white shadow-soft shrink-0"
            style={{ backgroundColor: primaryColor }}
          >
            Shop now
          </button>
        </div>
      </div>
    </div>
  )
}
