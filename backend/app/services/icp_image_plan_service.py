"""ICP-driven image variant planning from campaign name (+ brand / industry)."""

from __future__ import annotations

import json
import logging
import random
import re
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.services.ad_angle_library import (
    ANGLE_GUIDANCE,
    assign_angles_to_variants,
    per_variant_angle_instructions,
)
from app.services.australian_copy import AUSTRALIAN_ENGLISH_BRIEF_RULES
from app.services.image_prompt_service import (
    _SELECTOR_FALLBACK_USE_CASES,
    _USE_CASE_CATALOGUE,
    _USE_CASE_DESCRIPTIONS,
    _get_openrouter_client,
)

logger = logging.getLogger(__name__)

# Agency brand types (Brand Kit) — visuals should match the SERVICE sold (ads, leads, targeting),
# not random client-vertical stock scenes (e.g. warehouse for a Meta ads campaign).
_AGENCY_BRAND_INDUSTRIES = frozenset({
    "digital_marketing",
    "marketing",
    "general",  # generic agency default
    "pro_services",  # marketing / pro services agency in Brand Kit
})

# Scene pools — suggestions for variety, not hard bans. Laptop/coffee/notebook are fine when they fit.
_INDUSTRY_SCENE_POOLS: dict[str, list[str]] = {
    "digital_marketing": [
        "Marketing manager reviewing Meta Ads Manager on screen, frustrated by wasted spend, modern AU office",
        "Business owner scrolling Facebook feed on phone, noticing competitor ads, candid documentary moment",
        "Agency strategist and client at screen reviewing ad targeting map / audience breakdown",
        "Split focus: poor-performing ads dashboard vs relieved owner after fix — same person, different mood",
        "Creative director reviewing ad mockups on large monitor, performance metrics visible, team in background",
        "Small business owner on laptop in real workplace (warehouse office, shop back room, or home studio) checking lead form results — workplace matches ICP, screen shows ads/leads context",
    ],
    "wholesale": [
        "Wholesale warehouse aisle: ops manager with handheld scanner beside pallet racking, industrial daylight",
        "Loading dock: delivery truck check-off, clipboard and hi-vis vest",
        "Distribution centre: worker at pick slot while forklift moves in background",
        "Distributor back-office reviewing stock reports at desk with warehouse visible through window",
    ],
    "trade": [
        "Residential job site: tradie on ladder, tool belt and van visible",
        "Driveway service call: plumber under sink with client watching, natural daylight",
        "Commercial fit-out: electrician at switchboard, industrial interior",
        "Tradie between jobs in van checking phone for next lead, suburban AU street",
    ],
    "pro_services": [
        "Glass meeting room: advisor presenting strategy deck to clients, city view soft blur",
        "Professional at desk with client consultation, warm corporate light",
        "Whiteboard strategy session: framework sketched, collaborative mood",
        "Reception greeting client, trust and authority",
    ],
    "retail": [
        "Boutique shop floor: owner preparing display before weekend rush, warm pendant lights",
        "Saturday trade: staff at counter, customers browsing",
        "Manager carrying stock from back room to floor, energetic mood",
        "Shop window: passer-by pausing at display, inviting interior glow",
    ],
    "ecommerce": [
        "Home packing bench: branded boxes, shipping labels, hands packing order",
        "Garage studio: product samples and ring light, authentic DTC setup",
        "Founder at laptop reviewing online orders and ad performance side by side",
        "Courier pickup at front door: founder handing parcel to driver",
    ],
    "general": [
        "Documentary portrait: person in their real workplace solving the ICP pain — vary setting each variant",
        "Team huddle in authentic small-business workspace, candid AU commercial",
        "Over-shoulder whiteboard session circling one priority problem",
        "Environmental wide shot: subject small in frame, workplace context tells the story",
        "Morning light office: focused work moment with tools that fit the ICP (laptop, phone, or industry props as needed)",
    ],
}

_INDUSTRY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "digital_marketing": (
        "meta ads", "facebook ads", "instagram ads", "google ads", "ad targeting", "ad spend",
        "ppc", "paid social", "lead gen", "leads", "roas", "cac", "traffic", "digital marketing",
        "marketing agency", "ads audit", "campaign",
    ),
    "wholesale": ("wholesale", "distributor", "distribution", "dead stock", "inventory", "margin", "warehouse"),
    "trade": ("trade", "tradie", "plumb", "electric", "hvac", "builder", "roof", "construction"),
    "pro_services": ("consult", "account", "legal", "advisory", "dental", "clinic", "law firm"),
    "retail": ("retail", "store", "shop", "boutique", "foot traffic", "brick and mortar"),
    "ecommerce": ("ecommerce", "e-commerce", "dtc", "online store", "shopify", "unboxing"),
}

_VARIETY_GUIDANCE = """
- Vary scene, environment, props, lighting, and camera angle across variants — do NOT repeat the same setup.
- Do NOT use the exact same laptop + coffee + notebook composition in every variant; rotate settings.
- Laptop, coffee, notebook, and desk scenes ARE allowed when they genuinely fit the ICP and campaign.
- Pick visuals that match what is being SOLD: e.g. a digital marketing agency → ads, targeting, leads, performance.
- Client industry (wholesale, trade, etc.) informs WHO is in the scene; the brand service informs WHAT problem is shown.
""".strip()

_INDUSTRY_REFERENCE_ICPS = """
WHOLESALE — Margin Guardian:
Ops/purchasing manager, mid-size AU distributor. Pain: dead stock, missed fills, thin margins.
Visual: warehouse aisle, pallet racking, clipboard/tablet, industrial daylight.

TRADE — Booked-Out Tradie:
Owner-operator plumber/electric/HVAC, 1–8 staff. Pain: feast-or-famine leads, admin after hours.
Visual: residential job site, van with tools, tradie in workwear, golden-hour outdoor AU.

PROFESSIONAL SERVICES — Trust Builder:
Managing Partner (CPA) at a mid-tier accounting/advisory firm in Melbourne CBD with a satellite in Geelong. Decision power on marketing spend and partner alignment for a 6-month horizon.
Pain: referrals drying up, internal partner buy-in politics, competitors with stronger SEO/content and clearer Google Ads presence, plus fear of non-compliant or overly-salesy regulated marketing.
They need partner-ready proof (ROI, milestones, cost-per-client clarity) and an agency workflow that upskills the marketing coordinator instead of sidelining her.
Visual: modern Australian office, glass meeting room in warm morning light; managing partner presenting a partner-ready 90-day digital growth plan on a laptop/tablet; subtle blurred compliance/governance notes; monitor shows generic (non-readable) leads/pipeline/ROI charts; authentic tailored professional mood.

RETAIL — Floor Manager:
Specialty retail owner/manager. Pain: uneven foot traffic, discount dependency.
Visual: boutique floor, styled shelves, warm pendant lights, customer at counter.

ECOMMERCE — Cart Chaser:
DTC founder/marketing lead. Pain: creative fatigue, rising CAC.
Visual: home-studio unboxing, lifestyle product-in-use, crisp ecommerce aesthetic.

DIGITAL MARKETING AGENCY — Growth Partner:
Marketing manager or SMB owner. Pain: wasted ad spend, wrong targeting, leads going to competitors.
Visual: Meta/social ads context, dashboards, phone feed, targeting — NOT unrelated warehouse ops unless ads are the subject.
""".strip()

