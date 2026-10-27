'use client'

import Image from 'next/image'
import Link from 'next/link'
import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { BrandMark } from '@/components/brand/BrandMark'
import { authApi } from '@/lib/api'
import { authStorage } from '@/lib/auth'

const HERO_SLIDES = [
  { src: '/landing/hero-jewellery-4k.webp', position: '62% center', label: 'Ecommerce / Jewellery', headline: 'Product storytelling', detail: '4K campaign master' },
  { src: '/landing/hero-hvac-4k.webp', position: '64% center', label: 'Local service / HVAC', headline: 'Problem-led advertising', detail: '4K campaign master' },
  { src: '/landing/hero-landscaping-4k.webp', position: '62% center', label: 'Local service / Landscaping', headline: 'Transformation campaigns', detail: '4K campaign master' },
]

const WORKFLOW = [
  { number: '01', title: 'Bring your brand', body: 'Start with a focused brief. CreativeStudio organises your brand, offer and audience context.' },
  { number: '02', title: 'Direct every reference', body: 'Assign product, logo, scene, character and general references so each asset has one clear job.' },
  { number: '03', title: 'Choose the production route', body: 'Select the image or video model, placement, aspect ratio and duration that fit the campaign.' },
  { number: '04', title: 'Review, refine and export', body: 'Inspect variants, retry individual frames and export approved assets for your media workflow.' },
]

const GALLERY_ITEMS = [
  { src: '/landing/hero-jewellery-4k.webp', label: 'Luxury product campaign', category: 'Ecommerce' },
  { src: '/landing/hero-hvac-4k.webp', label: 'Service lead generation', category: 'Local Services' },
  { src: '/landing/hero-landscaping-4k.webp', label: 'Transformation campaign', category: 'Local Services' },
  { src: '/landing/industry-dental-4k.webp', label: 'Patient confidence campaign', category: 'Healthcare' },
  { src: '/landing/industry-real-estate-4k.webp', label: 'Property launch campaign', category: 'Property' },
  { src: '/landing/industry-hospitality-4k.webp', label: 'Dining experience campaign', category: 'Hospitality' },
  { src: '/landing/industry-fitness-4k.webp', label: 'Coaching campaign', category: 'Healthcare' },
  { src: '/landing/industry-automotive-4k.webp', label: 'Premium detailing campaign', category: 'Local Services' },
]

const GALLERY_FILTERS = ['All', 'Ecommerce', 'Local Services', 'Healthcare', 'Property', 'Hospitality']

const IMAGE_MODELS = [
  { provider: 'OpenAI', model: 'GPT Image', use: 'Art-directed campaign stills', input: 'Prompt + references' },
  { provider: 'BytePlus', model: 'Seedream', use: 'Reference-led product imagery', input: 'Prompt + image inputs' },
  { provider: 'Higgsfield', model: 'Image models', use: 'Alternative visual production', input: 'Workspace configuration' },
  { provider: 'Runway', model: 'Image route', use: 'Connected production fallback', input: 'Workspace configuration' },
]

const VIDEO_MODELS = [
  { provider: 'BytePlus', model: 'Seedance 2.0 / 2.5', use: 'Cinematic scenes and B-roll', input: 'Prompt + references' },
  { provider: 'HeyGen', model: 'Avatar video', use: 'Presenter and spoken campaigns', input: 'Avatar + voice + script' },
  { provider: 'Higgsfield', model: 'Video models', use: 'Motion-led ad production', input: 'Workspace configuration' },
  { provider: 'Runway', model: 'Video route', use: 'Connected video generation', input: 'Workspace configuration' },
]

const PLATFORM_ROWS = [
  { platform: 'Meta + Instagram', formats: 'Feed, carousel, Stories, Reels', ratios: '1:1 / 4:5 / 9:16 / 1.91:1' },
  { platform: 'TikTok + Snapchat', formats: 'In-feed, Spark, Stories', ratios: '9:16 / 1:1' },
  { platform: 'YouTube', formats: 'Shorts, in-stream, display', ratios: '9:16 / 16:9 / 1:1' },
  { platform: 'LinkedIn + X + Reddit', formats: 'Feed, video, carousel', ratios: '1:1 / 16:9 / 1.91:1' },
  { platform: 'Google Display', formats: 'Responsive and fixed display', ratios: '1.91:1 + placement sizes' },
  { platform: 'Pinterest', formats: 'Standard, video, long pin', ratios: '2:3 / 1:1 / 9:16' },
]

