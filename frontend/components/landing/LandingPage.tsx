'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { BrandMark } from '@/components/brand/BrandMark'
import { authApi } from '@/lib/api'
import { authStorage } from '@/lib/auth'

/** Every `src` on this page is unique — never reused across sections. */
const HERO_SLIDES = [
  {
    src: '/landing/jewellery.jpg',
    eyebrow: 'Ecommerce · Jewellery',
    title: 'Jewellery that feels like you',
    subtitle: 'UGC product creatives from niche-locked briefs',
  },
  {
    src: '/landing/hvac.jpg',
    eyebrow: 'Trade · Air conditioning',
    title: 'AC packing it in?',
    subtitle: 'Pain-led local service ads with real niche proof',
  },
  {
    src: '/landing/garden.jpg',
    eyebrow: 'Local · Landscaping',
    title: 'From overgrown to stunning',
    subtitle: 'Before/after angles that match dental-results style',
  },
]

const STUDIO_TOOLS = [
  { id: 'brand-kit', label: 'Brand Kit', blurb: 'Voice, colours, offers, guardrails' },
  { id: 'briefs', label: 'Briefs', blurb: 'Industry → niche → objective → angles' },
  { id: 'variants', label: 'Variants', blurb: 'Hooks, on-image copy, image prompts' },
  { id: 'safety', label: 'Brand Safety', blurb: 'Claims, policy, ACCC-aware checks' },
  { id: 'performance', label: 'Performance', blurb: 'Fatigue, CTR, ROAS signals' },
  { id: 'export', label: 'Export to Meta', blurb: 'Ship approved creatives' },
]

const FEATURE_BLOCKS = [
  {
    kicker: 'ICP Image Plan',
    title: 'One brief. A full Meta creative batch.',
    body: 'CreativeStudio builds ICP-aware hooks, headlines, CTAs, and art-directed image prompts — locked to your niche so jewellery never becomes furniture.',
    cta: 'Start a brief',
    src: '/landing/feat-brief.jpg',
  },
  {
    kicker: 'Ad Angles',
    title: 'Pain-led. Social proof. Before/after. Offer urgency.',
    body: 'Pick the angles that fit the objective. Each variant gets a distinct angle, scene, and CTA — not the same stock smile recycled six times.',
    cta: 'Try the studio',
    src: '/landing/feat-angles.jpg',
  },
  {
    kicker: 'Formats',
    title: 'Static. Carousel. Reel-ready concepts.',
    body: 'Plan image and video creatives for Meta placements, then refine, retry failed frames, and keep winners in your variants library.',
    cta: 'Login',
    src: '/landing/feat-formats.jpg',
  },
]

const USE_CASE_SHOWCASE = [
  { id: 'hero_product', group: 'Brand', label: 'Hero product view', src: '/landing/uc-hero-product.jpg' },
  { id: 'lifestyle', group: 'Brand', label: 'Lifestyle image', src: '/landing/uc-lifestyle.jpg' },
  { id: 'product_person', group: 'Brand', label: 'Product with person', src: '/landing/uc-person.jpg' },
  { id: 'feature_explanation', group: 'Brand', label: 'Feature explanation', src: '/landing/uc-feature.jpg' },
  { id: 'detail_texture', group: 'Conversion', label: 'Detail / texture close-up', src: '/landing/uc-texture.jpg' },
  { id: 'packaging_unbox', group: 'Conversion', label: 'Packaging & unboxing', src: '/landing/uc-unbox.jpg' },
  { id: 'comparison', group: 'Conversion', label: 'Comparison imagery', src: '/landing/uc-comparison.jpg' },
  { id: 'bs_emotional_using', group: 'Best Sellers', label: 'People using product', src: '/landing/uc-using.jpg' },
  { id: 'bs_emotional_appeal', group: 'Best Sellers', label: 'Emotional buyer appeal', src: '/landing/uc-emotion.jpg' },
  { id: 'bs_real_life', group: 'Best Sellers', label: 'Real-life application', src: '/landing/uc-reallife.jpg' },
  { id: 'bs_price_feature', group: 'Decision', label: 'Price / feature highlight', src: '/landing/uc-price.jpg' },
  { id: 'virtual_tryon', group: 'Templates', label: 'Virtual try-on (AR)', src: '/landing/uc-tryon.jpg' },
]