_ICP_FROM_CAMPAIGN_SYSTEM = f"""
You are an expert ICP strategist for AUSTRALIAN businesses.

Build the Ideal Customer Profile from:
- INDUSTRY = what the BRAND is (e.g. Mortgage Broking)
- NICHE = campaign specialty / offer angle (e.g. First Home Buyers, Refinance, Investment Loans)
- OBJECTIVE = what the ad must drive (awareness / traffic / lead_generation / conversions / purchase)
- BRAND NAME = the advertiser

CRITICAL RULES:
1) The ICP is the PERSON WHO SEES THE AD and should take the objective action — usually the brand's end customer, NOT another business in the same industry.
2) If INDUSTRY is Mortgage Broking / finance broker and OBJECTIVE is conversions / purchase / add_to_cart:
   → ICP = home buyers, refinancers, or property owners who need a loan — NOT other mortgage brokers.
   → Do NOT invent a B2B "broker selling lead-gen systems to other brokers" story unless NICHE explicitly says the brand sells lead-gen software/services TO brokers.
3) If OBJECTIVE is lead_generation: ICP may be prospects filling a form for the brand's service (still end customers unless niche says otherwise).
4) Niche words like "Lead Generation" under a broker brand usually mean HOW the broker markets home loans — still write ads for home-loan buyers unless niche clearly means selling leads as a product.
5) Never ignore OBJECTIVE. Purchase/conversions = buyer ready to act on the brand's core offer.

Output plain text in this exact format (no markdown):

AVATAR NAME: <FirstName LastName — "Archetype Nickname">
IDENTITY: <2-3 sentences: role, company/household, AU location, decision power>
CURRENT REALITY: <2-3 sentences: what is happening in their world right now>
CORE PAIN: <1-2 sentences: deepest frustration>
DESIRED OUTCOME: <1-2 sentences: what they want after the solution>
KEY OBJECTION: <1 sentence>
BUYING TRIGGER: <1 sentence>
LANGUAGE THEY USE: <3-5 short Australian phrases>

Match wholesale/trade/pro services/retail/ecommerce archetypes when industry/niche maps to them.
{AUSTRALIAN_ENGLISH_BRIEF_RULES}
Plain text only — no bullets, no extra sections.
""".strip()

