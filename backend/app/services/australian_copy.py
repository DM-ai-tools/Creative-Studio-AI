"""Australian English voice, spelling, and accent rules for spoken ad scripts."""

from __future__ import annotations

import re

AUSTRALIAN_ENGLISH_SCRIPT_RULES = """
AUSTRALIAN ENGLISH (mandatory for every spoken line):
- Write for a warm, natural AUSTRALIAN accent — not American, not British RP
- Use Australian English spelling: organise, realise, colour, centre, licence (noun), programme (TV)
- Sound like a confident Aussie talking to another Aussie business owner — relaxed, direct, fair dinkum
- Use Australian vocabulary and phrasing naturally: reckon, keen, heaps, arvo, tradie, no dramas, no worries, good on ya, ripper, crook (when unwell), whinge, smoko, footy, servo, mob (group), buckley's (none), flat out, chockers
- Contractions and rhythm: you're, we've, that's, won't, can't — conversational Aussie cadence
- Reference Australian context when it fits: states, suburbs, local business culture, AEST hours
- FORBIDDEN Americanisms: gotten, awesome (overused), sidewalk, vacation, candy, gas (use petrol), bucks, reach out, touch base, super excited, y'all, guys (prefer "team" or "you lot"), optimize, center, color
- Numbers, money & stats: write every figure as NUMERALS so it reads clearly in on-screen captions — e.g. "488% ROAS", "$18.9 million in spend", "$105 million", "over 1.2 million leads". Keep the magnitude word (million / thousand / per cent) after the digits so it is still spoken naturally. Do NOT spell figures out as words (never "one hundred and five million", "eighteen point nine million", "four hundred and eighty-eight per cent")
- CTA examples that sound Aussie: "Book a free audit", "Jump on it today", "Give us a bell", "Lock it in"
""".strip()

AUSTRALIAN_ENGLISH_BRIEF_RULES = """
- Notes and talking points must use Australian English spelling and phrasing
- Suggest Aussie-flavoured hook angles (direct, understated confidence — not US hype)
""".strip()

# Injected into image-variant planning (hooks, on-image lines, CTAs, offers) — ALL industries.
AUSTRALIAN_ENGLISH_ON_IMAGE_RULES = """
AUSTRALIAN ENGLISH — EVERY INDUSTRY (mandatory for hook, message, image_hook, image_headline, cta, offer):
Applies to wholesale, retail, ecommerce, trade, HVAC, dental, landscaping, professional services,
finance, healthcare, beauty, automotive, digital marketing — and any other niche. No exceptions.

VOICE
- Write like an Aussie talking to an Aussie buyer — direct, dry-confident, scroll-stopping.
- NOT bland US corporate brochure speak. NOT American ad voice.
- Australian spelling always: organise, realise, colour, centre, licence, metre, favour, optimise.

CATCHY ON-IMAGE (3-second billboard)
- image_hook + image_headline must stop the scroll — punchy, specific, niche words — not flat labels.
- Prefer natural Aussie beats when they fit: sorted, flat out, no dramas, keen, reckon, heaps,
  tradie, arvo, ring us, give us a bell, lock it in, get it sorted, gutting your margins.
- One natural Aussie beat per creative is enough — never cringe, never force slang into every line.

FLAT / US → FAIL (rewrite for ANY industry)
  BAD: "Customer waiting. Parts needed now." / "Same-day delivery available" / "Call Now"
  GOOD: "Job stuck waiting on parts?" / "Same-day dispatch, sorted" / "Ring us now"
  BAD: "Parts delays killing profits?" / "One reliable wholesale partner"
  GOOD: "Parts delays gutting your margins?" / "One wholesaler you can bank on"
  BAD: "Tired of your AC?" / "Book a consultation today" (generic US)
  GOOD: "AC packing it in this heat?" / "Book a free quote"
  BAD: "Transform your smile" / "Learn More"
  GOOD: "Still hiding that gap?" / "Book a consult"
  BAD: "Reliable service you can trust" (empty brochure)
  GOOD: niche-specific pain or outcome in Aussie plain English

FORBIDDEN Americanisms: gotten, sidewalk, vacation, candy, gas (use petrol), optimize, center, color,
reach out, touch base, y'all, "Call Now" as default when "Ring us" / "Give us a bell" / "Book free quote" fits.

Niche vocabulary first — then Aussie voice. Speak to THIS industry's buyer, not a generic "customer".
""".strip()


_US_SPELLING_PAIRS: list[tuple[str, str]] = [
    (r"\borganize\b", "organise"),
    (r"\borganized\b", "organised"),
    (r"\borganizing\b", "organising"),
    (r"\brealize\b", "realise"),
    (r"\brealized\b", "realised"),
    (r"\brealizing\b", "realising"),
    (r"\bcolor\b", "colour"),
    (r"\bcolors\b", "colours"),
    (r"\bcolored\b", "coloured"),
    (r"\bcenter\b", "centre"),
    (r"\bcenters\b", "centres"),
    (r"\bfavor\b", "favour"),
    (r"\bfavors\b", "favours"),
    (r"\bfavorite\b", "favourite"),
    (r"\boptimize\b", "optimise"),
    (r"\boptimized\b", "optimised"),
    (r"\boptimization\b", "optimisation"),
    (r"\bbehavior\b", "behaviour"),
    (r"\bbehaviors\b", "behaviours"),
    (r"\blicense\b", "licence"),
    (r"\bdefense\b", "defence"),
    (r"\boffense\b", "offence"),
    (r"\bgotten\b", "got"),
    (r"\bvacation\b", "holiday"),
    (r"\bsidewalk\b", "footpath"),
]