const ANGLE_PRESETS = [
  { id: 'pain_led', label: 'Pain-led', hint: 'Show the exact niche pain' },
  { id: 'before_after', label: 'Before / After', hint: 'Side-by-side transformation' },
  { id: 'social_proof', label: 'Social proof', hint: 'Trust without fake stats' },
  { id: 'offer_urgency', label: 'Offer urgency', hint: 'Decision-moment CTAs' },
  { id: 'problem_agitate_solve', label: 'PAS', hint: 'Problem → agitate → solve' },
  { id: 'pattern_interrupt', label: 'Pattern interrupt', hint: 'Stop-the-scroll frames' },
  { id: 'fomo_scarcity', label: 'FOMO / scarcity', hint: 'Act-now without spam' },
  { id: 'testimonial', label: 'Testimonial', hint: 'Buyer-language proof' },
]

export default function LandingPage() {
  const router = useRouter()
  const [slide, setSlide] = useState(0)

  useEffect(() => {
    const token = authStorage.getAccessToken()
    if (!token) return

    let active = true
    authApi
      .getMe()
      .then((user) => {
        if (active && user) router.replace('/dashboard')
      })
      .catch(() => {
        authStorage.clear()
      })

    return () => {
      active = false
    }
  }, [router])

  useEffect(() => {
    const id = window.setInterval(() => {
      setSlide((s) => (s + 1) % HERO_SLIDES.length)
    }, 5200)
    return () => window.clearInterval(id)
  }, [])

  const active = HERO_SLIDES[slide]

  return (
    <div className="hf-root">
      <header className="hf-nav">
        <div className="hf-nav-inner">
          <Link href="/" className="hf-logo">
            <BrandMark size={32} className="rounded-[8px]" />
            Creative<span>Studio</span>
          </Link>
          <nav className="hf-nav-links" aria-label="Landing">
            <a href="#studio">Studio</a>
            <a href="#use-cases">Use cases</a>
            <a href="#angles">Angles</a>
            <a href="#examples">Examples</a>
          </nav>
          <div className="hf-nav-actions">
            <Link href="/login" className="hf-btn-accent">
              Login
            </Link>
          </div>
        </div>
      </header>

      <section className="hf-hero">
        {HERO_SLIDES.map((item, i) => (
          <div
            key={item.src}
            className={`hf-hero-slide ${i === slide ? 'is-active' : ''}`}
            aria-hidden={i !== slide}
          >
            <Image
              src={item.src}
              alt=""
              fill
              priority={i === 0}
              sizes="100vw"
              className="object-cover"
            />
          </div>
        ))}
        <div className="hf-hero-veil" />

        <div className="hf-hero-content">
          <p className="hf-hero-brand">
            Creative<span>Studio</span> AI
          </p>
          <p className="hf-kicker">{active.eyebrow}</p>
          <h1 className="hf-hero-title">{active.title}</h1>
          <p className="hf-hero-sub">{active.subtitle}</p>
          <div className="hf-hero-cta">
            <Link href="/login" className="hf-btn-accent hf-btn-lg">
              Login
            </Link>
          </div>
          <div className="hf-hero-dots" role="tablist" aria-label="Featured creatives">
            {HERO_SLIDES.map((item, i) => (
              <button
                key={item.src}
                type="button"
                role="tab"
                aria-selected={i === slide}
                className={i === slide ? 'is-active' : ''}
                onClick={() => setSlide(i)}
              />
            ))}
          </div>
        </div>
      </section>

      <section id="studio" className="hf-strip">
        <div className="hf-strip-track">
          {STUDIO_TOOLS.map((tool) => (
            <div key={tool.id} className="hf-chip">
              <span className="hf-chip-label">{tool.label}</span>
              <span className="hf-chip-blurb">{tool.blurb}</span>
            </div>
          ))}
        </div>
      </section>

      <section className="hf-features">
        <div className="hf-features-head">
          <p className="hf-kicker">AI creative suite for Meta Ads</p>
          <h2 className="hf-display">
            Brief in.
            <br />
            On-brand variants out.
          </h2>
        </div>

        {FEATURE_BLOCKS.map((block, i) => (
          <article key={block.kicker} className={`hf-feature ${i % 2 === 1 ? 'is-flip' : ''}`}>
            <div className="hf-feature-copy">
              <p className="hf-kicker">{block.kicker}</p>
              <h3 className="hf-feature-title">{block.title}</h3>
              <p className="hf-feature-body">{block.body}</p>
              <Link href="/login" className="hf-btn-accent hf-btn-lg mt-4 inline-flex">
                {block.cta}
              </Link>
            </div>
            <div className="hf-feature-media">
              <Image src={block.src} alt="" fill sizes="(max-width: 900px) 100vw, 50vw" className="object-cover" />
              <div className="hf-feature-media-veil" />
            </div>
          </article>
        ))}
      </section>

      <section id="use-cases" className="hf-presets">
        <div className="hf-presets-head">
          <div>
            <p className="hf-kicker">Image use cases</p>
            <h2 className="hf-display">CreativeStudio use cases</h2>
            <p className="hf-lede">
              The same catalogue you pick inside a brief — each tile shows a different creative direction, not the same photo recycled.
            </p>
          </div>
        </div>

        <div className="hf-preset-grid">
          {USE_CASE_SHOWCASE.map((uc) => (
            <article key={uc.id} className="hf-preset-card">
              <div className="hf-preset-media">
                <Image
                  src={uc.src}
                  alt={uc.label}
                  fill
                  sizes="(max-width: 640px) 50vw, 20vw"
                  className="object-cover"
                />
              </div>
              <div className="hf-preset-meta">
                <span className="hf-preset-group">{uc.group}</span>
                <span className="hf-preset-label">{uc.label}</span>
              </div>
            </article>
          ))}
        </div>
      </section>

      <section id="angles" className="hf-angles">
        <div className="hf-presets-head">
          <div>
            <p className="hf-kicker">Ad angles</p>
            <h2 className="hf-display">Angles that drive the frame</h2>
            <p className="hf-lede">
              Select angles in the brief. CreativeStudio assigns them across variants so every creative has a job.
            </p>
          </div>
        </div>
        <div className="hf-angle-row">
          {ANGLE_PRESETS.map((angle) => (
            <article key={angle.id} className="hf-angle-card">
              <span className="hf-angle-label">{angle.label}</span>
              <span className="hf-angle-hint">{angle.hint}</span>
            </article>
          ))}
        </div>
      </section>

      <section id="examples" className="hf-community">
        <div className="hf-presets-head">
          <div>
            <p className="hf-kicker">Niche examples</p>
            <h2 className="hf-display">Jewellery. Trade. Landscaping.</h2>
            <p className="hf-lede">
              Featured niche creatives from the hero — shown once here as campaign examples.
            </p>
          </div>
        </div>
        <div className="hf-community-grid">
          {HERO_SLIDES.map((item) => (
            <article key={item.src} className="hf-example-text">
              <p className="hf-community-eyebrow">{item.eyebrow}</p>
              <h3 className="hf-community-title">{item.title}</h3>
              <p className="hf-community-sub">{item.subtitle}</p>
            </article>
          ))}
        </div>
      </section>

      <section className="hf-final">
        <p className="hf-hero-brand hf-final-brand">
          Creative<span>Studio</span> AI
        </p>
        <h2 className="hf-display hf-final-title">Skip the deck. Make the ad.</h2>
        <p className="hf-lede hf-final-lede">
          Australian Meta creatives — brief, angles, use cases, variants, brand safety, export.
        </p>
        <div className="hf-hero-cta">
          <Link href="/login" className="hf-btn-accent hf-btn-lg">
            Login
          </Link>
        </div>
      </section>

      <footer className="hf-footer">
        <p>© {new Date().getFullYear()} CreativeStudio AI</p>
        <p>Powered by Traffic Radius</p>
      </footer>
    </div>
  )
}