_VARIANTS_SYSTEM = """
You are an award-winning Creative Director at a global advertising agency, producing
high-converting Australian digital ad creatives. Your job is NOT to generate beautiful
AI images — it is to generate ADVERTISEMENTS that convert.

MARKETING WORKFLOW (mandatory order — never skip):
The campaign inputs arrive in this priority: 1) Industry, 2) Niche, 3) Brand,
4) Campaign Objective, 5) Ad Angle / Hook Framework. These five define the marketing intent.

STEP 1 — CAMPAIGN INTENT (derive BEFORE writing anything, output it per variant):
- audience: who exactly sees this ad (from the ICP)?
- problem: what pain are they living with right now?
- action: what must they do after seeing the ad (from the objective)?
- emotion: what single emotion should the creative trigger (fear of missing out, relief, hope, urgency, pride)?
- single_message: the ONE sentence this creative must communicate. One ad = one message.

STEP 2 — DESIGN VISUAL + COPY TOGETHER (one cohesive advertisement):
The image is NEVER a pretty background with text placed on top.
The VISUAL must communicate 70–80% of the message BEFORE the viewer reads a word:
- What is happening? What problem is shown? What solution is offered? What should I do?
The on-image text reinforces the remaining 20–30%.

VISUAL REASONING (critical — THINK, do not template; this applies to ANY industry):
Apply this reasoning to every variant — the specifics must come from THIS campaign's inputs,
not from a memorised example:
1. THE STRANGER TEST (two questions, BOTH must pass with all text removed):
   a) "What is this ad about?" — the stranger must instantly name the industry/niche.
      The frame MUST contain a clear CATEGORY CUE: e.g. for home loans a house must be
      visible somewhere in the scene (through the window, on the property sheet, keys,
      a sold sign, the front door); for a gym, the training space; for food delivery,
      the meal arriving. NEVER remove the category from the frame — without it the ad
      reads as generic.
   b) "What is being promised?" — the stranger must also see the PROMISE, not just the
      category. A house alone says "real estate-ish"; it does not say "low interest".
2. SETTING MUST GROUND THE INDUSTRY (mandatory on EVERY single variant — this is a common
   failure mode, do not let some variants pass and others fail):
   - Whenever a person is the subject, put them in — or visibly near — a LOCATION or OBJECT
     set that unmistakably belongs to THIS industry's world. Work this out fresh for whatever
     industry is given; do not rely on memorised examples. Ask: "where would this exact
     moment realistically happen, and what object from that world can sit in frame?"
     Examples of the THINKING (not a fixed list — invent the equivalent for any industry):
     dental → clinic interior, treatment chair, overhead light, clinical mirror, shade guide,
     whitening tray; mortgage/finance → paperwork with rate figures, house glimpsed through a
     window, keys, calculator; fitness → gym floor, equipment, training space; legal → office
     with case files, gavel/scales motif, courthouse exterior; hospitality/food → kitchen,
     plated dish, dining room; automotive → showroom, workshop bay, the vehicle itself;
     beauty → salon chair, mirror, treatment tools; real estate → property exterior, open
     home signage, for-sale board.
   - A GENERIC location (plain office desk, blank laptop screen, neutral hallway, empty room)
     with NO industry object anywhere in frame is a FAILURE, even if the emotion and copy are
     perfect — the viewer must recognise the industry from the background alone, not just from
     the on-image text.
   - If the story requires a non-industry location (e.g. someone self-conscious at their own
     work desk before a dental fix), you MUST still insert a bridging industry object into
     that scene (a phone screen showing a booking confirmation, a hand mirror, a takeaway cup
     from the clinic) — never leave the setting industry-neutral.
3. CATEGORY CUE + PROOF TOGETHER: the winning frame is ONE decisive moment — the industry
   object grounds the scene, and a prop, gesture, or reaction PROVES the single_message at
   a glance: a result being revealed, a burden visibly lifted, a person reacting to the benefit.
   (e.g. home-loan ad: the house visible through the window WHILE the buyer studies a document
   showing a lower rate — the stranger reads "cheaper home loan" in one glance.)
   CRITICAL — SINGLE MOMENT ONLY: do NOT describe two timeframes, two settings, or two
   versions of the same person in one image. No "before-and-after in one frame", no
   "split-moment", no "left side shows X / right side shows Y", no narrative montage.
   Image models cannot render two moments in one photo — they generate a generic portrait
   instead. Pick the SINGLE most powerful moment: either the problem peak (person mid-struggle)
   OR the solution payoff (person experiencing the result). One moment. One emotion. One scene.
4. EMOTION CHECK (every face must ACT its story role — direct them like a film director):
   - Choose ONE story state per image: PROBLEM state OR SOLUTION state, never both.
   - For the subject, spell out their exact facial expression AND body language to match the
     chosen state. Never leave expression to chance — image models default to a catalogue smile.
   - PROBLEM state: visibly negative and specific — lips pressed closed, eyes lowered, hand
     covering mouth, tense shoulders, worried brow, avoiding camera gaze.
   - SOLUTION state: open confident smile, relaxed posture, direct gaze into camera.
   - Write micro-direction into the prompt ("eyebrows pulled together", "exhale of relief",
     "jaw relaxed, eyes lit") so the emotion cannot be misread.
   - NEVER write contradictory directions: do not say "conflicted but determined" or "serious
     but hopeful" — pick one dominant emotion and describe only that.
5. BANNED: generic stock-photo energy — smiling person at laptop with no story, team huddles,
   meaningless handshakes, empty office scenes, and DEFAULT SMILES on people who are supposed
   to be worried, embarrassed, or frustrated. Every prop and every expression must earn its
   place in the story.
- The prompt must read like an art-directed ad brief: subject, action, story props, emotion on
  faces, lighting, camera angle — all serving the single_message.

TWO LAYERS OF COPY (critical):
1) `hook` + `message` = the FULL post hook and headline (strong and complete — used as the ad caption/primary text).
2) `image_hook` + `image_headline` = SHORT catchy lines BURNED onto the photo. Same idea as hook/message,
   compressed into 3-second scroll-stoppers — NOT a paste of the full lines, NOT a new random angle.
3) `offer` = longer caption follow-up — NEVER burned onto the image.

Example (aligned correctly):
- single_message: "A broker gets you rates the big banks won't give you."
- hook: "Thousands of homebuyers just like you are getting rates the big four won't match"
- message: "Stop comparing bank offers and start accessing broker-only rates that save real money over 30 years"
- image_hook: "Big banks aren't your only option"
- image_headline: "Access lower broker rates"
- visual: buyer at kitchen table, bank letters pushed aside, broker comparison sheet with a visibly
  lower rate circled in green — relief starting to show on their face.
WRONG: inventing a new FOMO angle on the image ("Peers are locking in better rates") that breaks the single_message.
NOTE: this example only illustrates the reasoning — NEVER reuse its scene, industry, or wording.
Derive every visual from THIS campaign's industry, niche, brand, objective, angle, and ICP.

Output ONLY valid JSON:
{
  "variants": [
    {
      "use_cases": ["id1"],
      "intent": {
        "audience": "one line",
        "problem": "one line",
        "action": "one line",
        "emotion": "one word or phrase",
        "single_message": "the ONE thing this creative communicates"
      },
      "hook": "full post hook — strong and complete",
      "message": "full post headline — strong and complete",
      "image_hook": "max 6 words, catchy, same idea as hook",
      "image_headline": "max 8 words, catchy, same idea as message",
      "cta": "2-4 word button text unique to this variant",
      "offer": "caption follow-up in 2–3 sentences, never burned on the image",
      "prompt": "art-directed image prompt, one paragraph 120-260 words — single moment, single setting, single emotion. Visual tells the story WITHOUT describing two timeframes or two scenes.",
      "reasoning": "one sentence: name the industry-specific location/object visible in the background (the setting cue), what a stranger would say the image shows with text removed (must match the single_message), and how the copy reinforces it"
    }
  ]
}

Rules:
- Each variant MUST differ in scene, angle, hook, message, image lines, CTA, use cases, environment, props, and lighting — but each variant is ONE message told cohesively.
- When a VARIANT AD ANGLE ASSIGNMENT is provided, that variant MUST use ONLY that angle for intent + hook + visual.
- When AD STYLES / HOOK FRAMEWORKS are provided, they are MANDATORY — hooks AND visuals must clearly match them.
- If pattern_interrupt is selected: NEVER produce generic stock meeting/laptop huddle scenes; the image must feel unexpected and scroll-stopping; do NOT use the phrase "professional stock photography".
- use_cases: 1-3 ids from the catalogue only.
- prompt MUST describe the visual story FIRST (subject, action, stakes, emotion, props), THEN the exact on-image text: burn ONLY image_hook + image_headline + CTA. Never put full hook/message/offer text on the image.
- prompt MUST mention the selected ad style by name when frameworks are provided (e.g. "pattern interrupt stop-the-scroll commercial").
- ON-IMAGE COPY: industry/niche vocabulary, speaks to the ICP's fear or desire, Australian English, never the persona's first name.
- CTA RULES (critical):
  - Every variant MUST include its own `cta` field, matched to the objective's action (e.g. Book Consultation, Get Free Audit, Claim Free Review, Book Free Quote).
  - Do NOT use "Learn More" unless the campaign is pure awareness with no conversion action.
  - If a CTA HINT is provided, treat it as optional guidance — still vary CTAs across variants when it improves the angle.
  - Never repeat the exact same CTA across all variants in one batch.
- Human subjects: sharp visible faces, authentic Australian context, real emotion — not catalogue smiles.
- CHILDREN IN ADS (critical — Runway content policy): if the subject is a child or family with children, NEVER describe the child as anxious, scared, frightened, crying, distressed, grimacing, wincing, mouth-open-in-pain, or in a vulnerable medical situation. Show children as calm, curious, smiling, or happy. Dental-context children must be relaxed/content in a colourful child-friendly environment, not in a clinical chair looking worried.
- Single full-bleed photo — ONE moment, ONE setting, ONE emotion. NO collage, NO split panels,
  NO "before and after in one frame", NO "left side / right side" compositions, NO watermarks.
  Image models cannot render two narrative moments in one photo — describe only a single scene.

UNIQUENESS (critical):
- Follow the REQUIRED SCENE MANDATE for each variant as a starting point, then make it specific to the ICP and the single_message.
- Match the visual to what the BRAND SELLS and who the ICP is — service context beats random industry stock imagery.
- Vary camera angle, time of day, interior vs exterior, and subject action across variants.
- Avoid repeating the same scene/prop combo across variants in one batch (e.g. do not generate three café-laptop shots).
""".strip()


def _carousel_story_roles(count: int, angle_assignments: list[str]) -> str:
    """Build a swipe-story brief so carousel cards read as one social post sequence."""
    n = max(1, count)
    lines = [
        "CAROUSEL SWIPE STORY (mandatory — this is ONE Meta/LinkedIn carousel post):",
        f"- Produce exactly {n} cards that form ONE continuous narrative a viewer swipes through.",
        "- Same ICP, same campaign, same brand offer — do NOT invent unrelated mini-campaigns.",
        "- Card 1 = PROBLEM (stop the scroll, name the pain).",
        "- Middle card(s) = AGITATE / PROOF / MYTH (deepen stakes, social proof, bust objections).",
        "- Final card = SOLUTION + clear CTA (calm control, broker/brand path forward).",
        "- Hooks/headlines must ADVANCE the story — card N should feel like the next beat after card N-1.",
        "- On-image lines stay short, but must match THAT card's beat (not a random new angle).",
        "- Visual continuity: related colour grade / setting family is fine; each card still a distinct photo.",
        "- Last card CTA should be the strongest action CTA; earlier cards may tease or use softer CTAs.",
        "",
        "PER-CARD STORY BEAT + AD ANGLE:",
    ]
    for i in range(n):
        if n == 1:
            role = "FULL story in one card (problem → hint of solution)"
        elif i == 0:
            role = "PROBLEM — open the wound / pattern interrupt on the pain"
        elif i == n - 1:
            role = "SOLUTION — resolve with brand path + strong CTA"
        elif i == 1 and n >= 3:
            role = "AGITATE — make the cost of inaction feel real"
        else:
            role = "PROOF / DEPTH — evidence, myth-bust, or social proof that bridges to the solution"
        angle = angle_assignments[i] if i < len(angle_assignments) else ""
        angle_bit = f" | ad angle: {angle}" if angle else ""
        lines.append(f"- Card {i + 1}/{n}: {role}{angle_bit}")
    return "\n".join(lines)