const IMAGE_RATIO_EXAMPLES = [
  { ratio: '1:1', className: 'is-square', src: '/landing/hero-jewellery-4k.webp', title: 'Square feed', placement: 'Instagram and Facebook feed', size: '3840 x 3840' },
  { ratio: '4:3', className: 'is-four-three', src: '/landing/industry-real-estate-4k.webp', title: 'Classic landscape', placement: 'Web, editorial and display', size: '3840 x 2880' },
  { ratio: '4:5', className: 'is-four-five', src: '/landing/industry-dental-4k.webp', title: 'Portrait feed', placement: 'Instagram and Meta feed', size: '3072 x 3840' },
  { ratio: '9:16', className: 'is-nine-sixteen', src: '/landing/industry-fitness-4k.webp', title: 'Full-screen vertical', placement: 'Stories, Reels and TikTok', size: '2160 x 3840' },
  { ratio: '16:9', className: 'is-sixteen-nine', src: '/landing/industry-hospitality-4k.webp', title: 'Widescreen', placement: 'YouTube, web and display', size: '3840 x 2160' },
  { ratio: '1.91:1', className: 'is-wide-ad', src: '/landing/hero-hvac-4k.webp', title: 'Wide social ad', placement: 'Facebook and Google ads', size: '3840 x 2010' },
  { ratio: '2:3', className: 'is-two-three', src: '/landing/hero-landscaping-4k.webp', title: 'Tall discovery', placement: 'Pinterest and print', size: '2560 x 3840' },
]

const REFERENCES = [
  ['Product', 'Lock the item, packaging and important visual details.'],
  ['Character', 'Lock a presenter on HeyGen avatar video. Seedance 2.0/2.5 reject photoreal person references.'],
  ['Logo', 'Supply the approved brand mark as its own controlled asset.'],
  ['Scene', 'Guide location, composition, lighting and visual environment.'],
  ['Reference', 'Add supporting style or continuity context where needed.'],
]

const FAQS = [
  { q: 'Which image and video models can I use?', a: 'CreativeStudio routes work through configured providers. Current routes include OpenAI image models, BytePlus Seedream and Seedance, HeyGen avatar video, and optional Higgsfield and Runway providers. Availability depends on your workspace configuration.' },
  { q: 'What aspect ratios are supported?', a: 'Image workflows include 1:1, 4:3, 4:5, 9:16, 16:9, 1.91:1 and 2:3, with custom image variants where supported. Video controls include 9:16, 1:1, 16:9, 4:3 and 4:5. Each provider validates its own native formats.' },
  { q: 'Does 4:5 work natively with every video model?', a: 'No. BytePlus Seedance does not accept native 4:5 reference-to-video output. CreativeStudio maps that request to 3:4 and clearly identifies the crop needed for a 4:5 Meta feed asset.' },
  { q: 'How long can a video be?', a: 'The production interface supports compositions up to four minutes. Individual model clips can have shorter limits, so longer videos may be planned and assembled from multiple scenes rather than generated in one call.' },
  { q: 'How many reference images can I add?', a: 'You can assign up to nine reference assets across product, logo, scene, character and general reference roles. Provider-specific input limits are checked during production.' },
  { q: 'Does CreativeStudio publish directly to ad platforms?', a: 'CreativeStudio prepares and exports campaign-ready assets. Publishing, campaign setup and media spend remain in the relevant advertising platform unless a connected export workflow is explicitly available in your workspace.' },
  { q: 'How is generation cost calculated?', a: 'Cost depends on the selected provider, model, resolution, duration and number of outputs. CreativeStudio shows an estimate using those production settings; final provider billing can vary with actual usage.' },
  {
    q: 'Can I keep a person consistent across scenes?',
    a: 'On HeyGen avatar video, yes — the same avatar and voice carry through your script and final composition. On BytePlus Seedance 2.0 and 2.5, photoreal identity in a character reference is blocked by provider policy; those jobs are rejected with a clear error instead of inventing a different person. Use HeyGen for a consistent on-camera presenter, and Seedance for cinematic B-roll with product, scene, logo or non-photoreal anchors.',
  },
]