_US_SPELLING_COMPILED: list[tuple[re.Pattern[str], str]] | None = None


def _us_spelling_patterns() -> list[tuple[re.Pattern[str], str]]:
    global _US_SPELLING_COMPILED
    if _US_SPELLING_COMPILED is None:
        _US_SPELLING_COMPILED = [(re.compile(p, re.I), repl) for p, repl in _US_SPELLING_PAIRS]
    return _US_SPELLING_COMPILED


def _match_case(src: str, repl: str) -> str:
    if not src:
        return repl
    if src.isupper():
        return repl.upper()
    if src[0].isupper():
        return repl[:1].upper() + repl[1:]
    return repl


def enforce_australian_english_copy(text: str) -> str:
    """
    Soft post-process: AU spelling + a few flat US CTA swaps.
    Does not invent slang — keeps meaning, fixes Americanisms.
    """
    out = (text or "").strip()
    if not out:
        return out
    for pat, repl in _us_spelling_patterns():
        out = pat.sub(lambda m, r=repl: _match_case(m.group(0), r), out)
    cta_map = {
        "call now": "Ring us now",
        "call us": "Give us a bell",
        "learn more": "Find out more",
        "contact us": "Get in touch",
    }
    key = out.lower().strip()
    if key in cta_map:
        return cta_map[key]
    return out


# Injected into every variant-generation system prompt.
ACCC_COMPLIANCE_RULES = """
AUSTRALIAN CONSUMER LAW — MANDATORY COMPLIANCE (ACCC):
These rules apply to ALL generated copy (hook, message, image_hook, image_headline, offer, cta):

1. NO FALSE OR MISLEADING CLAIMS
   - Do NOT invent statistics the brand has not claimed (e.g. "saved 1,000+ families", "over 95% success rate").
   - Do NOT use specific numbers (customer counts, dollar savings, percentage rates) unless they appear in the brand inputs.
   - Do NOT write "Voted #1", "Australia's best", "industry-leading" unless brand inputs confirm an actual award or ranking.

2. NO INVENTED FINANCIAL RATES
   - Do NOT quote a specific interest rate (e.g. "rates from 5.8%", "6.1% fixed") unless the exact rate appears in the brand/offer inputs.
   - Use relative language instead: "competitive rates", "rates that may surprise you", "compare your options".

3. NO FAKE SOCIAL PROOF OR RECENCY
   - Do NOT write "500+ happy customers", "trusted by thousands", "serving [city] for 20 years" unless confirmed by brand inputs.
   - A brand that opened 2 months ago must NOT claim years of experience or hundreds of customers.
   - Social proof must be general and believable OR drawn directly from the brand inputs.

4. GUARANTEES AND PROMISES
   - Do NOT make absolute guarantees ("guaranteed results", "100% success") without brand confirmation.
   - Softer language: "we back our work", "no-risk quote", "satisfaction backed by our team".

5. SUPERLATIVES
   - Avoid "cheapest", "lowest", "fastest", "best in [city]" unless substantiated in brand inputs.
   - Use verifiable claims: "upfront pricing", "same-day availability", "no call-out fee" (only if brand confirms).

6. CLIMATE / SEASONAL CLAIMS
   - If the SERVICE LOCATION is a hot-climate state (WA, QLD, NT) make summer heat the default pain trigger.
   - If it is a four-season state (VIC, NSW, TAS, SA, ACT) allow heating and cooling pain triggers; do not assume year-round heat.

OUTPUT RULE: If you are unsure whether a claim is backed by the brand inputs, use a softer, provable alternative.
Do NOT hallucinate specifics to make copy sound more impressive.
""".strip()

# Per-state climate context — used to colour scene and pain triggers for trade/HVAC campaigns.
AU_STATE_CLIMATE: dict[str, str] = {
    "WA":  "hot dry summers (Perth 35–45°C Jan–Mar), mild winters — cooling is the dominant pain trigger year-round",
    "NT":  "tropical heat year-round (Darwin 30–38°C), wet/dry seasons — cooling always relevant",
    "QLD": "sub-tropical to tropical; Brisbane 28–35°C summers, mild winters — cooling dominant, heating rarely needed",
    "NSW": "four seasons; Sydney summers 25–35°C, winters 8–18°C — both cooling and heating relevant",
    "VIC": "famously four seasons in one day; Melbourne summers 20–40°C, winters 5–15°C — heating equally important in winter",
    "SA":  "hot dry summers (Adelaide 35–43°C), cool winters — cooling dominant, heating needed in winter",
    "TAS": "cool temperate; Hobart 15–25°C summers, cold winters — heating is the dominant pain trigger",
    "ACT": "continental; hot summers (35°C+), cold winters with frost — heating as important as cooling",
}

AUSTRALIAN_HEYGEN_VOICE_RULE = (
    "VOICE & ACCENT (mandatory): Presenter speaks clear, warm AUSTRALIAN English — "
    "natural Aussie intonation, rhythm, and vowels. Not American. Not British. "
    "Conversational Australian business tone — like a trusted local advisor on camera."
)