def _billboard_words(text: str, max_words: int) -> str:
    """Clamp on-image copy to a short billboard line."""
    words = [w for w in (text or "").strip().split() if w]
    if not words:
        return ""
    clipped = " ".join(words[:max_words]).strip(" ,;:-")
    # Drop trailing dangling connectors after hard clip
    while clipped.lower().endswith(("to", "for", "and", "or", "of", "a", "the", "with")):
        parts = clipped.split()
        if len(parts) <= 1:
            break
        clipped = " ".join(parts[:-1])
    return clipped


def _related_image_lines(hook: str, message: str) -> tuple[str, str]:
    """
    Meaning-preserving condensed lines for the photo.
    Prefer short rewrites that keep the same idea — never invent a new angle,
    and never return a broken word-clip of the full post hook.
    """
    hook_l = (hook or "").lower()
    msg_l = (message or "").lower()
    combined = f"{hook_l} {msg_l}"

    # Domain-aware condensations (same idea as full copy, billboard length).
    if any(k in combined for k in ("big four", "big bank", "bank offer", "bank rate")):
        image_hook = "Big banks aren't your only option"
        image_headline = "Access lower broker rates"
    elif "broker" in combined and "rate" in combined:
        image_hook = "Broker-only rates beat banks"
        image_headline = "See what you could save"
    elif "rate" in combined and any(k in combined for k in ("save", "saving", "lower", "cheaper")):
        image_hook = "Still overpaying on rates?"
        image_headline = "Lock a better home loan"
    elif any(k in combined for k in ("first home", "homebuyer", "home buyer", "home loan")):
        image_hook = "Ready for a better loan?"
        image_headline = "Compare broker-only rates"
    elif any(k in combined for k in ("refinance", "refi")):
        image_hook = "Refinance before rates move"
        image_headline = "Check your broker options"
    elif any(k in combined for k in ("lead", "tyre", "tire kicker", "convert")):
        image_hook = "Tired of tyre-kicker leads?"
        image_headline = "Attract ready-to-act buyers"
    else:
        # Last resort: short clean clip, but strip dangling junk and avoid "?" spam.
        image_hook = _billboard_words(hook, 6)
        image_headline = _billboard_words(message, 8)
        # If clip is basically the start of the long hook, tighten further.
        if hook and image_hook and hook.lower().startswith(image_hook.lower().rstrip("?")):
            nouns = [
                w for w in re.findall(r"[A-Za-z][A-Za-z'-]+", hook)
                if w.lower() not in {
                    "the", "and", "are", "you", "your", "that", "with", "from",
                    "just", "like", "will", "wont", "won't", "over", "into", "this",
                }
            ]
            if len(nouns) >= 3:
                image_hook = " ".join(nouns[:4])
                if not image_hook.endswith("?"):
                    image_hook = f"{image_hook}?"

    image_hook = _billboard_words(image_hook, 7)
    image_headline = _billboard_words(image_headline, 8)
    return image_hook, image_headline


_ON_IMAGE_TEXT_PATTERNS = [
    # Quoted burn-in instructions the model often invents / contradicts.
    re.compile(
        r"""(?ix)
        (?:
            (?:large\s+)?(?:3-second\s+)?(?:billboard\s+)?hook(?:\s+text)?(?:\s+\([^)]*\))?
            |(?:short\s+)?(?:punch\s+)?headline(?:\s+text)?(?:\s+\([^)]*\))?
            |(?:bold\s+)?(?:on[- ]image\s+)?(?:hook|headline|message)(?:\s+text)?
            |burn\s+on[- ]image\s+text
            |cta\s+button(?:\s+text)?
            |text\s+overlay
            |upper\s+third
            |lower\s+third
        )
        [^\"\n]{0,80}
        [\"“][^\"”]{1,160}[\"”]
        \.?
        """,
    ),
    re.compile(
        r"""(?ix)
        (?:must\s+read\s+exactly|must\s+appear|must\s+say|reading)\s*:\s*
        [\"“][^\"”]{1,160}[\"”]
        \.?
        """,
    ),
]


# Sanitise Runway prompts: remove content that triggers policy violations.
# Particularly: children in distress, vulnerable subjects in medical settings.
_CHILD_DISTRESS_TERMS = re.compile(
    r"(?i)\b(?:anxious|scared|terrified|frightened|fear(?:ful)?|distressed|"
    r"crying|tearful|grimacing|grimace|wince|wincing|panicked|panic|dread(?:ful)?|"
    r"apprehensive|mouth\s+(?:wide\s+)?open(?!\s+smile)|"
    r"crying|whimpering|trembling|clenching)\b"
)
_CHILD_SUBJECT_TERMS = re.compile(
    r"(?i)\b(?:child(?:ren)?|kid(?:s)?|toddler|boy|girl|young\s+(?:patient|person)|"
    r"minor|youth|juvenile|little\s+one|pre-?teen|elementary(?:-age)?)\b"
)


def _sanitize_runway_prompt(prompt: str) -> str:
    """
    Replace content-policy-triggering language before sending to Runway.
    Particularly:
    - Children in distress/fear → replace with calm/happy equivalents.
    - Medical procedures shown on subjects → soften to 'consultation' context.
    """
    text = prompt or ""
    sentences = re.split(r"(?<=[.!?])\s+", text)
    cleaned_parts = []
    for sent in sentences:
        has_child = bool(_CHILD_SUBJECT_TERMS.search(sent))
        if has_child and _CHILD_DISTRESS_TERMS.search(sent):
            # Replace distress terms with calm/positive equivalents
            sent = _CHILD_DISTRESS_TERMS.sub("calm", sent)
            # Replace "mouth open" patterns specifically
            sent = re.sub(
                r"(?i)mouth\s+(?:wide\s+)?open",
                "relaxed open smile",
                sent,
            )
        cleaned_parts.append(sent)
    return " ".join(cleaned_parts)


# Sentinel so re-runs of enforce_on_image_copy_in_prompt are idempotent.
_ANCHOR_SENTINEL = "TEXT-ANCHOR:"