export default function LandingPage() {
  const router = useRouter()
  const [slide, setSlide] = useState(0)
  const [galleryFilter, setGalleryFilter] = useState('All')
  const [modelType, setModelType] = useState<'image' | 'video'>('image')

  useEffect(() => {
    const token = authStorage.getAccessToken()
    if (!token) return
    let active = true
    authApi.getMe().then((user) => {
      if (active && user) router.replace('/dashboard')
    }).catch(() => authStorage.clear())
    return () => { active = false }
  }, [router])

  useEffect(() => {
    const id = window.setInterval(() => setSlide((current) => (current + 1) % HERO_SLIDES.length), 5600)
    return () => window.clearInterval(id)
  }, [])

  const visibleGallery = galleryFilter === 'All' ? GALLERY_ITEMS : GALLERY_ITEMS.filter((item) => item.category === galleryFilter)
  const visibleModels = modelType === 'image' ? IMAGE_MODELS : VIDEO_MODELS
  const activeHero = HERO_SLIDES[slide]

  return (
    <div className="lp-root">
      <header className="lp-nav">
        <div className="lp-nav-inner">
          <Link href="/" className="lp-logo" aria-label="CreativeStudio AI home">
            <BrandMark size={34} className="lp-logo-mark" />
            <span>CreativeStudio <strong>AI</strong></span>
          </Link>
          <nav className="lp-nav-links" aria-label="Main navigation">
            <a href="#workflow">How it works</a><a href="#models">Models</a><a href="#platforms">Platforms</a><a href="#pricing">Pricing</a><a href="#faq">FAQ</a>
          </nav>
          <div className="lp-nav-actions">
            <Link href="/login" className="lp-nav-login">Sign in</Link>
            <Link href="/login" className="lp-button lp-button-small">Start creating</Link>
          </div>
        </div>
      </header>

      <main>
        <section className="lp-hero" aria-labelledby="hero-title">
          {HERO_SLIDES.map((item, index) => (
            <div key={item.src} className={`lp-hero-image ${index === slide ? 'is-active' : ''}`} aria-hidden={index !== slide}>
              <Image
                src={item.src}
                alt=""
                fill
                priority={index === 0}
                sizes="100vw"
                className="object-cover"
                style={{ objectPosition: item.position }}
              />
            </div>
          ))}
          <div className="lp-hero-shade" />
          <div className="lp-hero-inner">
            <div className="lp-hero-copy">
              <p className="lp-eyebrow lp-eyebrow-light">One production system. Every campaign format.</p>
              <h1 id="hero-title">CreativeStudio AI</h1>
              <p className="lp-hero-lede">Turn a brand brief and approved references into art-directed image and video campaigns built for the placement.</p>
              <div className="lp-hero-actions">
                <Link href="/login" className="lp-button">Open CreativeStudio</Link>
                <a href="#workflow" className="lp-text-link">See how production works</a>
              </div>
              <div className="lp-hero-proof" aria-label="CreativeStudio capabilities">
                <div><strong>5</strong><span>reference roles</span></div>
                <div><strong>9</strong><span>assets per brief</span></div>
                <div><strong>4 min</strong><span>video compositions</span></div>
              </div>
            </div>
            <div className="lp-hero-caption" aria-live="polite">
              <span>{activeHero.label}</span><strong>{activeHero.headline}</strong><small>{activeHero.detail}</small>
              <div className="lp-hero-dots" role="tablist" aria-label="Featured campaign examples">
                {HERO_SLIDES.map((item, index) => (
                  <button key={item.src} type="button" role="tab" aria-label={`Show ${item.label}`} aria-selected={index === slide} className={index === slide ? 'is-active' : ''} onClick={() => setSlide(index)} />
                ))}
              </div>
            </div>
          </div>
        </section>

        <section className="lp-capability-bar" aria-label="Core capabilities"><div className="lp-page-width">
          <span>Brand intelligence</span><span>Campaign strategy</span><span>Image generation</span><span>Avatar video</span><span>Cinematic B-roll</span><span>Placement-ready export</span>
        </div></section>

        <section id="workflow" className="lp-section lp-workflow"><div className="lp-page-width">
          <div className="lp-section-heading lp-heading-row"><div><p className="lp-eyebrow">Built for production, not prompting</p><h2>A controlled path from brief to campaign.</h2></div><p>CreativeStudio keeps brand context, references, formats and generation settings together so a campaign can be reviewed as one system.</p></div>
          <div className="lp-workflow-grid">{WORKFLOW.map((step) => <article key={step.number}><span>{step.number}</span><h3>{step.title}</h3><p>{step.body}</p></article>)}</div>
        </div></section>

        <section id="examples" className="lp-section lp-gallery-section"><div className="lp-page-width">
          <div className="lp-section-heading lp-heading-row lp-heading-light"><div><p className="lp-eyebrow lp-eyebrow-light">Meta campaign references</p><h2>Industry work, not a wall of products.</h2></div>
            <div className="lp-segmented" role="tablist" aria-label="Filter campaign references by industry">{GALLERY_FILTERS.map((filter) => <button key={filter} type="button" role="tab" aria-selected={galleryFilter === filter} className={galleryFilter === filter ? 'is-active' : ''} onClick={() => setGalleryFilter(filter)}>{filter}</button>)}</div>
          </div>
          <div className="lp-gallery-grid">{visibleGallery.map((item) => <article key={item.src} className="lp-gallery-item"><Image src={item.src} alt={item.label} fill sizes="(max-width: 700px) 100vw, (max-width: 1080px) 50vw, 33vw" className="object-cover" /><div className="lp-gallery-meta"><span>{item.category}</span><strong>{item.label}</strong><small>4K campaign master</small></div></article>)}</div>
        </div></section>

        <section id="models" className="lp-section lp-models"><div className="lp-page-width lp-model-layout">
          <div className="lp-model-intro"><p className="lp-eyebrow">Model directory</p><h2>Choose the route that fits the job.</h2><p className="lp-section-copy">CreativeStudio does not hide every task behind one generic button. Select the production route based on the asset, motion and control you need.</p>
            <div className="lp-segmented lp-segmented-dark" role="tablist" aria-label="Model type"><button type="button" role="tab" aria-selected={modelType === 'image'} className={modelType === 'image' ? 'is-active' : ''} onClick={() => setModelType('image')}>Image models</button><button type="button" role="tab" aria-selected={modelType === 'video'} className={modelType === 'video' ? 'is-active' : ''} onClick={() => setModelType('video')}>Video models</button></div>
            <p className="lp-config-note">Provider availability depends on workspace configuration.</p>
          </div>
          <div className="lp-model-table" role="table" aria-label={`${modelType} model directory`}><div className="lp-model-row lp-model-head" role="row"><span role="columnheader">Provider / model</span><span role="columnheader">Best for</span><span role="columnheader">Input</span></div>{visibleModels.map((item) => <div className="lp-model-row" role="row" key={`${item.provider}-${item.model}`}><span role="cell"><small>{item.provider}</small><strong>{item.model}</strong></span><span role="cell">{item.use}</span><span role="cell">{item.input}</span></div>)}</div>
        </div></section>

        <section className="lp-section lp-references"><div className="lp-page-width lp-reference-layout">
          <div className="lp-reference-image"><Image src="/landing/feat-brief.jpg" alt="Creative campaign planning example" fill sizes="(max-width: 900px) 100vw, 50vw" className="object-cover" /><div className="lp-reference-badge"><strong>Up to 9</strong><span>role-based references</span></div></div>
          <div className="lp-reference-copy"><p className="lp-eyebrow">Reference control</p><h2>Tell the system what every asset means.</h2><p className="lp-section-copy">A logo is not a product reference. A character is not a mood board. Assigning roles reduces contradictory instructions and gives every model clearer context.</p><div className="lp-reference-list">{REFERENCES.map(([title, body]) => <div key={title}><strong>{title}</strong><span>{body}</span></div>)}</div></div>
        </div></section>

        <section id="platforms" className="lp-section lp-platforms"><div className="lp-page-width">
          <div className="lp-section-heading lp-heading-row"><div><p className="lp-eyebrow">Platforms and formats</p><h2>Design for the placement from the start.</h2></div><p>Ratios are production decisions. Choose the destination before generation instead of forcing one master asset into every feed.</p></div>
          <div className="lp-ratio-heading"><div><span>Supported image outputs</span><strong>One campaign, shaped for every placement.</strong></div><p>Each preview shows the real canvas shape CreativeStudio can prepare. Pixel dimensions are representative 4K-class export examples.</p></div>
          <div className="lp-ratio-grid">
            {IMAGE_RATIO_EXAMPLES.map((item) => (
              <article className="lp-ratio-card" key={item.ratio}>
                <div className="lp-ratio-stage">
                  <div className={`lp-ratio-frame ${item.className}`}>
                    <Image src={item.src} alt={`${item.title} example in ${item.ratio} ratio`} fill sizes="(max-width: 700px) 80vw, (max-width: 1100px) 40vw, 22vw" className="object-cover" />
                    <span>{item.ratio}</span>
                  </div>
                </div>
                <div className="lp-ratio-copy"><strong>{item.title}</strong><span>{item.placement}</span><small>{item.size} px</small></div>
              </article>
            ))}
          </div>
          <div className="lp-platform-table"><div className="lp-platform-row lp-platform-head"><span>Platform</span><span>Placements</span><span>Primary ratios</span></div>{PLATFORM_ROWS.map((row) => <div className="lp-platform-row" key={row.platform}><strong>{row.platform}</strong><span>{row.formats}</span><code>{row.ratios}</code></div>)}</div>
          <div className="lp-format-callout"><div><span>Image</span><strong>1:1 / 4:3 / 4:5 / 9:16 / 16:9 / 1.91:1 / 2:3</strong></div><div><span>Video</span><strong>9:16 / 1:1 / 16:9 / 4:3 / 4:5*</strong></div><p>* Native support varies by provider. Seedance maps 4:5 reference video to 3:4 for cropping.</p></div>
        </div></section>

        <section id="pricing" className="lp-section lp-pricing"><div className="lp-page-width lp-pricing-layout">
          <div><p className="lp-eyebrow lp-eyebrow-light">Transparent production cost</p><h2>Know what drives the estimate before you generate.</h2><p>There is no honest single price for every output. Cost changes with the provider, model, resolution, duration and number of variants.</p><Link href="/login" className="lp-button">Open the studio</Link></div>
          <div className="lp-estimate-panel" aria-label="Generation cost factors"><div className="lp-estimate-top"><span>Generation estimate</span><strong>Calculated before run</strong></div><div className="lp-estimate-line"><span>Provider and model</span><b>Selected route</b></div><div className="lp-estimate-line"><span>Output</span><b>Resolution + ratio</b></div><div className="lp-estimate-line"><span>Video</span><b>Seconds + clip count</b></div><div className="lp-estimate-line"><span>Variants</span><b>Number of outputs</b></div><p>Estimates use the configured provider rate. Final billing may vary with actual provider usage.</p></div>
        </div></section>

        <section id="faq" className="lp-section lp-faq"><div className="lp-page-width lp-faq-layout">
          <div className="lp-faq-intro"><p className="lp-eyebrow">Frequently asked questions</p><h2>Clear answers before production starts.</h2><p className="lp-section-copy">The important conditions are part of the workflow, not hidden after generation.</p></div>
          <div className="lp-faq-list">{FAQS.map((item, index) => <details key={item.q} open={index === 0}><summary>{item.q}<span aria-hidden="true">+</span></summary><p>{item.a}</p></details>)}</div>
        </div></section>

        <section className="lp-final"><div className="lp-final-image"><Image src="/landing/feat-formats.jpg" alt="CreativeStudio campaign formats" fill sizes="100vw" className="object-cover" /></div><div className="lp-final-shade" /><div className="lp-page-width lp-final-content"><p className="lp-eyebrow lp-eyebrow-light">Ready for the next campaign</p><h2>Build the brief. Direct the models. Ship the creative.</h2><p>One workspace for brand context, references, image variants, video production and review.</p><Link href="/login" className="lp-button">Start creating</Link></div></section>
      </main>

      <footer className="lp-footer"><div className="lp-page-width lp-footer-grid"><div><Link href="/" className="lp-logo"><BrandMark size={32} className="lp-logo-mark" /><span>CreativeStudio <strong>AI</strong></span></Link><p>Professional image and video production for performance teams.</p></div><div><strong>Product</strong><a href="#workflow">How it works</a><a href="#models">Models</a><a href="#platforms">Formats</a></div><div><strong>Company</strong><a href="#pricing">Pricing</a><a href="#faq">FAQ</a><Link href="/login">Sign in</Link></div><div><strong>Production</strong><span>Brand-controlled inputs</span><span>Provider-aware formats</span><span>Campaign-ready exports</span></div></div><div className="lp-page-width lp-footer-bottom"><span>Copyright {new Date().getFullYear()} CreativeStudio AI</span><span>Powered by Traffic Radius</span></div></footer>
    </div>
  )
}