def enforce_on_image_copy_in_prompt(
    prompt: str,
    *,
    image_hook: str,
    image_headline: str,
    cta: str = "",
    full_hook: str = "",
    full_headline: str = "",
) -> str:
    """
    Pin EXACT on-image text so image models don't invent alternate slogans.

    Double-enforcement:
    - Prepend TEXT-ANCHOR before the visual description (model reads rules first).
    - Append the same rules after the description (end-of-prompt weight).
    Both blocks quote IDENTICAL strings — no contradictory instructions.
    Also sanitises child-distress language that triggers Runway content policy.
    """
    cleaned = _sanitize_runway_prompt((prompt or "").strip())

    # Strip any prior TEXT-ANCHOR injection (makes this call idempotent).
    # Sentinel may now appear anywhere in the string (not just the start).
    if _ANCHOR_SENTINEL in cleaned:
        cleaned = cleaned[: cleaned.find(_ANCHOR_SENTINEL)].strip()

    # Strip known conflicting quoted burn-in instructions already in the prompt.
    for pat in _ON_IMAGE_TEXT_PATTERNS:
        cleaned = pat.sub(" ", cleaned)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    # Strip accidental full post copy pasted into the prompt.
    for long_line in (full_hook, full_headline):
        line = (long_line or "").strip()
        if len(line) >= 24 and line.lower() in cleaned.lower():
            cleaned = re.sub(re.escape(line), "", cleaned, flags=re.IGNORECASE)
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    hook = (image_hook or "").strip()
    headline = (image_headline or "").strip()
    button = (cta or "").strip()
    if not hook and not headline:
        return cleaned

    # Build concise quoted copy list.
    parts: list[str] = [f'"{hook}"']
    if headline:
        parts.append(f'"{headline}"')
    if button:
        parts.append(f'"{button}"')
    copy_list = " / ".join(parts)

    # CTA pill button visual instruction.
    cta_desc = (
        f' lower-third pill-shaped button, solid brand-colour background, "{button}" in white bold text.'
        if button else ""
    )

    # TEXT-ANCHOR sentinel stays so idempotency check works on re-runs,
    # but the visual scene now comes FIRST so the model builds the scene before
    # processing text overlay rules — better scene fidelity with fewer artefacts.
    text_rules = (
        f" {_ANCHOR_SENTINEL} TEXT on this image ONLY: upper-third {parts[0]}"
        + (f", centre {parts[1]}" if len(parts) > 1 else "")
        + (cta_desc if button else "")
        + " No other text, slogans, signs, or labels anywhere."
        + f" ON-IMAGE COPY (final authority): render EXACTLY — {copy_list}."
        + (" CTA must look like a pill button with background colour, not plain text." if button else "")
        + " Discard any other marketing words."
    )

    # Structure: [visual scene FIRST] → [text rules LAST]
    return _clamp_prompt(f"{cleaned.rstrip()}{text_rules}")




@dataclass
class IcpImageVariantPlan:
    use_cases: list[str]
    hook: str
    message: str
    cta: str
    offer: str
    prompt: str
    reasoning: str
    ad_angle: str = ""
    image_hook: str = ""
    image_headline: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "use_cases": self.use_cases,
            "hook": self.hook,
            "message": self.message,
            "image_hook": self.image_hook,
            "image_headline": self.image_headline,
            "cta": self.cta,
            "offer": self.offer,
            "prompt": self.prompt,
            "reasoning": self.reasoning,
            "ad_angle": self.ad_angle,
        }


def _parse_json_object(raw: str) -> dict[str, Any] | None:
    """Parse a JSON object from LLM output, tolerating fences and trailing prose."""
    text = (raw or "").strip()
    if not text:
        return None
    # Strip markdown fences if present.
    text = re.sub(r"```(?:json)?", "", text).strip().strip("`").strip()
    candidates = [text]
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        candidates.append(text[start : end + 1])
    # Prefer the first balanced `{...}` block when the model appends explanation prose.
    if start >= 0:
        depth = 0
        in_str = False
        esc = False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == '"':
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidates.append(text[start : i + 1])
                    break
    seen: set[str] = set()
    for candidate in candidates:
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            data = json.loads(candidate)
            if isinstance(data, dict):
                return data
        except (json.JSONDecodeError, TypeError, ValueError):
            continue
    return None


def _clamp_prompt(prompt: str, max_len: int = 4000) -> str:
    prompt = (prompt or "").strip()
    if len(prompt) > max_len:
        return prompt[: max_len - 1] + "…"
    return prompt


def _valid_use_cases(ids: list[Any]) -> list[str]:
    return [uc for uc in (ids or []) if isinstance(uc, str) and uc in _USE_CASE_DESCRIPTIONS] or list(
        _SELECTOR_FALLBACK_USE_CASES
    )


def _derive_industry_bucket(*, campaign_name: str, industry: str, icp_text: str = "") -> str:
    """Map brand industry + campaign + ICP to a scene pool key."""
    ind = (industry or "").lower().strip()

    # Agency / digital marketing brand → visuals about ads, leads, targeting (the service sold).
    if ind in _AGENCY_BRAND_INDUSTRIES or "digital_marketing" in ind:
        return "digital_marketing"

    # Product / client brands: infer vertical from campaign + ICP text.
    haystack = f"{campaign_name} {icp_text}".lower()
    scores: dict[str, int] = {k: 0 for k in _INDUSTRY_SCENE_POOLS if k != "digital_marketing"}
    for bucket, keywords in _INDUSTRY_KEYWORDS.items():
        if bucket == "digital_marketing":
            continue
        for kw in keywords:
            if kw in haystack:
                scores[bucket] = scores.get(bucket, 0) + 1

    # Campaign explicitly about ads/traffic for any brand
    dm_score = sum(1 for kw in _INDUSTRY_KEYWORDS["digital_marketing"] if kw in haystack)
    if dm_score >= 2:
        return "digital_marketing"

    best = max(scores, key=lambda k: scores[k])
    if scores[best] > 0:
        return best

    if "retail" in ind or ind == "dtc":
        return "ecommerce" if "dtc" in ind else "retail"
    if "local" in ind or "construction" in ind:
        return "trade"
    if "saas" in ind:
        return "pro_services"
    return "general"


def _pick_scene_mandates(
    *,
    count: int,
    campaign_name: str,
    industry: str,
    icp_text: str = "",
    avoid_snippets: list[str] | None = None,
    hook_frameworks: list[str] | None = None,
) -> list[str]:
    """Pick distinct scene mandates; prefer industry pool, light backfill for variety."""
    frameworks = [f.lower().strip() for f in (hook_frameworks or []) if f]
    if "pattern_interrupt" in frameworks:
        pool = list(_PATTERN_INTERRUPT_SCENES) + list(
            _INDUSTRY_SCENE_POOLS.get("digital_marketing", _INDUSTRY_SCENE_POOLS["general"])
        )
        random.shuffle(pool)
        chosen: list[str] = []
        avoid = " ".join((avoid_snippets or [])).lower()
        for scene in pool:
            if len(chosen) >= count:
                break
            if scene.lower()[:48] in avoid or scene in chosen:
                continue
            chosen.append(f"PATTERN INTERRUPT: {scene}")
        while len(chosen) < count:
            extra = random.choice(_PATTERN_INTERRUPT_SCENES)
            chosen.append(f"PATTERN INTERRUPT: {extra} (distinct angle from prior)")
        return chosen[:count]

    bucket = _derive_industry_bucket(
        campaign_name=campaign_name,
        industry=industry,
        icp_text=icp_text,
    )
    primary = list(_INDUSTRY_SCENE_POOLS.get(bucket, _INDUSTRY_SCENE_POOLS["general"]))
    if bucket == "digital_marketing":
        secondary = list(_INDUSTRY_SCENE_POOLS["general"])
    else:
        secondary = [
            s
            for b, scenes in _INDUSTRY_SCENE_POOLS.items()
            if b not in (bucket, "digital_marketing")
            for s in scenes
        ]
    pool = primary + secondary
    random.shuffle(pool)

    avoid = " ".join((avoid_snippets or [])).lower()
    chosen: list[str] = []
    for scene in pool:
        if len(chosen) >= count:
            break
        scene_key = scene.lower()[:48]
        if scene_key in avoid:
            continue
        if scene in chosen:
            continue
        chosen.append(scene)

    while len(chosen) < count:
        extra = random.choice(_INDUSTRY_SCENE_POOLS.get(bucket, _INDUSTRY_SCENE_POOLS["general"]))
        if extra not in chosen:
            chosen.append(extra)
        else:
            chosen.append(
                f"Variant {len(chosen) + 1}: documentary AU commercial scene — "
                f"{extra} (distinct angle and props from prior variants)"
            )
    return chosen[:count]


async def build_icp_from_campaign(
    *,
    campaign_name: str,
    brand_name: str = "",
    industry: str = "",
    niche: str = "",
    objective_id: str = "",
) -> str:
    """Build ICP from industry + niche + objective + brand (end-customer focused)."""
    industry_label = (industry or "").strip() or campaign_name
    niche_label = (niche or "").strip()
    objective_label = (objective_id or "conversions").strip()

    if not settings.OPENROUTER_API_KEY:
        buyer_focus = (
            "Australian home buyer / refinancer comparing brokers"
            if "mortgage" in industry_label.lower() or "broker" in industry_label.lower()
            else f"Australian buyer evaluating {industry_label}"
        )
        return (
            f'AVATAR NAME: Target Buyer — "The Ready-to-Act Prospect"\n'
            f"IDENTITY: {buyer_focus}. Brand: {brand_name or 'local business'}. "
            f"Industry: {industry_label}. Niche: {niche_label or 'general'}.\n"
            f"CURRENT REALITY: Comparing options and looking for proof before committing "
            f"(objective: {objective_label}).\n"
            f"CORE PAIN: Uncertainty, wasted time, and fear of choosing the wrong path.\n"
            f"DESIRED OUTCOME: A clear, trustworthy next step that matches the brand offer.\n"
            f'KEY OBJECTION: "I\'ve seen this before — show me it works for people like me."\n'
            f"BUYING TRIGGER: Cost of delay becomes obvious.\n"
            f'LANGUAGE THEY USE: "Is this worth it?" | "Show me proof" | "How fast can we start?"'
        )

    user_content = "\n".join([
        f"INDUSTRY (what the brand is): {industry_label}",
        f"NICHE (campaign specialty): {niche_label or 'Not specified'}",
        f"OBJECTIVE (what the ad must drive): {objective_label}",
        f"CAMPAIGN LABEL: {campaign_name}",
        f"BRAND: {brand_name or 'Not specified'}",
        "",
        "Remember: ICP = person who sees the ad and takes the objective action "
        "(usually the brand's end customer). Do not invent B2B-to-peers copy unless niche clearly says so.",
        "",
        "INDUSTRY REFERENCE ARCHETYPES (use when industry/niche maps to one):",
        _INDUSTRY_REFERENCE_ICPS,
    ])

    try:
        client = _get_openrouter_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": _ICP_FROM_CAMPAIGN_SYSTEM},
                {"role": "user", "content": user_content},
            ],
            max_tokens=900,
        )
        icp_text = (response.choices[0].message.content or "").strip()
        if len(icp_text) < 100:
            raise ValueError("ICP response too short")
        return icp_text
    except Exception:
        logger.exception("ICP-from-campaign failed — using fallback")
        return (
            f'AVATAR NAME: Buyer — "The Motivated Customer"\n'
            f"IDENTITY: Australian buyer for {industry_label}"
            f"{f' / {niche_label}' if niche_label else ''}. Brand: {brand_name}.\n"
            f"CURRENT REALITY: Actively comparing options (objective: {objective_label}).\n"
            f"CORE PAIN: Time and money wasted on solutions that underdeliver.\n"
            f"DESIRED OUTCOME: Fast, trustworthy results.\n"
            f'KEY OBJECTION: "Not sure this is the right fit."\n'
            f"BUYING TRIGGER: Cost of inaction becomes obvious.\n"
            f'LANGUAGE THEY USE: "Show me proof" | "How long does it take?"'
        )


def _fallback_cta_options(*, industry: str, cta_hint: str) -> list[str]:
    """Distinct action CTAs for fallback plans — avoid Learn More by default."""
    from app.services.cta_defaults import suggested_cta_for_industry

    hint = (cta_hint or "").strip()
    primary = hint if hint and hint.lower() not in {"learn more", "learnmore"} else suggested_cta_for_industry(
        industry or "general"
    )
    if primary.lower() in {"learn more", "learnmore"}:
        primary = "Get Free Quote"
    pool = [
        primary,
        "Book Consultation",
        "Get Free Audit",
        "Claim Free Review",
        "Start Free Pilot",
        "Book Free Quote",
        "Request Strategy Call",
        "Get Partner-Ready Plan",
    ]
    # Preserve order, drop duplicates (case-insensitive).
    seen: set[str] = set()
    out: list[str] = []
    for item in pool:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out


def _fallback_variants(
    *,
    campaign_name: str,
    brand_name: str,
    industry: str,
    cta: str,
    offer_hint: str,
    image_aspect_ratio: str,
    variant_count: int,
    existing_hooks: list[str],
    scene_mandates: list[str] | None = None,
    angle_assignments: list[str] | None = None,
    reason: str = "template fallback",
) -> list[IcpImageVariantPlan]:
    """Template variants when the LLM path is unavailable or returns unusable output."""
    brand = brand_name or "your brand"
    cta_options = _fallback_cta_options(industry=industry, cta_hint=cta)
    offer_base = offer_hint.strip() or f"{brand} — free review this week"
    variants: list[IcpImageVariantPlan] = []
    mandates = scene_mandates or _pick_scene_mandates(
        count=variant_count,
        campaign_name=campaign_name,
        industry=industry,
    )

    for i in range(variant_count):
        scene = mandates[i % len(mandates)]
        niche_word = (industry or campaign_name or "leads").split()[0][:18]
        hook = f"Your best {niche_word} results are slipping away to competitors who package the whole offer"
        if hook in existing_hooks:
            hook = f"Still chasing cold {niche_word} while bigger players win the relationship?"
        message = f"{brand} helps you keep clients with a clearer, integrated next step this week"
        image_hook, image_headline = _related_image_lines(hook, message)
        cta_text = cta_options[i % len(cta_options)]
        offer = (
            f"{offer_base}. "
            f"You get clarity without the guesswork, so you can act with confidence — claim the next step now."
        )
        prompt = enforce_on_image_copy_in_prompt(
            _clamp_prompt(
                f"Photoreal Australian commercial ad, {image_aspect_ratio}. "
                f"SCENE MANDATE: {scene}. Subject matches buyer for campaign '{campaign_name}'. "
                f"Documentary commercial lighting, authentic non-stock feel, sharp visible faces."
            ),
            image_hook=image_hook,
            image_headline=image_headline,
            cta=cta_text,
            full_hook=hook,
            full_headline=message,
        )
        variants.append(
            IcpImageVariantPlan(
                use_cases=["bs_real_life", "bs_emotional_appeal"][: 1 + (i % 2)],
                hook=hook,
                message=message,
                cta=cta_text,
                offer=offer,
                prompt=prompt,
                reasoning=f"Fallback variant {i + 1}: {reason}.",
                ad_angle=(angle_assignments[i] if angle_assignments and i < len(angle_assignments) else ""),
                image_hook=image_hook,
                image_headline=image_headline,
            )
        )
    return variants


_PATTERN_INTERRUPT_SCENES = [
    "Extreme close-up of a broker's phone exploding with competitor lead notifications — startled reaction, harsh phone glow",
    "Empty client chair in a mortgage office with a 'LOST LEAD' sticky note — cold daylight, unsettling quiet",
    "Over-shoulder shot of Facebook/Google ads for rival brokers filling the screen while subject looks defeated",
    "Dutch-tilt (tilted camera) of a broker mid-scroll, frozen by a shocking ad claim — high contrast, urgent mood",
    "Metaphor visual: leaking pipeline / funnel of leads spilling onto the floor of a modern AU office",
    "Subject staring straight into camera with a bold confronting expression — almost uncomfortable intimacy, scroll-stop",
]


def _style_enforcement_block(frameworks: list[str]) -> str:
    if not frameworks:
        return ""
    lines = [
        "STYLE ENFORCEMENT (mandatory — selected frameworks override generic stock scenes):",
    ]
    for fid in frameworks:
        tip = ANGLE_GUIDANCE.get(fid)
        if tip:
            lines.append(f"- {fid.upper().replace('_', ' ')}: {tip}")
    if "pattern_interrupt" in frameworks:
        lines.extend(
            [
                "- BAN for pattern_interrupt: 'professional stock photography', smiling team huddle, "
                "generic glass meeting room with polite laptop review, soft corporate brochure lighting.",
                "- REQUIRE for pattern_interrupt: unusual angle OR unexpected prop/metaphor OR confrontational "
                "viewer stare OR competitive threat visible in-frame; hook must feel like a scroll-stop.",
                "- In each prompt, explicitly say the creative approach is pattern interrupt / stop-the-scroll "
                "(not stock photography).",
            ]
        )
    return "\n".join(lines)


async def generate_icp_image_plan(
    *,
    campaign_name: str,
    brand_name: str = "",
    industry: str = "",
    niche: str = "",
    objective_id: str = "",
    cta: str = "",
    offer: str = "",
    image_aspect_ratio: str = "1:1",
    hook_frameworks: list[str] | None = None,
    variant_count: int = 1,
    existing_hooks: list[str] | None = None,
    existing_prompts: list[str] | None = None,
    creative_format: str = "static",
) -> dict[str, Any]:
    """
    Build ICP from industry + niche + objective, then produce N distinct image variant plans.
    Returns { icp_text, variants: [{ use_cases, hook, message, image_hook, image_headline, ... }] }.
    """
    count = max(1, min(20, int(variant_count or 1)))
    hooks_avoid = [h.strip() for h in (existing_hooks or []) if h and h.strip()]
    prompts_avoid = [p.strip() for p in (existing_prompts or []) if p and p.strip()]
    frameworks = [f.strip() for f in (hook_frameworks or []) if f and str(f).strip()]
    angle_assignments = assign_angles_to_variants(frameworks, count, objective_id)
    industry_label = (industry or "").strip() or campaign_name
    niche_label = (niche or "").strip()
    is_carousel = (creative_format or "").strip().lower() == "carousel"
    framework_lines = []
    for fid in frameworks:
        tip = ANGLE_GUIDANCE.get(fid, "Apply this marketing angle clearly in hook + scene.")
        framework_lines.append(f"- {fid}: {tip}")
    framework_block = (
        "\n".join(framework_lines)
        if framework_lines
        else "- (none selected) — AI will pick angles from campaign objective and ICP."
    )
    angle_block = per_variant_angle_instructions(angle_assignments)
    carousel_block = (
        _carousel_story_roles(count, angle_assignments) if is_carousel and count >= 1 else ""
    )

    icp_text = await build_icp_from_campaign(
        campaign_name=campaign_name,
        brand_name=brand_name,
        industry=industry_label,
        niche=niche_label,
        objective_id=objective_id,
    )

    scene_mandates = _pick_scene_mandates(
        count=count,
        campaign_name=campaign_name,
        industry=industry_label,
        icp_text=icp_text,
        avoid_snippets=prompts_avoid,
        hook_frameworks=frameworks,
    )

    if not settings.OPENROUTER_API_KEY:
        variants = _fallback_variants(
            campaign_name=campaign_name,
            brand_name=brand_name,
            industry=industry_label,
            cta=cta,
            offer_hint=offer,
            image_aspect_ratio=image_aspect_ratio,
            variant_count=count,
            existing_hooks=hooks_avoid,
            scene_mandates=scene_mandates,
            angle_assignments=angle_assignments,
            reason="OPENROUTER_API_KEY is missing",
        )
        return {"icp_text": icp_text, "variants": [v.to_dict() for v in variants]}

    style_block = _style_enforcement_block(list(dict.fromkeys(angle_assignments)))
    user_msg = "\n".join([
        _USE_CASE_CATALOGUE,
        "",
        "---",
        "MARKETING INPUTS (this order defines campaign intent — process 1→5 before writing):",
        f"1. INDUSTRY (brand category): {industry_label}",
        f"2. NICHE (campaign specialty): {niche_label or 'Not specified'}",
        f"3. BRAND: {brand_name or 'Unknown'}",
        f"4. CAMPAIGN OBJECTIVE (must drive this action): {objective_id or 'conversions'}",
        "5. AD ANGLE / HOOK FRAMEWORK: see SELECTED AD ANGLES below",
        "",
        f"CREATIVE FORMAT: {'carousel (swipe story)' if is_carousel else 'static (standalone ads)'}",
        f"CAMPAIGN LABEL: {campaign_name}",
        f"SCENE POOL: {_derive_industry_bucket(campaign_name=campaign_name, industry=industry_label, icp_text=icp_text)}",
        f"CTA HINT (optional shared guidance — still invent a distinct CTA per variant): {cta or 'none — invent action CTAs from campaign + ICP'}",
        f"OFFER HINT (caption only — do NOT put in image): {offer or 'infer from ICP and campaign'}",
        f"ASPECT RATIO: {image_aspect_ratio}",
        f"VARIANT / CARD COUNT: {count}",
        "",
        "STEP 1 — for each variant, first derive the campaign intent (audience, problem, action, emotion, single_message) from the inputs above and the ICP.",
        "STEP 2 — design the visual and the copy TOGETHER so the image alone communicates 70-80% of the single_message and the on-image text reinforces the rest.",
        "STEP 3 — run the STRANGER TEST on every scene: with all text removed, a stranger must answer BOTH 'what is this ad about?' (a clear category cue from the industry/niche must be visible in the frame — e.g. a house for home loans) AND 'what is being promised?' (the benefit must be provable on camera). Never drop the category object from the scene, and never show ONLY the category without the promise.",
        f"STEP 3b — MANDATORY on EVERY variant, no exceptions: ground the setting in the {industry_label or 'this'} industry's own world (its typical location, tools, or objects) so a viewer instantly recognises the industry from the background alone, even before reading the on-image text. A plain office desk / blank laptop / neutral room with zero industry cues is a FAILED variant — fix it by adding a real object or location from this industry into the frame.",
        "",
        "CONTEXT RULES:",
        "- Write for the ICP (end customer who takes the objective action).",
        "- If brand is a mortgage/finance broker and objective is conversions/purchase: speak to home buyers / refinancers — NOT other brokers.",
        "- Niche informs the offer angle; do not invent a different business model.",
        "",
        *( [carousel_block, ""] if carousel_block else [] ),
        "SELECTED AD ANGLES (user picked — rotate across batch):",
        framework_block,
        "",
        angle_block,
        "",
        *( [style_block, ""] if style_block else [] ),
        "VARIETY GUIDANCE:",
        _VARIETY_GUIDANCE,
        "",
        "ICP PROFILE:",
        icp_text,
        "",
        "SCENE STARTING POINT (one per variant — adapt to ICP; vary props and setting across variants):",
        *[f"  Variant {i + 1}: {scene_mandates[i]}" for i in range(count)],
        "",
        *(f"AVOID THESE HOOKS (already used): {h}" for h in hooks_avoid),
        *(f"AVOID REPEATING SCENES SIMILAR TO: {p[:120]}…" for p in prompts_avoid[:5]),
        "",
        f"Produce exactly {count} variant(s). Each must use HALO aligned to the ICP.",
        (
            "CAROUSEL MODE: every hook/message/prompt must advance the SAME swipe story "
            "(problem → agitate/proof → solution). Angles colour the beat; they must not break the story."
            if is_carousel
            else "STATIC MODE: variants can be alternate standalone creatives."
        ),
        "Keep FULL hook + message strong and complete for the post.",
        "Also invent RELATED image_hook (max 6 words) + image_headline (max 8 words) — catchy twins for the photo only.",
        "Both image_hook and image_headline are REQUIRED on every variant — never leave them blank.",
        "Burn ONLY image_hook + image_headline + CTA into the prompt — never the full hook/message/offer.",
        "Each variant needs its own action CTA on the image button — do not default every variant to Learn More.",
        "If pattern_interrupt is selected, every prompt must feel like a stop-the-scroll Pattern Interrupt — not stock photography.",
        "The prompt must describe a scene that SHOWS the single_message (problem, transformation, or outcome) — never a pretty background for text. No generic stock-photo scenes (smiling person at laptop, handshake, team huddle) unless they carry real story props.",
        "EXPRESSIONS: direct every face like a film director — spell out the exact expression per person matched to their story role (worried/embarrassed for the problem state, confident/relieved for the outcome). In before/after frames the two expressions must be opposites; explicitly state the 'before' person is NOT smiling.",
        f"INDUSTRY SETTING CHECK (apply to EVERY variant, not just some): before finalising each prompt, confirm the background/location/props visibly belong to the {industry_label or 'campaign'} industry. If a variant's setting could belong to ANY industry (plain desk, blank laptop, neutral room), add a real object or location from this industry's world before writing the final prompt.",
        "Return ONLY the JSON object. Do not add markdown commentary, headings, or explanation after the closing brace.",
    ])

    fallback_reason = "template fallback"
    try:
        client = _get_openrouter_client()
        model = settings.OPENROUTER_MODEL_CLAUDE or settings.OPENROUTER_MODEL_CLAUDE_SCRIPT
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _VARIANTS_SYSTEM},
                {"role": "user", "content": user_msg},
            ],
            max_tokens=3600,
            temperature=0.85,
        )
        raw = (response.choices[0].message.content or "").strip()
        data = _parse_json_object(raw)
        raw_variants = (data or {}).get("variants") if data else None

        if isinstance(raw_variants, list) and raw_variants:
            variants: list[IcpImageVariantPlan] = []
            cta_fallbacks = _fallback_cta_options(industry=industry_label, cta_hint=cta)
            used_ctas: set[str] = set()
            for i, item in enumerate(raw_variants[:count]):
                if not isinstance(item, dict):
                    continue
                hook = str(item.get("hook") or "").strip()
                message = str(item.get("message") or "").strip()
                image_hook = _billboard_words(str(item.get("image_hook") or ""), 6)
                image_headline = _billboard_words(str(item.get("image_headline") or ""), 8)
                if not image_hook or not image_headline:
                    derived_h, derived_m = _related_image_lines(hook, message)
                    image_hook = image_hook or derived_h
                    image_headline = image_headline or derived_m
                cta_line = str(item.get("cta") or "").strip()
                if not cta_line or cta_line.lower() in used_ctas:
                    for candidate in cta_fallbacks:
                        if candidate.lower() not in used_ctas:
                            cta_line = candidate
                            break
                    if not cta_line:
                        cta_line = cta_fallbacks[i % len(cta_fallbacks)]
                used_ctas.add(cta_line.lower())
                offer_line = str(item.get("offer") or offer or cta or "").strip()
                prompt = _clamp_prompt(str(item.get("prompt") or ""))
                if not hook or not message or not prompt:
                    continue
                # Pin EXACT on-image lines into the prompt (strip any inventted slogans).
                prompt = enforce_on_image_copy_in_prompt(
                    prompt,
                    image_hook=image_hook,
                    image_headline=image_headline,
                    cta=cta_line,
                    full_hook=hook,
                    full_headline=message,
                )
                intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
                single_message = str((intent or {}).get("single_message") or "").strip()
                if single_message:
                    # Make the visual story authoritative for the image model too.
                    prompt = (
                        f"{prompt} VISUAL STORY (non-negotiable): before any text is read, "
                        f"the scene itself must communicate — {single_message}"
                    )
                reasoning_line = str(item.get("reasoning") or "").strip()
                if single_message and single_message.lower() not in reasoning_line.lower():
                    reasoning_line = (
                        f"Single message: {single_message}" + (f" — {reasoning_line}" if reasoning_line else "")
                    )
                variants.append(
                    IcpImageVariantPlan(
                        use_cases=_valid_use_cases(item.get("use_cases")),
                        hook=hook,
                        message=message,
                        cta=cta_line,
                        offer=offer_line,
                        prompt=prompt,
                        reasoning=reasoning_line,
                        ad_angle=(
                            angle_assignments[i]
                            if angle_assignments and i < len(angle_assignments)
                            else str(item.get("ad_angle") or "").strip()
                        ),
                        image_hook=image_hook,
                        image_headline=image_headline,
                    )
                )
            if variants:
                while len(variants) < count:
                    fb = _fallback_variants(
                        campaign_name=campaign_name,
                        brand_name=brand_name,
                        industry=industry_label,
                        cta=cta,
                        offer_hint=offer,
                        image_aspect_ratio=image_aspect_ratio,
                        variant_count=1,
                        existing_hooks=hooks_avoid + [v.hook for v in variants],
                        scene_mandates=[scene_mandates[len(variants) % len(scene_mandates)]],
                        reason="LLM returned fewer variants than requested",
                    )
                    variants.append(fb[0])
                return {
                    "icp_text": icp_text,
                    "variants": [v.to_dict() for v in variants[:count]],
                }

        logger.warning("ICP image plan LLM returned invalid JSON; using fallback variants")
        fallback_reason = "LLM returned unusable JSON"
    except Exception:
        logger.exception("generate_icp_image_plan LLM failed")
        fallback_reason = "LLM request failed"

    variants = _fallback_variants(
        campaign_name=campaign_name,
        brand_name=brand_name,
        industry=industry_label,
        cta=cta,
        offer_hint=offer,
        image_aspect_ratio=image_aspect_ratio,
        variant_count=count,
        existing_hooks=hooks_avoid,
        scene_mandates=scene_mandates,
        angle_assignments=angle_assignments,
        reason=fallback_reason,
    )
    return {"icp_text": icp_text, "variants": [v.to_dict() for v in variants]}
