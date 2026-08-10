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
from app.services.australian_copy import (
    ACCC_COMPLIANCE_RULES,
    AU_STATE_CLIMATE,
    AUSTRALIAN_ENGLISH_BRIEF_RULES,
    AUSTRALIAN_ENGLISH_ON_IMAGE_RULES,
    enforce_australian_english_copy,
)
from app.services.brand_facts_service import (
    brand_facts_whitelist_text,
    format_brand_facts_for_llm,
)
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
        "Wholesale warehouse aisle: Commercial Director with handheld scanner beside pallet racking, industrial daylight",
        "Loading dock: delivery truck check-off, clipboard and hi-vis vest, trade cartons stacked",
        "Distribution centre: pick slot + forklift background while ops lead checks B2B order tablet",
        "Distributor back-office: Commercial Director reviewing portal order % vs phone orders, warehouse through window",
        "Trade catalogue moment: specialty food SKUs on racking with wholesale MOQ labels, buyer walking aisle",
    ],
    "trade": [
        "Residential job site: tradie on ladder, tool belt and branded van visible, golden-hour AU light",
        "5:30am driveway: owner-operator scrolling ServiceM8 on phone allocating three crews before dawn",
        "Commercial plant room / strata building: plumber quoting maintenance work, clipboard and high-vis",
        "Tradie in work van between jobs, phone showing cold Hipages lead already answered by competitors",
        "Suburban AU street: work van parked, owner checking Google Maps ranking vs competitor pin",
        "Office manager at kitchen-table desk handling scheduling while tradie husband loads tools into van",
        "Driveway service call: plumber under sink with client watching, natural daylight, van in background",
        "Commercial fit-out: electrician at switchboard, industrial interior, crew in background",
    ],
    "hvac": [
        "Hot lounge at dusk: homeowner stares at dusty wall-mounted split-system with water stain drip beneath it",
        "Outdoor condenser on concrete pad: technician connecting copper pipe while homeowner watches from patio",
        "Bedroom night heat: restless parent, pedestal fan running, indoor head unit dark/not cooling",
        "Same-day install: indoor head unit being mounted on lounge wall, ladder and refrigerant gauges visible",
        "Power-bill pain: phone showing 28C indoor vs 35C outdoor beside old indoor AC unit on the wall",
        "Fresh install social proof: new outdoor condenser + homeowner smiling — unit is hero, not the van alone",
        "Roof/ceiling ducted grille service: tech with gauges checking airflow while family waits in doorway",
        "Repair vs replace moment: tech pointing at failing outdoor compressor while homeowner holds quote clipboard",
    ],
    "roofing": [
        "Interior daylight below new skylight: homeowner looks up at bright restored roof section with clean flashing and fresh tiles visible",
        "Roof restoration payoff: homeowner touches solid freshly restored ceiling beneath modern skylight opening — outcome fills the frame",
        "Installer-on-roof outcome moment: new Keylite skylights aligned on restored tiled roof while homeowner watches from yard",
        "Bright dry living room after roof fix: skylight and clean ceiling dominate; any old stain edge is faint and secondary only",
        "Qualified roofer detail: technician finishing flashing around skylight on fresh tiles, safety harness and roofing tools visible",
        "Before/after outcome in ONE frame: restored roof/skylight as hero; tiny residual tile sample far in the corner only",
    ],
    "pro_services": [
        "Glass meeting room: advisor presenting strategy deck to clients, city view soft blur",
        "Professional at desk with client consultation, warm corporate light",
        "Whiteboard strategy session: framework sketched, collaborative mood",
        "Reception greeting client, trust and authority",
    ],
    "retail": [
        "Boutique wellness shop floor: founder preparing display before weekend rush, warm pendant lights",
        "Saturday trade: staff at counter with Shopify POS, customers browsing skincare shelves",
        "Omnichannel moment: store manager packing online click-and-collect order at the counter",
        "Shop window: passer-by pausing at clean-beauty display, inviting interior glow",
        "Retail Director on floor with Marketing Manager reviewing phone Meta ads beside styled shelves",
    ],
    "ecommerce": [
        "Home packing bench: branded DTC boxes, shipping labels, founder packing order",
        "Garage studio: product samples and ring light, authentic Shopify brand setup",
        "Scaling founder at laptop: Meta Ads + Shopify orders side by side, creative fatigue mood",
        "Courier pickup at front door: founder handing parcel to driver",
        "Content desk: UGC / product hero shoot setup feeding paid creative pipeline",
    ],
    "jewellery": [
        "UGC unboxing: hands open a jewellery pouch revealing a gold necklace / ring on soft tissue, phone-shot framing",
        "Mirror try-on: person fastening earrings or necklace, close-up sparkle, bathroom/bedroom natural light",
        "Jewellery flat-lay: rings, bracelet, chain on marble with soft shadows — product is the hero",
        "Gift moment: recipient opens a small jewellery box, genuine reaction, Sydney apartment setting",
        "Stacking rings on hand in daylight by a window — intimate product detail, not furniture or home décor",
        "Checkout / cart moment: phone showing jewellery product page beside the physical piece on the table",
    ],
    "dental": [
        "Dental consultation room: patient winces while pointing at one molar on x-ray monitor",
        "Home bathroom mirror: adult pulls cheek aside inspecting sore tooth, cold drink pushed away",
        "Dental waiting area: patient holds ice pack to jaw, root canal referral letter on lap",
        "Kitchen evening: person avoids biting hard food, dental appointment card and pain relief visible",
        "Treatment chair consult: dentist shows tooth diagram with inflamed root while patient listens",
        "Implant consult: patient studies hand mirror showing missing back molar gap beside implant x-ray with post circled",
        "Dental office desk: open implant brochure with screw-and-crown diagram next to printed jaw x-ray",
    ],
    "landscaping": [
        "BEFORE/AFTER split: LEFT overgrown neglected backyard + concerned homeowner; RIGHT same person smiling in lush transformed garden with entertaining area",
        "Dental-results style garden comparison: left weeds/patchy lawn/frustrated owner; right neat beds/pavers/proud smile — clear vertical divide",
        "Garden reveal handover: landscaper and homeowner on the AFTER half; BEFORE half still shows straggly shrubs and dead lawn",
        "Side-by-side Melbourne backyard makeover: same fence line, left wild scrub, right manicured lawn and outdoor lounge",
        "Pain-led (not before/after): homeowner deflated at edge of fully neglected yard — weeds dominate the frame",
        "Social proof (not before/after): neighbours enjoying finished entertaining area — finished garden only",
    ],
    "home_improvement": [
        "Renovation reveal: homeowner stands in newly finished space (kitchen / bathroom / deck) looking back with pride; a single unpainted wall corner hints at the journey without dominating",
        "Tradie handover: tradesperson shows client the finished result, pointing at the highlight feature; work tools packed to one side",
        "Before-to-now: homeowner touches the new feature (splashback, deck board, tap), expression of satisfaction; visible old/unfinished edge at far frame border only",
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
    "trade": (
        "trade", "tradie", "trades", "plumb", "plumber", "electric", "electrician",
        "builder", "building", "roof", "roofer", "construction", "hipages", "service seeking",
        "oneflare", "servicem8", "strata", "commercial plumber", "emergency plumber",
        "google maps", "gbp", "google business", "multi-crew", "apprentice",
    ),
    "hvac": (
        "hvac", "air con", "aircon", "air conditioning", "air-conditioning", "air conditioner",
        "split system", "split-system", "ducted", "condenser", "refrigerat", "cooling",
        "heating and cooling",
    ),
    "roofing": (
        "roof", "roofing", "roofer", "roof restoration", "restoration", "re-roof",
        "reroof", "skylight", "skylights", "keylite", "tile roof", "leaking roof",
        "roof leak", "flashing", "ridge cap", "ceiling leak",
    ),
    "landscaping": (
        "landscap", "landscaping", "landscape", "gardening", "garden design", "lawn",
        "garden", "turf", "outdoor design", "outdoor living", "backyard", "backyard design",
        "entertaining area", "paving", "pavers", "retaining wall", "garden bed",
        "mulch", "planting", "pruning", "mowing", "hedge", "irrigation", "garden maintenance",
        "green thumb", "horticultural", "horticulture",
    ),
    "home_improvement": (
        "home improvement", "renovation", "reno", "builder", "building", "construction",
        "bathroom reno", "kitchen reno", "deck", "decking", "tiling", "cladding",
        "extension", "granny flat",
    ),
    "pro_services": ("consult", "account", "legal", "advisory", "dental", "clinic", "law firm"),
    "dental": (
        "dental", "dentist", "tooth", "teeth", "molar", "root canal", "endodontic", "implant",
        "crown", "filling", "gum", "oral", "orthodont", "invisalign", "whitening", "extraction",
    ),
    "retail": ("retail", "store", "shop", "boutique", "foot traffic", "brick and mortar"),
    "ecommerce": ("ecommerce", "e-commerce", "dtc", "online store", "shopify", "unboxing"),
    "jewellery": (
        "jewellery", "jewelry", "jeweller", "jeweler", "necklace", "earrings", "bracelet",
        "pendant", "ring", "rings", "diamond", "gold chain", "fine jewellery",
    ),
}

_VARIETY_GUIDANCE = """
- Vary scene, environment, props, lighting, and camera angle across variants — do NOT repeat the same setup.
- Do NOT use the exact same laptop + coffee + notebook composition in every variant; rotate settings.
- Laptop / notepad / calculator scenes are ALLOWED only if a large industry hero prop is ALSO in frame
  (e.g. HVAC = indoor split-system or outdoor condenser behind the person). Laptop-alone = FAIL.
- Pick visuals that match what is being SOLD: e.g. a digital marketing agency → ads, targeting, leads, performance.
- Client industry (wholesale, trade, etc.) informs WHO is in the scene; the brand service informs WHAT problem is shown.
- When NICHE names a specific treatment or trade (root canal, implants, air conditioning, plumbing, etc.),
  the visual must prove THAT niche with physical objects — not generic worry, not vans-only social proof.
""".strip()

# Procedure/treatment-specific visual mandates — injected when niche keywords match.
_NICHE_PROCEDURE_HINTS: list[tuple[tuple[str, ...], str]] = [
    (
        ("root canal", "endodontic", "endodontics"),
        """ROOT CANAL NICHE — visual proof is mandatory:
- Stranger test: with text removed, viewer must say "tooth/jaw pain" or "dental treatment" — NOT "stressed at work" or "sad in office".
- Show SPECIFIC physical tooth pain: wincing while pressing one cheek/jaw, swollen side of face, refusing ice-cold drink, or studying dental x-ray with finger on ONE molar.
- Include 2+ props: dental x-ray on screen/printout, tooth diagram with root highlighted, referral letter mentioning root canal, chilled water pushed away, bathroom mirror cheek-pull to inspect gum.
- BANNED: generic corporate desk stress, paperwork piles, laptop-only scenes, ambiguous sadness without jaw/tooth gesture.""",
    ),
    (
        (
            "dental implant",
            "dental implants",
            "implant",
            "implants",
            "implant treatment",
            "implant restoration",
            "tooth implant",
            "missing tooth",
            "missing teeth",
            "edentulous",
        ),
        """DENTAL IMPLANT NICHE — visual proof is mandatory (both, not one):
- Missing-tooth evidence must be visible: a clear back-tooth gap OR cheek-pull/hand-mirror view showing the missing molar area (no guessing).
- Implant evidence must be visible: printed dental x-ray WITH implant post/crown circled OR an implant treatment diagram/brochure OR a 3D implant render on a monitor.
- Stranger test: with text removed, the viewer must say "missing teeth + dental implants" — not "sad dental patient" or "general dentistry".
- BANNED: dentures-only props with no implant diagram/x-ray, generic office/home stress, plain clinic chair with no implant plan visuals.""",
    ),
    (
        ("whitening", "teeth whitening", "bleaching"),
        """TEETH WHITENING NICHE — show stain vs brightness concern: shade guide, before photo of yellowed teeth on phone, whitening tray, coffee/wine stain awareness.
- Stranger must recognise cosmetic dental whitening — not skincare or general beauty.""",
    ),
    (
        ("invisalign", "braces", "orthodont", "aligner"),
        """ORTHODONTICS NICHE — show aligner tray, braces wire, crowded teeth concern in mirror, orthodontist consult room.
- Stranger must recognise teeth straightening — not generic dental fear.""",
    ),
    (
        ("extraction", "wisdom tooth", "toothache", "tooth pain", "abscess"),
        """ACUTE DENTAL PAIN NICHE — show sharp toothache moment: jaw clenched, one-sided chew avoided, ice pack, swollen cheek, emergency dental referral.
- Physical pain must be unmistakably DENTAL — not headache or work stress.""",
    ),
    (
        (
            "hvac",
            "air con",
            "aircon",
            "air conditioning",
            "air-conditioning",
            "air conditioner",
            "ducted",
            "split system",
            "split-system",
            "refrigerat",
            "cooling system",
            "heating and cooling",
        ),
        """HVAC / AIR CONDITIONING NICHE — visual proof is mandatory (same bar as dental implants):
- Stranger test: with ALL text removed (including laptop screens and notepads), the viewer MUST say
  "air conditioning / HVAC" — NOT "person at desk", "home finance", or "generic home service".
- EVERY variant MUST show at least ONE unmistakable physical HVAC object as a HERO / midground prop
  (roughly 25%+ of the frame or clearly beside the subject — NOT a tiny speck through a far window):
  wall-mounted indoor split-system head unit, outdoor condenser/compressor on a concrete pad,
  ducted grille, refrigerant gauges, copper pipework, or a technician physically installing/servicing a unit.
- Pain-led: failing indoor unit (dust, water stain drip under head unit), phone showing hot indoor temp,
  pedestal fan as backup, restless night heat — the broken AC is the hero prop.
- Problem-agitate-solve (critical): show PROBLEM + AGITATE + SOLVE in ONE frame —
  e.g. dusty/leaking indoor head unit OR large outdoor condenser (problem) + crumpled rival quotes /
  hot-room thermometer / pedestal fan (agitate) + technician explaining OR clear branded diagnostic
  clipboard in the subject's hands (solve). Calm "reading a clean quote at a pretty table" with only
  a tiny condenser in the garden FAILS — that is solve-only, not PAS, and barely reads as HVAC.
- Social proof / install: show a real install or fresh outdoor unit + happy homeowner — NEVER only
  smiling families + generic service vans with no AC equipment visible.
- BANNED: laptop + notepad + calculator with no AC unit in frame; street of happy families with vans
  only; generic "tradie vibe" without an air-con machine; tiny window-background condenser as the
  only HVAC cue.""",
    ),
    (
        ("plumb", "plumber", "blocked drain", "hot water", "burst pipe", "tapware"),
        """PLUMBING NICHE — visual proof mandatory:
- Show pipes, under-sink work, burst/leak water, hot-water system, or plumber under a sink with van tools.
- BANNED: laptop quote shopping or happy families with vans and no plumbing props.""",
    ),
    (
        ("electric", "electrician", "switchboard", "wiring", "power point", "electrical"),
        """ELECTRICAL NICHE — visual proof mandatory:
- Show switchboard, wiring, power tools at a board, or sparks-safe install moment with electrician.
- BANNED: laptop-only scenes or vans-only social proof with no electrical equipment.""",
    ),
    (
        (
            "roof",
            "roofing",
            "roofer",
            "roof restoration",
            "re-roof",
            "reroof",
            "skylight",
            "skylights",
            "keylite",
            "roof leak",
            "ceiling leak",
            "roof replacement",
        ),
        """ROOFING / ROOF RESTORATION / SKYLIGHT NICHE — visual proof mandatory:
- Stranger test: with all text removed, viewer must say "roof / skylight / roof restoration" — NOT
  "woman holding paperwork" or "generic home warranty decision".
- Every variant must show a PHYSICAL roofing proof object as a hero or midground cue:
  restored roof tiles, skylight opening with daylight through it, Keylite / skylight frame,
  flashing detail, ridge capping, roofer on the roof, leak stain repair, approved restoration quote,
  or a visible old damaged tile/sample pushed aside.
- For skylight / restoration before_after: SIDE-BY-SIDE dental-results style —
  LEFT leak/dark/stain concern; RIGHT bright restored skylight + relieved homeowner.
  Not after-only certificate portrait.
- For warranty/trust angles: the warranty certificate may be present, but it CANNOT be the only proof.
  The roof/skylight result itself must still be visible in frame.
- If certificates / installer credentials appear, they must be secondary props with soft/unreadable text —
  never a big readable wall poster competing with the ad copy.
- BANNED: generic smiling homeowner holding certificate with no visible roof/skylight result; generic
  architect/installers credential posters as the main proof; plain interior paperwork scenes that could
  belong to any home service; staged dirty-bucket "before props" as the visual hero.""",
    ),
    (
        (
            "landscap", "landscape", "landscaping", "gardening", "garden design",
            "lawn", "garden", "turf", "outdoor living", "backyard design",
            "entertaining area", "paving", "retaining wall", "garden bed",
            "mulch", "planting", "pruning", "mowing", "irrigation",
            "artificial turf", "synthetic turf", "artificial grass", "synthetic grass",
            "fake grass", "turf installation", "artificial lawn",
        ),
        """LANDSCAPING / GARDEN DESIGN / ARTIFICIAL TURF NICHE — visual proof of TRANSFORMATION is mandatory:
- Stranger test: with all text removed, viewer must say "garden/backyard/turf transformation".
- Artificial turf install: show real turf rolls / new synthetic lawn surface as hero proof —
  NOT a vague green lawn that could be natural grass.
- For BEFORE/AFTER (MATCH DENTAL RESULTS STYLE): SIDE-BY-SIDE REQUIRED.
  LEFT = BEFORE: patchy dead/brown natural lawn, weeds, muddy patches; homeowner concerned.
  RIGHT = AFTER: same person smiling on pristine artificial turf / perfect green lawn.
  Clear vertical contrast like Invisalign braces-vs-aligner.
  BANNED: after-only lifestyle paradise; tiny far-background whisper; peer drinks.
- For PAIN-LED: maintenance pain dominates — mowing, watering, patchy grass, frustration.
- For SOCIAL PROOF: peers on finished turf OK (different angle).""",
    ),
    (
        (
            "jewellery", "jewelry", "jeweller", "jeweler", "necklace", "earrings",
            "bracelet", "pendant", "fine jewellery", "costume jewellery",
        ),
        """JEWELLERY NICHE — product lock is mandatory (niche beats other brand categories):
- Stranger test: with text removed, viewer must say "jewellery / necklace / rings / earrings" — NOT furniture, home décor, or outdoor goods.
- Hero props: necklace, ring, earrings, bracelet, chain, jewellery box / pouch, try-on at a mirror, unboxing sparkle.
- Copy (hook, headline, offer, on-image, CTA story) must sell JEWELLERY only — even if VERIFIED BRAND FACTS or the brand kit also list furniture, outdoor, or home accessories.
- BANNED: sofas, furniture collections, "home refresh", outdoor goods, home décor staging, multi-category "curated furniture" offers.""",
    ),
    (
        (
            "home improvement", "renovation", "reno", "bathroom reno", "kitchen reno",
            "deck", "decking", "extension", "granny flat",
        ),
        """HOME IMPROVEMENT / RENOVATION NICHE — visual proof of transformation is mandatory:
- Stranger test: viewer must immediately name the specific renovation (kitchen / bathroom / deck) — not "nice room".
- Show the COMPLETED RESULT as the hero with a physical "transition edge": finished benchtop
  meeting old floor tiling still in place, new deck boards meeting old concrete, fresh paint on
  feature wall beside unpainted adjacent surface — something that says "before meets after".
- Include the homeowner actively experiencing the result (running hand along benchtop, opening new
  doors, stepping onto deck and looking back with satisfaction).
- BANNED: generic interior/exterior photo with no transformation cue; before/after split panels.""",
    ),
]

_GENERAL_DENTAL_HINT = """DENTAL NICHE — visual proof is mandatory:
- Stranger test: viewer must recognise DENTAL from the scene alone — clinic chair, overhead light, x-ray, shade guide, dental mirror, treatment diagram, or referral card.
- Pain-led angles must show JAW/TOOTH pain (cheek pressed, wincing at cold, pointing at one tooth) — never generic office sadness.
- BANNED: plain office desk, laptop paperwork, neutral worry that could be any life problem."""

_GENERAL_TRADE_HINT = """TRADE SERVICES NICHE — visual proof is mandatory:
- Stranger test: viewer must name the SPECIFIC trade from the frame (plumbing / electrical / HVAC / building)
  — not "generic tradie" or "happy family with a van".
- Put the TOOLS / MACHINE / JOB of that trade in camera (pipework, switchboard, outdoor AC condenser,
  framing timber) — vans and smiles alone FAIL.
- BANNED: laptop quote comparison with no trade equipment; street montage of families + vans only."""


def _build_niche_visual_mandate(*, niche: str, industry: str) -> str:
    """Return procedure-specific visual rules when niche names a treatment or trade."""
    hay = f"{niche} {industry}".lower().strip()
    if not hay:
        return ""
    for keywords, block in _NICHE_PROCEDURE_HINTS:
        if any(kw in hay for kw in keywords):
            return block
    dental_markers = (
        "dental", "dentist", "tooth", "teeth", "oral", "clinic", "orthodont", "periodont"
    )
    if any(m in hay for m in dental_markers):
        return _GENERAL_DENTAL_HINT
    trade_markers = (
        "trade", "tradie", "local", "construction", "builder", "home services",
    )
    if any(m in hay for m in trade_markers):
        return _GENERAL_TRADE_HINT
    return ""


# Ordered — more specific niches first.
_NICHE_CATEGORY_KEYWORDS: list[tuple[tuple[str, ...], str]] = [
    (("root canal", "endodontic", "endodontics"), "root_canal"),
    (
        (
            "dental implant",
            "dental implants",
            "implant treatment",
            "implant restoration",
            "tooth implant",
            "missing tooth",
            "missing teeth",
            "edentulous",
            "implants",
            "implant",
        ),
        "dental_implants",
    ),
    (("whitening", "teeth whitening", "bleaching"), "whitening"),
    (("invisalign", "braces", "orthodont", "aligner"), "orthodontics"),
    (("extraction", "wisdom tooth", "toothache", "tooth pain", "abscess"), "acute_dental_pain"),
    (
        (
            "hvac",
            "air con",
            "aircon",
            "air conditioning",
            "air-conditioning",
            "air conditioner",
            "ducted",
            "split system",
            "split-system",
            "heating and cooling",
            "cooling system",
        ),
        "hvac",
    ),
    (("plumb", "plumber", "blocked drain", "hot water", "burst pipe"), "plumbing"),
    (("electric", "electrician", "switchboard", "electrical install"), "electrical"),
    (
        (
            "roof",
            "roofing",
            "roofer",
            "roof restoration",
            "re-roof",
            "reroof",
            "roof leak",
            "ceiling leak",
            "skylight",
            "skylights",
            "keylite",
            "flashing",
        ),
        "roofing",
    ),
    (
        (
            "artificial turf",
            "synthetic turf",
            "fake grass",
            "artificial grass",
            "synthetic grass",
            "turf installation",
            "artificial lawn",
        ),
        "landscaping",
    ),
    (
        (
            "landscap", "landscape", "landscaping", "gardening", "garden design",
            "lawn", "garden", "turf", "outdoor living", "backyard design",
            "entertaining area", "paving", "retaining wall", "garden bed",
            "mulch", "planting", "pruning", "mowing", "irrigation",
        ),
        "landscaping",
    ),
    (
        (
            "jewellery", "jewelry", "jeweller", "jeweler", "necklace", "earrings",
            "bracelet", "ring ", "rings", "pendant", "gold chain", "diamond",
            "fine jewellery", "costume jewellery", "piercing jewellery",
        ),
        "jewellery",
    ),
    (
        (
            "home improvement", "renovation", "reno", "bathroom reno", "kitchen reno",
            "deck", "decking", "extension", "granny flat",
        ),
        "home_improvement",
    ),
]

# Keywords that prove the niche is visually present — PHYSICAL props only (not "AC quotes on laptop").
_NICHE_PROOF_KEYWORDS: dict[str, tuple[str, ...]] = {
    "root_canal": ("root canal", "inflamed root", "molar root", "ice water", "jaw wince", "x-ray", "xray"),
    "dental_implants": (
        "missing tooth", "missing molar", "molar gap", "tooth gap", "missing back",
        "implant post", "implant x-ray", "implant brochure", "screw-and-crown",
        "crown-and-post", "dental implant", "implants",
    ),
    "whitening": ("shade guide", "whitening", "stain", "bleach"),
    "orthodontics": ("aligner", "braces", "orthodont", "crowded teeth"),
    "acute_dental_pain": ("ice pack", "swollen cheek", "toothache", "emergency dental"),
    "hvac": (
        "split-system", "split system", "wall-mounted", "wall mounted", "indoor head",
        "outdoor condenser", "outdoor unit", "condenser", "compressor", "ducted",
        "air conditioner unit", "ac unit", "air-con unit", "air con unit",
        "refrigerant", "copper pipe", "installing the outdoor", "installing the indoor",
        "mounting the indoor", "water stain", "dusty vents",
    ),
    "plumbing": (
        "under sink", "under-sink", "pipe", "burst", "leak", "hot-water", "hot water system",
        "drain", "tapware", "plumber wrench", "pipe wrench",
    ),
    "electrical": (
        "switchboard", "circuit board", "wiring", "cable tray", "power point",
        "electrical panel", "conduit",
    ),
    "roofing": (
        "roof tile", "roof tiles", "restored roof", "roof restoration", "skylight", "skylights",
        "keylite", "flashing", "ridge cap", "ridge capping", "ceiling stain", "leak stain",
        "roof harness", "roofer on roof", "approved restoration quote", "tile sample",
    ),
    "jewellery": (
        "jewellery", "jewelry", "necklace", "earrings", "bracelet", "ring", "rings",
        "pendant", "chain", "jewellery box", "jewelry box", "pouch", "sparkle", "gold",
        "diamond", "try-on", "unboxing",
    ),
    "landscaping": (
        "garden bed", "garden beds", "fresh mulch", "mulch", "retaining wall", "new lawn",
        "turf", "nursery tag", "freshly planted", "paver", "pavers", "entertaining area",
        "landscaping tool", "spade", "barrow", "pruning shear", "overgrown corner",
        "old fence", "weathered fence", "transformed garden", "transformed backyard",
        "lush lawn", "newly laid", "garden transformed",
    ),
    "home_improvement": (
        "new deck", "new kitchen", "new bathroom", "renovated", "freshly tiled",
        "feature wall", "new benchtop", "transition edge", "before meets after",
    ),
}

# Short checklist ONLY when the LLM scene lacks niche proof — never a fixed scene rewrite.
_NICHE_PROOF_APPEND: dict[str, str] = {
    "root_canal": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): show jaw/cheek wince "
        "plus a dental x-ray with one inflamed molar root circled, or cold drink left untouched."
    ),
    "dental_implants": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): include at least one clear "
        "missing-tooth/molar gap OR an implant x-ray/diagram with post-and-crown visible — "
        "never a denture-only prop, never a generic office-sadness portrait."
    ),
    "whitening": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): shade guide or visible "
        "stain-vs-brightness contrast beside teeth."
    ),
    "orthodontics": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): clear aligner tray or "
        "braces wire, or crowded-teeth concern in mirror."
    ),
    "acute_dental_pain": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): ice pack / swollen cheek / "
        "one-sided chew avoid with emergency dental cue."
    ),
    "hvac": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): a PHYSICAL air-con machine "
        "must be a HERO / midground prop (indoor split-system head unit beside the subject AND/OR "
        "outdoor condenser filling a clear portion of the frame) — NOT a tiny speck through a far window. "
        "Laptop quotes, notepads, calculators, happy families, or service vans alone FAIL — "
        "the stranger must recognise HVAC with text removed."
    ),
    "plumbing": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): show real plumbing props "
        "(under-sink pipes, leak, hot-water system, or plumber tools) — vans/laptops alone FAIL."
    ),
    "electrical": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): show switchboard / wiring / "
        "electrician at a board — vans/laptops alone FAIL."
    ),
    "roofing": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): show the ACTUAL roof/skylight "
        "result as a hero cue — restored tiles, visible skylight opening/frame, flashing detail, leak repair, "
        "or roofer on the roof. A warranty certificate or approved quote may support the story, but cannot be "
        "the only proof. Keep any installer credential text secondary and unreadable. Before/after must be ONE "
        "present-time outcome with the restored result dominating the frame — residual old-problem cues tiny only."
    ),
    "landscaping": (
        "NICHE PROOF (weave into THIS scene): for before_after use SIDE-BY-SIDE like dental results — "
        "LEFT overgrown neglected yard + concerned homeowner; RIGHT lush transformed garden + proud smile. "
        "After-only lifestyle paradise FAILS."
    ),
    "jewellery": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): show REAL jewellery as the hero "
        "(necklace, ring, earrings, bracelet, chain, jewellery box / pouch). "
        "BANNED: furniture, sofas, outdoor goods, home décor collections, 'home refresh' staging."
    ),
    "home_improvement": (
        "NICHE PROOF (weave into THIS scene — do not replace setting): include a visible physical "
        "transition edge (new material meeting old) and a homeowner actively touching/experiencing "
        "the completed result — never just a nice interior shot with no transformation cue."
    ),
}

# Old boilerplate we used to prepend identically on every implant variant — strip if present.
_STALE_VISUAL_PROOF_PREFIX_RE = re.compile(
    r"(?is)^\s*VISUAL PROOF\s*[—\-:].*?(?=(?:Pain-led|Benefit|Before|After|Photoreal|"
    r"Single |Full-bleed|A \d|An? \d|\d0-something|NICHE PROOF|$))"
)

_SPLIT_COMPOSITION_RE = re.compile(
    r"(?is)\b(?:left\s+half|right\s+half|left\s+side|right\s+side|"
    r"before\s*(?:and|/|&)\s*after|split[- ](?:screen|panel|frame|moment)|"
    r"two\s+halves|side[- ]by[- ]side\s+comparison)\b[^.]*(?:\.|$)"
)


def _resolve_niche_category(*, niche: str, industry: str) -> str | None:
    hay = f"{niche} {industry}".lower().strip()
    if not hay:
        return None
    for keywords, category in _NICHE_CATEGORY_KEYWORDS:
        if any(kw in hay for kw in keywords):
            return category
    return None


_FURNITURE_HOME_DRIFT_RE = re.compile(
    r"(?i)\b(?:"
    r"furniture|sofa(?:s)?|couch(?:es)?|outdoor\s+goods|home\s+refresh|"
    r"home\s+(?:décor|decor|accessories|wares|goods)|homewares|"
    r"home\s+deserves|(?:for|of)\s+(?:our|your)\s+home\b|"
    r"living\s+room\s+set|coffee\s+table|dining\s+(?:table|set|furniture)|"
    r"wardrobe|sectional|recliner|patio\s+set|"
    r"curated\s+collection\s+of\s+furniture"
    r")\b"
)

_JEWELLERY_PRODUCT_LOCK_FIX = (
    " NICHE PRODUCT LOCK: this campaign niche is JEWELLERY — hero must be necklace/ring/"
    "earrings/bracelet/jewellery box. BANNED: furniture, sofas, outdoor goods, home décor,"
    " home refresh staging."
)


def _is_jewellery_niche(*, niche: str = "", industry: str = "", text: str = "") -> bool:
    if _resolve_niche_category(niche=niche, industry=industry) == "jewellery":
        return True
    hay = f"{niche} {industry} {text}".lower()
    return any(
        k in hay
        for k in ("jewellery", "jewelry", "jeweller", "jeweler", "necklace", "earrings")
    )


def enforce_niche_product_focus_copy(
    text: str,
    *,
    niche: str,
    industry: str,
    field: str = "hook",
) -> str:
    """
    When niche is jewellery, strip brand-kit drift into furniture / home décor copy.
    Niche wins over multi-category brand facts.
    """
    out = (text or "").strip()
    if not out or not _is_jewellery_niche(niche=niche, industry=industry, text=""):
        return out
    if not _FURNITURE_HOME_DRIFT_RE.search(out):
        return out

    if field in {"image_hook", "hook"}:
        return "Found jewellery pieces I actually love"
    if field in {"image_headline", "message"}:
        return "Jewellery that feels uniquely yours"
    if field == "offer":
        return (
            "Browse our curated jewellery — necklaces, rings, earrings, and bracelets. "
            "Shop pieces you'll actually wear — check the site for current first-order offers "
            "and shipping details."
        )
    if field == "cta":
        return "Shop Jewellery"
    return out


def enforce_niche_product_focus_in_prompt(
    prompt: str,
    *,
    niche: str,
    industry: str,
) -> str:
    """Keep jewellery-niche image prompts from drifting into furniture/home staging."""
    text = (prompt or "").strip()
    if not text or not _is_jewellery_niche(niche=niche, industry=industry, text=""):
        return text
    if "NICHE PRODUCT LOCK" in text and not _FURNITURE_HOME_DRIFT_RE.search(text):
        return text

    cleaned = _FURNITURE_HOME_DRIFT_RE.sub("jewellery piece", text)
    cleaned = re.sub(
        r"(?i)\b(?:sofa(?:s)?|couch(?:es)?|coffee\s+table|dining\s+table|wardrobe)\b",
        "jewellery display",
        cleaned,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if "NICHE PRODUCT LOCK" not in cleaned:
        cleaned = f"{cleaned}{_JEWELLERY_PRODUCT_LOCK_FIX}"
    return cleaned


def _sanitize_niche_prop_conflicts(prompt: str, *, niche: str, industry: str) -> str:
    """Remove props that contradict the niche (e.g. dentures in an implant ad)."""
    category = _resolve_niche_category(niche=niche, industry=industry)
    text = (prompt or "").strip()
    if category == "dental_implants":
        text = re.sub(
            r"(?i)\b(?:partial\s+)?denture(?:\s+case)?\b",
            "implant treatment brochure",
            text,
        )
    if category == "jewellery":
        text = enforce_niche_product_focus_in_prompt(text, niche=niche, industry=industry)
    return text


def _strip_stale_visual_proof_prefix(prompt: str) -> str:
    """Remove identical VISUAL PROOF scene prefixes that made every angle look the same."""
    text = (prompt or "").strip()
    stripped = _STALE_VISUAL_PROOF_PREFIX_RE.sub("", text).strip()
    return stripped or text


def _strip_split_composition_language(prompt: str, *, allow_comparison: bool = False) -> str:
    """
    Strip accidental collage language for most angles.
    BEFORE/AFTER is the exception — dental-style left/right comparison is REQUIRED.
    """
    text = (prompt or "").strip()
    if allow_comparison:
        # Remove anti-split mandates that would kill before/after comparisons.
        text = re.sub(
            r"(?is)\bSINGLE\s+MOMENT\s+ONLY:[^.]*?(?:split|halves|before/after)[^.]*\.?",
            " ",
            text,
        )
        text = re.sub(
            r"(?is)\bno\s+split\s+panels?\s+or\s+before/after\s+halves\.?",
            " ",
            text,
        )
        text = re.sub(r"\s{2,}", " ", text).strip()
        return text

    cleaned = _SPLIT_COMPOSITION_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if cleaned.lower() == text.lower():
        return text
    if "single full-bleed" not in cleaned.lower() and "one moment" not in cleaned.lower():
        cleaned = (
            f"{cleaned} SINGLE MOMENT ONLY: one continuous full-bleed frame, one setting, "
            f"one emotion - no split panels or before/after halves."
        )
    return cleaned


def _prompt_has_niche_proof(prompt: str, category: str) -> bool:
    lower = (prompt or "").lower()
    keys = _NICHE_PROOF_KEYWORDS.get(category) or ()
    return any(k in lower for k in keys)


def enforce_niche_visual_proof_in_prompt(
    prompt: str,
    *,
    niche: str,
    industry: str,
    ad_angle: str = "",
) -> str:
    """Ensure niche visual proof exists without forcing the same scene on every variant.

    Previously we prepended an identical bathroom-mirror block to every dental-implant
    prompt, which made different ad angles look like the same generation prompt.
    Now we only append a short checklist when proof keywords are missing.
    """
    cleaned = _strip_stale_visual_proof_prefix(prompt)
    cleaned = _sanitize_niche_prop_conflicts(cleaned, niche=niche, industry=industry)
    # Before/after MUST keep dental-style left/right comparison language.
    allow_comparison = (ad_angle or "").strip().lower() == "before_after"
    cleaned = _strip_split_composition_language(cleaned, allow_comparison=allow_comparison)
    category = _resolve_niche_category(niche=niche, industry=industry)
    if not category:
        return cleaned
    if _prompt_has_niche_proof(cleaned, category):
        return cleaned
    append = _NICHE_PROOF_APPEND.get(category, "").strip()
    if not append:
        return cleaned
    body = cleaned.strip()
    if not body:
        return append
    return f"{body} {append}"


# Place names that leak from reference ICPs / old examples — never burn onto ads unless they ARE the service area.
_ARCHETYPE_LOCATION_PHRASES: tuple[str, ...] = (
    "Western Sydney",
    "Blacktown",
    "Parramatta",
    "Hills District",
    "North Brisbane",
    "north Brisbane",
    "Brisbane's north",
    "Brisbane north",
    "Brisbane",
    "Melbourne CBD",
    "Melbourne",
    "Geelong",
    "Perth",
)


def _normalize_service_location(geography: str) -> str:
    geo = (geography or "").strip()
    if not geo:
        return ""
    # Skip ultra-generic country-only values for on-image locality claims.
    if geo.lower() in {"australia", "au", "united states", "usa", "uk", "new zealand", "nz"}:
        return ""
    return geo


_AU_STATE_ABBREV: dict[str, str] = {
    "western australia": "WA", "wa": "WA",
    "northern territory": "NT", "nt": "NT",
    "queensland": "QLD", "qld": "QLD",
    "new south wales": "NSW", "nsw": "NSW",
    "victoria": "VIC", "vic": "VIC",
    "south australia": "SA", "sa": "SA",
    "tasmania": "TAS", "tas": "TAS",
    "act": "ACT", "australian capital territory": "ACT",
    # Major city → state mappings
    "perth": "WA", "darwin": "NT",
    "brisbane": "QLD", "gold coast": "QLD", "sunshine coast": "QLD", "cairns": "QLD",
    "sydney": "NSW", "newcastle": "NSW", "wollongong": "NSW", "central coast": "NSW",
    "melbourne": "VIC", "geelong": "VIC", "ballarat": "VIC", "bendigo": "VIC",
    "adelaide": "SA", "hobart": "TAS", "launceston": "TAS", "canberra": "ACT",
}


def _state_climate_hint(geography: str) -> str:
    """Return a climate context line for the LLM when geography maps to an AU state."""
    geo = (geography or "").strip().lower()
    if not geo:
        return ""
    for token in geo.replace(",", " ").split():
        state = _AU_STATE_ABBREV.get(token)
        if state:
            climate = AU_STATE_CLIMATE.get(state, "")
            if climate:
                return (
                    f"STATE CLIMATE CONTEXT ({state}): {climate}. "
                    "Use this to pick realistic seasonal pain triggers for HVAC / cooling / heating copy."
                )
    return ""


def enforce_service_location_in_text(text: str, *, geography: str) -> str:
    """Replace archetype cities with the brief service location (or strip them)."""
    out = (text or "").strip()
    if not out:
        return out
    service = _normalize_service_location(geography)
    for phrase in _ARCHETYPE_LOCATION_PHRASES:
        if not re.search(re.escape(phrase), out, flags=re.I):
            continue
        # Keep the phrase if it is part of the real service location.
        if service and phrase.lower() in service.lower():
            continue
        if service:
            out = re.sub(re.escape(phrase), service, out, flags=re.I)
        else:
            # No service area set — remove invented locality rather than keep Western Sydney/Brisbane.
            out = re.sub(rf"(?i)\b(?:in|across|for|around|serving|trusted by)\s+{re.escape(phrase)}\b", "", out)
            out = re.sub(re.escape(phrase), "", out, flags=re.I)
    out = re.sub(r"\s{2,}", " ", out).strip(" ,.-")
    return out


_PAS_WEAK_SOLVE_ONLY_RE = re.compile(
    r"(?is)(?:calm|relief|relaxed|reading|reviewing).{0,80}(?:quote|diagnostic|clipboard)"
    r"|(?:quote sheet|printed quote|system diagnostic).{0,120}(?:relief|relaxed|hope|confidence)"
)

_HVAC_WEAK_BACKGROUND_ONLY_RE = re.compile(
    r"(?is)(?:through (?:the |a )?(?:kitchen |lounge )?window|in the (?:far )?background|"
    r"visible through).{0,60}(?:condenser|outdoor unit|compressor|air.?con)"
)

_PAS_AGITATE_CUES = (
    "water stain", "dusty", "dust", "pedestal fan", "hot", "28", "35", "crumpled",
    "dodgy", "rival quote", "three quote", "failed", "leaking", "sweat", "wince",
    "frustrated", "worried", "agitat",
)

_PAS_HVAC_APPEND = (
    "PAS + HVAC FIX (mandatory — rewrite composition, do not ignore): ONE frame must show "
    "(1) PROBLEM — indoor split-system head unit LARGE beside/behind the subject OR outdoor "
    "condenser as a clear midground hero (not a tiny window speck); "
    "(2) AGITATE — water stain / dusty vents / pedestal fan / hot-room phone temp / crumpled "
    "dodgy rival quotes; "
    "(3) SOLVE — technician explaining OR honest branded diagnostic clipboard entering the story. "
    "BANNED: calm woman only reading a clean quote at a pretty table — that is solve-only, not PAS."
)


def enforce_pas_angle_in_prompt(
    prompt: str,
    *,
    ad_angle: str,
    niche: str,
    industry: str,
) -> str:
    """Strengthen Problem-Agitate-Solve when the LLM returned a solve-only trust scene."""
    text = (prompt or "").strip()
    if (ad_angle or "").strip().lower() != "problem_agitate_solve":
        return text
    if "PAS + HVAC FIX" in text or "PAS VISUAL FIX" in text:
        return text
    lower = text.lower()
    has_agitate = any(cue in lower for cue in _PAS_AGITATE_CUES)
    weak_solve = bool(_PAS_WEAK_SOLVE_ONLY_RE.search(text))
    category = _resolve_niche_category(niche=niche, industry=industry)
    weak_hvac = category == "hvac" and bool(_HVAC_WEAK_BACKGROUND_ONLY_RE.search(text))
    # Pass only when agitation is visible AND HVAC cue is not a tiny window speck.
    if has_agitate and not weak_hvac and not weak_solve:
        return text
    if has_agitate and not weak_hvac:
        return text
    if category == "hvac" or weak_hvac or (weak_solve and category == "hvac"):
        return f"{text} {_PAS_HVAC_APPEND}"
    if weak_solve or not has_agitate:
        return (
            f"{text} PAS VISUAL FIX (mandatory): keep ONE frame but make PROBLEM and AGITATE "
            f"props large and obvious, then show the SOLVE arriving — not a calm solve-only portrait."
        )
    return text


def enforce_generic_angle_logic_in_prompt(
    prompt: str,
    *,
    ad_angle: str,
    niche: str,
    industry: str,
) -> str:
    """
    Universal ad-angle semantics that should hold for ANY industry.

    Only appends a short fix when the scene violates the angle — never spam
    ANGLE LOGIC FIX onto every prompt (that pollutes the image model).
    """
    text = (prompt or "").strip()
    angle = (ad_angle or "").strip().lower()
    if not text or not angle:
        return text

    # Strip prior ANGLE LOGIC FIX blocks so re-runs stay clean.
    text = re.sub(r"(?is)\s*ANGLE LOGIC FIX\s*\([^)]+\):.*?(?=(?:\s*[A-Z]{3,}|\s*$))", " ", text)
    text = re.sub(r"\s{2,}", " ", text).strip()

    if angle == "before_after":
        return enforce_before_after_angle_in_prompt(
            text, niche=niche, industry=industry
        )
    if angle == "pain_led":
        return enforce_pain_led_angle_in_prompt(text)
    if angle == "problem_agitate_solve":
        return enforce_pas_angle_in_prompt(
            text, ad_angle=angle, niche=niche, industry=industry
        )

    # Soft checks for other angles — only append when clearly off.
    lower = text.lower()
    if angle == "social_proof" and not any(
        k in lower for k in ("review", "recommend", "result", "completed", "peer", "customer", "client", "happy")
    ):
        return (
            f"{text} ANGLE FIX (social_proof): show believable proof-in-context — a real result, "
            f"peer recommendation, or completed job — not a vague trust portrait."
        )
    if angle == "offer_urgency" and not any(
        k in lower for k in ("urgent", "today", "deadline", "limited", "decide", "now", "this week")
    ):
        return (
            f"{text} ANGLE FIX (offer_urgency): make the decision moment feel time-sensitive "
            f"with a clear next step — not an evergreen brochure pose."
        )
    return text


_BEFORE_AFTER_THEATRICAL_RESIDUAL_RE = re.compile(
    r"(?is)\b("
    r"stained\s+(?:water\s+)?bucket|dirty\s+bucket|old\s+bucket|"
    r"crumpled\s+(?:roof\s+)?(?:assessment\s+)?report|"
    r"giant\s+(?:resolved|approved)\s+stamp|"
    r"marked\s+['\"]?resolved['\"]?|"
    r"stamp(?:ed)?\s+['\"]?(?:resolved|approved)['\"]?|"
    r"foreground.{0,40}(?:bucket|report|stamp)|"
    r"(?:bucket|report|stamp).{0,40}foreground|"
    r"thermometer|temperature\s+display|\d{1,2}\s*°\s*c"
    r")\b",
)

_BEFORE_AFTER_OUTCOME_CUES = (
    "restored", "newly installed", "fresh", "bright", "dry", "clean", "completed",
    "new ", "improved", "fixed", "installed", "skylight", "result", "outcome",
    "confident", "relief", "satisfied", "smiling", "transformed",
    # landscaping / home improvement transformation outcomes
    "transformed garden", "transformed backyard", "lush", "manicured", "entertaining area",
    "new lawn", "freshly planted", "garden bed", "new paved", "retaining wall",
    "pride", "contentment", "gazing across", "looking back", "handover",
    # general home improvement
    "newly finished", "renovation", "reveal", "completed result",
)


_BEFORE_AFTER_WEAK_RESIDUAL_RE = re.compile(
    r"(?is)\b("
    r"far\s+background|just\s+visible|whisper|faint\s+(?:edge|corner)|"
    r"tiny\s+(?:corner|sample|residual)|small\s+corner|"
    r"barely\s+visible|almost\s+hidden|soft\s+hint|hint(?:ed)?\s+at\s+only|"
    r"residual\s+contrast\s+cue|not\s+a\s+prop\s+hero"
    r")\b"
)

_BEFORE_AFTER_BEFORE_ZONE_CUES = (
    "overgrown", "neglected", "weeds", "straggly", "patchy lawn", "bare lawn",
    "untended", "wild scrub", "dead grass", "broken paver", "cracked paver",
    "before zone", "neglected zone", "old overgrown",
)

_BEFORE_AFTER_SOCIAL_PROOF_LEAK_RE = re.compile(
    r"(?is)\b("
    r"group\s+of\s+(?:four|three|friends|neighbours|homeowners)|"
    r"glasses?\s+in\s+hand|drinks?\s+in\s+hand|laughing\s+together|"
    r"peer\s+interaction|credentials?\s+that\s+matter|b\s+corporation|"
    r"iso\s*9001|certificate\s+in\s+(?:hand|frame)"
    r")\b"
)


def _inject_before_after_comparison_before_anchor(
    prompt: str,
    *,
    niche: str = "",
    industry: str = "",
) -> str:
    """Ensure dental-style comparison sits in the visual body BEFORE TEXT-ANCHOR."""
    text = enforce_before_after_angle_in_prompt(
        prompt or "", niche=niche, industry=industry
    )
    sentinel = "TEXT-ANCHOR:"
    if sentinel not in text:
        return text
    body, sep, anchor = text.partition(sentinel)
    # Move any comparison that landed in the anchor back into the body.
    comp_re = re.compile(r"(?is)\s*BEFORE/AFTER COMPARISON \(must render\)[^.]*(?:\.[^.]*){0,6}\.?")
    m = comp_re.search(anchor)
    if m:
        comp = m.group(0).strip()
        anchor = (anchor[: m.start()] + anchor[m.end() :]).strip()
        body = comp_re.sub(" ", body)
        body = f"{body.strip()} {comp} "
    elif "BEFORE/AFTER COMPARISON" not in body:
        body = enforce_before_after_angle_in_prompt(
            body, niche=niche, industry=industry
        )
    return f"{body.strip()} {sep}{anchor}".strip()


def enforce_before_after_angle_in_prompt(
    prompt: str,
    *,
    niche: str = "",
    industry: str = "",
) -> str:
    """
    BEFORE/AFTER = dental-style dual comparison (like Invisalign braces vs aligner).

    LEFT = problem / before state (concerned expression + neglected/broken props).
    RIGHT = solution / after state (confident smile + transformed result).
    Same person or same place, clear side-by-side contrast — NOT lifestyle-only after.
    """
    text = (prompt or "").strip()
    if not text:
        return text
    if "BEFORE/AFTER COMPARISON (must render)" in text:
        return text

    lower = text.lower()
    category = _resolve_niche_category(niche=niche, industry=industry)

    # Strip anti-split language that would kill the comparison.
    text = re.sub(
        r"(?is)\bSINGLE\s+MOMENT\s+ONLY:[^.]*\.?",
        " ",
        text,
    )
    text = re.sub(
        r"(?is)\bno\s+split\s+panels?[^.]*\.?|\bno\s+two\s+timeframes[^.]*\.?",
        " ",
        text,
    )
    # Strip weak whisper residuals — wrong approach for this angle.
    text = re.sub(
        r"(?is)\b(?:in\s+the\s+)?(?:far\s+)?(?:background|bottom\s+corner)[^.]*?"
        r"(?:just\s+visible|whisper|faint|tiny|small\s+corner|residual)[^.]*\.?",
        " ",
        text,
    )
    text = re.sub(r"\s{2,}", " ", text).strip()

    has_dual = bool(
        re.search(
            r"(?is)\b(left\s+(?:half|side)|right\s+(?:half|side)|side[- ]by[- ]side|"
            r"split[- ](?:screen|panel|comparison)|before\s*(?:and|/|&)\s*after|"
            r"two\s+halves|comparison\s+frame)\b",
            text,
        )
    )
    has_before_emotion = any(
        k in lower for k in ("concern", "frustrat", "unhappy", "skeptic", "worried", "deflated", "grimace")
    )
    has_after_emotion = any(
        k in lower for k in ("smile", "confident", "proud", "satisfied", "relief", "joy")
    )
    lifestyle_only = (
        any(k in lower for k in ("transformed", "lush", "paradise", "entertaining", "manicured"))
        and not has_dual
        and not has_before_emotion
    )

    if has_dual and has_before_emotion and has_after_emotion and not lifestyle_only:
        return text

    # Industry/niche-specific comparison templates (dental Invisalign pattern).
    if category == "landscaping":
        comparison = (
            " BEFORE/AFTER COMPARISON (must render like a dental results ad): "
            "SIDE-BY-SIDE split of the SAME Melbourne backyard and SAME homeowner. "
            "LEFT HALF — BEFORE: overgrown neglected yard (tall weeds, straggly shrubs, patchy dead lawn, "
            "no usable entertaining space); homeowner looks concerned/frustrated holding a dying plant or "
            "staring at the mess. "
            "RIGHT HALF — AFTER: same homeowner smiling with pride in the transformed lush garden "
            "(neat beds, fresh mulch, paved entertaining area, outdoor furniture). "
            "Clear vertical contrast — stranger must read 'garden makeover' with text removed. "
            "BANNED: lifestyle-only paradise with no before half; tiny far-background whisper of weeds."
        )
    elif category in {"hvac"}:
        comparison = (
            " BEFORE/AFTER COMPARISON (must render like a dental results ad): "
            "SIDE-BY-SIDE. LEFT — BEFORE: hot/uncomfortable room, dusty failing split-system, "
            "homeowner sweaty/frustrated. RIGHT — AFTER: same person relaxed under a new clean "
            "indoor head unit, cool comfort. Clear left/right contrast."
        )
    elif category == "roofing":
        comparison = (
            " BEFORE/AFTER COMPARISON (must render like a dental results ad): "
            "SIDE-BY-SIDE. LEFT — BEFORE: dark room / ceiling stain / leaking worry. "
            "RIGHT — AFTER: bright room under new skylight / restored roof, homeowner relieved. "
            "Clear left/right contrast."
        )
    elif category in {
        "dental_implants", "root_canal", "whitening", "orthodontics", "acute_dental_pain",
    } or category is None and any(k in f"{niche} {industry}".lower() for k in ("dental", "invisalign", "braces")):
        comparison = (
            " BEFORE/AFTER COMPARISON (must render): SIDE-BY-SIDE same person. "
            "LEFT — BEFORE: concerned expression with the problem prop (gap / metal braces / stained teeth). "
            "RIGHT — AFTER: confident smile with the solution prop (implant plan / clear aligner / whitened smile). "
            "Clear left/right contrast like a clinical results ad."
        )
    else:
        comparison = (
            " BEFORE/AFTER COMPARISON (must render like a dental results ad): "
            "SIDE-BY-SIDE dual state of the SAME subject/place. "
            "LEFT HALF — BEFORE: problem state visible (broken/neglected/painful) + concerned expression. "
            "RIGHT HALF — AFTER: solved/transformed result + confident smile. "
            "Clear vertical split — stranger reads the transformation with text removed. "
            "BANNED: after-only lifestyle shot; tiny residual before cue in far background."
        )

    return f"{text.rstrip()}{comparison}"


def enforce_pain_led_angle_in_prompt(prompt: str) -> str:
    """Universal pain-led: no solution smile / settled confidence."""
    text = (prompt or "").strip()
    if not text or "PAIN-LED FIX" in text:
        return text
    lower = text.lower()
    soft_solution = any(
        k in lower
        for k in (
            "satisfied smile", "confident smile", "relief", "relaxed shoulders",
            "settled", "restored and", "problem solved", "completed job",
        )
    )
    has_pain = any(
        k in lower
        for k in (
            "wince", "pain", "frustrated", "worried", "leak", "broken", "failing",
            "hot", "sweat", "anxious", "grimace", "irritated", "dusty", "crack",
        )
    )
    if soft_solution or not has_pain:
        return (
            f"{text} PAIN-LED FIX (universal): show the pain at its peak RIGHT NOW — no settled "
            f"confidence, no solved outcome smile. Physical/situational discomfort must be obvious "
            f"with text removed."
        )
    return text


# ---------------------------------------------------------------------------
# ACCC Compliance — post-generation copy stripper
# ---------------------------------------------------------------------------

# Patterns that signal fabricated statistics (numbers + unit without brand source).
_ACCC_FAKE_STAT_RE = re.compile(
    r"\b(\d[\d,\.]*\s*(?:\+|plus|%|per\s*cent|customers?|clients?|families|homes?|jobs?|"
    r"years?\s+(?:of\s+)?(?:experience|serving|in\s+(?:the\s+)?(?:industry|business))|"
    r"(?:five|ten|twenty)\s*(?:year|yr)))\b",
    re.I,
)

# "Voted #1", "Australia's best", "#1 in [place]"
_ACCC_SUPERLATIVE_RE = re.compile(
    r"\b(voted\s+(?:#?1|number\s+one|best)|australia(?:\'?s)?\s+(?:best|leading|number\s+one|#1)|"
    r"#1\s+(?:in|for|rated)|(?:lowest|cheapest|fastest)\s+(?:price|rate|service|in\s+\w+))\b",
    re.I,
)

# Specific financial rates e.g. "6.1%", "5.89% p.a." unless followed by a disclaimer signal.
_ACCC_RATE_RE = re.compile(
    r"\b\d{1,2}\.\d{1,2}\s*%\s*(?:p\.?a\.?|per\s+(?:annum|year|month))?\b",
    re.I,
)

# Social proof phrases that imply large scale without a citation.
_ACCC_SOCIAL_PROOF_RE = re.compile(
    r"\b(trusted\s+by\s+(?:thousands|hundreds|millions)|"
    r"(?:over|more\s+than)\s+\d[\d,\.]*\s*(?:happy\s+)?(?:customers?|clients?|families|homes?|people)|"
    r"serving\s+(?:the\s+)?(?:\w+\s+){1,3}for\s+(?:over\s+)?\d+\s+years?|"
    r"we(?:'ve|\s+have)\s+served\s+(?:over\s+)?\d[\d,\.]*)\b",
    re.I,
)

_ACCC_GUARANTEED_RE = re.compile(
    r"\b(100\s*%\s+(?:guaranteed|success|satisfaction)|guaranteed\s+results?|"
    r"results?\s+guaranteed)\b",
    re.I,
)

# Safe replacement tokens
_ACCC_REPLACEMENTS: list[tuple[re.Pattern[str], str]] = [
    (_ACCC_SUPERLATIVE_RE,     "trusted local experts"),
    (_ACCC_SOCIAL_PROOF_RE,    "local homeowners"),
    (_ACCC_RATE_RE,            "competitive rates"),
    (_ACCC_GUARANTEED_RE,      "we back our work"),
]


def enforce_accc_compliance(text: str, *, brand_inputs: str = "") -> str:
    """
    Strip or soften claims in copy that would likely breach ACCC advertising rules.

    The function never removes context from image prompts; it only softens copy fields
    (hook, message, image_hook, image_headline, offer).  Pass brand_inputs so that
    figures that appear in the brand brief are whitelisted.
    """
    out = (text or "").strip()
    if not out:
        return out
    for pattern, replacement in _ACCC_REPLACEMENTS:
        out = pattern.sub(replacement, out)
    # For fake stats: if the number doesn't appear in brand_inputs → replace.
    for match in reversed(list(_ACCC_FAKE_STAT_RE.finditer(out))):
        stat_text = match.group(0)
        if brand_inputs and stat_text.split()[0] in brand_inputs:
            continue  # brand supplied this figure — allow it
        out = out[: match.start()] + "local homeowners" + out[match.end():]
    return out


_SCENE_TOKEN_RE = re.compile(r"[a-z0-9']+", re.I)
_SCENE_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "to", "in", "on", "with", "for", "at", "by",
    "is", "are", "as", "her", "his", "their", "she", "he", "this", "that", "from",
})


def _scene_fingerprint(prompt: str) -> set[str]:
    """Lightweight token set used to detect near-duplicate scenes across variants."""
    # Focus on the visual body — ignore on-image copy / CTA tails when present.
    body = re.split(r"(?i)\b(?:burn onto|text-anchor|on-image|cta button)\b", prompt or "", maxsplit=1)[0]
    tokens = {
        t.lower()
        for t in _SCENE_TOKEN_RE.findall(body)
        if len(t) > 3 and t.lower() not in _SCENE_STOPWORDS
    }
    return tokens


def _prompts_too_similar(a: str, b: str, *, threshold: float = 0.55) -> bool:
    fa, fb = _scene_fingerprint(a), _scene_fingerprint(b)
    if not fa or not fb:
        return False
    overlap = len(fa & fb) / max(1, min(len(fa), len(fb)))
    return overlap >= threshold


def enforce_angle_scene_diversity(
    prompt: str,
    *,
    ad_angle: str,
    prior_prompts: list[str],
    variant_index: int,
    niche: str = "",
    industry: str = "",
) -> str:
    """If this prompt is too similar to an earlier variant, force a distinct setting note."""
    text = (prompt or "").strip()
    if not text or not prior_prompts:
        return text
    if not any(_prompts_too_similar(text, prev) for prev in prior_prompts):
        return text
    angle = (ad_angle or "").strip() or f"variant_{variant_index + 1}"
    category = _resolve_niche_category(niche=niche, industry=industry)
    by_category: dict[str, list[str]] = {
        "hvac": [
            "DIFFERENT SETTING REQUIRED: outdoor condenser on concrete pad being installed — not kitchen laptop.",
            "DIFFERENT SETTING REQUIRED: dusty wall-mounted indoor split-system with water stain — not street montage.",
            "DIFFERENT SETTING REQUIRED: technician mounting indoor head unit on lounge wall with gauges visible.",
            "DIFFERENT SETTING REQUIRED: night bedroom heat with pedestal fan + dark AC unit — not quote spreadsheet.",
        ],
        "dental_implants": [
            "DIFFERENT SETTING REQUIRED: dental consult room with implant model on the desk — not kitchen.",
            "DIFFERENT SETTING REQUIRED: bathroom mirror cheek-pull showing molar gap — not dining table.",
            "DIFFERENT SETTING REQUIRED: clinic waiting area with implant brochure open on lap — not apple scene.",
            "DIFFERENT SETTING REQUIRED: outdoor café patio avoiding hard food, implant referral card visible.",
        ],
        "plumbing": [
            "DIFFERENT SETTING REQUIRED: under-sink leak with pipe wrench in frame — not laptop quotes.",
            "DIFFERENT SETTING REQUIRED: hot-water system cupboard with plumber diagnosing — not street vans.",
        ],
        "electrical": [
            "DIFFERENT SETTING REQUIRED: electrician at open switchboard — not laptop quotes.",
            "DIFFERENT SETTING REQUIRED: wiring install with conduit visible — not happy families only.",
        ],
        "roofing": [
            "DIFFERENT SETTING REQUIRED: interior room under new skylight with bright daylight — not certificate-only portrait.",
            "DIFFERENT SETTING REQUIRED: roofer on restored tiled roof adjusting flashing — not generic living room trust scene.",
            "DIFFERENT SETTING REQUIRED: leak-repair aftermath with old bucket/stained sample pushed aside — not paperwork-only table.",
            "DIFFERENT SETTING REQUIRED: yard view of fresh roof section with aligned skylights — not framed credential poster as hero proof.",
        ],
        "landscaping": [
            "DIFFERENT SETTING REQUIRED: homeowner running hand along new retaining wall edge beside freshly planted bed — not generic garden pose.",
            "DIFFERENT SETTING REQUIRED: wide backyard shot with entertaining area in foreground and overgrown corner at far frame edge — not close-up plant portrait.",
            "DIFFERENT SETTING REQUIRED: landscaper handing over new paved zone to client, tools nearby, freshly turned soil visible — not relaxed person standing in garden.",
            "DIFFERENT SETTING REQUIRED: before-state dominated scene — untended lawn, straggly shrubs, no entertaining area — homeowner looking deflated at edge of yard.",
        ],
        "home_improvement": [
            "DIFFERENT SETTING REQUIRED: close-up of finished benchtop/deck board meeting old material — homeowner hand touching the new surface.",
            "DIFFERENT SETTING REQUIRED: homeowner opening new feature doors or stepping onto fresh deck, looking back with satisfaction.",
        ],
    }
    diversifiers = by_category.get(category or "", [
        "DIFFERENT SETTING REQUIRED: change room, primary action, and hero industry prop from the previous variant.",
        "DIFFERENT SETTING REQUIRED: new location + new industry object — do not reuse the same desk/prop combo.",
        "DIFFERENT SETTING REQUIRED: opposite time of day and a larger category cue object in frame.",
        "DIFFERENT SETTING REQUIRED: move outdoors or into the niche's workplace with unmistakable tools.",
    ])
    note = diversifiers[variant_index % len(diversifiers)]
    return (
        f"{text} ANGLE DIVERSITY ({angle}): this frame must NOT reuse the previous variant's "
        f"room/action/prop combo. {note}"
    )

_INDUSTRY_REFERENCE_ICPS = """
WHOLESALE — Catalogue Commander (David Marchetti):
Commercial Director at a mid-size AU specialty food & beverage wholesale distributor
(~AUD $18M turnover, warehouse + trade customers across VIC/NSW). Board wants ~15% growth;
reps + trade shows alone won't get there. B2B portal live but underused (~12% of orders vs 30% target);
Google Ads freelancer spend unclear vs wholesale orders; competitors winning with better portals / Shopping.
Pain: past agency trauma, board scrutiny, attribution gap (orders vs vanity metrics), sales team CRM avoidance.
Needs commercial language (orders, AOV, CAC, portal adoption) — NOT consumer café marketing.
(EXAMPLE psychology only — place names like Dandenong South are NOT the campaign service area.
 Always use the brief SERVICE LOCATION for any on-image or post geography.)
Visual: warehouse aisle / loading dock / B2B portal on screen / catalogue + trade packing —
industrial daylight, hi-vis, pallet racking; stranger reads "wholesale / distribution".

TRADE SERVICES — WHEN THE BRAND IS THE TRADE BUSINESS (HVAC / plumbing / electrical installer):
ICP = the HOME OWNER / property manager who needs the job done — NOT other tradie crews.
Example: Brisbane homeowner whose split-system is dying in summer heat; wants a trusted local
installer, clear quote, same-week install. Pain: sweaty nights, unreliable quotes, fear of cowboys.
Visual: hot living room / bedroom, wall-mounted indoor head unit (dusty / dripping / silent),
outdoor condenser, family discomfort, technician installing a new unit — stranger instantly reads "AC install".
NEVER write "your crews", "Hipages", "qualified leads for crews", or sell a lead-gen system to other tradies
unless the brand explicitly sells marketing/leads software.

TRADE SERVICES — Multi-Crew Builder (Shane Callahan) — USE ONLY IF THE BRAND SELLS MARKETING / LEADS / AGENCY
SERVICES TO TRADIES (digital marketing agency, lead marketplace, SaaS for trades):
Owner-operator of a commercial + residential plumbing/trade business —
(EXAMPLE psychology only — place names in this archetype are NOT the campaign service area.
 Always use the brief SERVICE LOCATION for any on-image or post geography.)
Pain: paying for Ads + Hipages but still can't fill crews; needs phone ringing with good jobs.
Visual: ServiceM8, work van, Hipages lead going cold — ONLY when brand is the agency/lead product.

PROFESSIONAL SERVICES — Trust Builder:
Managing Partner (CPA) at a mid-tier accounting/advisory firm in an Australian CBD with a regional satellite.
(EXAMPLE psychology only — do NOT copy Melbourne/Geelong into ads; use SERVICE LOCATION.)
Decision power on marketing spend and partner alignment for a 6-month horizon.
Pain: referrals drying up, internal partner buy-in politics, competitors with stronger SEO/content and clearer Google Ads presence, plus fear of non-compliant or overly-salesy regulated marketing.
They need partner-ready proof (ROI, milestones, cost-per-client clarity) and an agency workflow that upskills the marketing coordinator instead of sidelining her.
Visual: modern Australian office, glass meeting room in warm morning light; managing partner presenting a partner-ready 90-day digital growth plan on a laptop/tablet; subtle blurred compliance/governance notes; monitor shows generic (non-readable) leads/pipeline/ROI charts; authentic tailored professional mood.

RETAIL — Omnichannel Operator (Marie):
Founder / Retail Director of a multi-location health & wellness retail brand (physical stores + Shopify)
with a Marketing Manager stretched thin. Online growing but foot traffic soft; Meta ROAS declining from
creative fatigue; Google Ads on freelancer autopilot; Klaviyo / loyalty under-monetised; seasonal peaks
(EOFY, Father's Day, BF, Christmas) drive ~half of revenue.
Pain: brand aesthetic vs performance tension; competitor DTC flagships; needs agency that "gets retail"
and collaborates with in-house marketing (not replaces them).
(EXAMPLE psychology only — store suburb names are NOT the campaign service area; use SERVICE LOCATION.)
Visual: boutique wellness shop floor, warm pendant lights, styled shelves, Shopify POS / counter,
customers browsing, owner or manager on floor — stranger reads "specialty retail", not warehouse or DTC garage.

ECOMMERCE — Scaling Founder (Jordan Hale):
Founder/CEO of an Australian DTC brand on Shopify Plus (~mid seven-figure revenue) hitting the scaling wall:
Meta CAC up, blended ROAS down, creative fatigue, attribution disagreement (Triple Whale vs Meta vs GA4),
Head of Growth stretched across Meta/Google/TikTok/Klaviyo. Needs step-change capability without replacing
in-house lead — agency as partner for paid + creative velocity + retention.
Pain: plateau, creative hit-rate decline, international expansion curiosity, investor-ready growth narrative.
(EXAMPLE psychology only — do NOT invent archetype cities; use SERVICE LOCATION.)
Visual: home-studio / brand HQ packing bench, Shopify + ads dashboards, product-in-use lifestyle,
authentic DTC aesthetic — stranger reads "online brand / ecommerce", not bricks-and-mortar shop floor.

DIGITAL MARKETING AGENCY — Growth Partner:
Marketing manager or SMB owner. Pain: wasted ad spend, wrong targeting, leads going to competitors.
Visual: Meta/social ads context, dashboards, phone feed, targeting — NOT unrelated warehouse ops unless ads are the subject.
""".strip()


def _brand_sells_marketing_to_trades(*, brand_name: str, industry: str, niche: str) -> bool:
    """True only when the advertiser is an agency / lead product sold TO tradies."""
    hay = f"{brand_name} {industry} {niche}".lower()
    return any(
        kw in hay
        for kw in (
            "digital marketing", "marketing agency", "lead gen", "lead generation software",
            "lead marketplace", "hipages alternative", "ads for trad", "agency for trad",
            "ppc for trad", "seo for trad", "saas for trad", "crm for trad",
        )
    )


def _brand_is_trade_service_provider(*, brand_name: str, industry: str, niche: str) -> bool:
    """
    True when the brand itself installs / repairs / trades (HVAC, plumbing, landscaping, etc.).
    Lead Gen objective then means homeowners enquire — not selling leads to other crews.
    """
    if _brand_sells_marketing_to_trades(brand_name=brand_name, industry=industry, niche=niche):
        return False
    hay = f"{brand_name} {industry} {niche}".lower()
    trade_signals = (
        "trade", "tradie", "hvac", "air con", "aircon", "air-conditioning", "air conditioning",
        "heating", "cooling", "plumb", "electric", "electrician", "builder", "roof",
        "hot water", "split system", "ducted", "install",
        "landscap", "garden", "lawn", "turf", "outdoor living", "backyard", "paving",
        "home improvement", "renovation", "deck",
    )
    # Brand names like "Newimage Heating & Cooling" are strong signals.
    brand_l = (brand_name or "").lower()
    brand_looks_trade = any(
        kw in brand_l
        for kw in (
            "heating", "cooling", "air", "plumb", "electric", "hvac", "build", "roof",
            "landscap", "garden", "lawn",
        )
    )
    return brand_looks_trade or any(kw in hay for kw in trade_signals)


# SaaS / waitlist / agency CTAs that never belong on a local trade / landscaping homeowner ad.
_MISMATCHED_HOME_SERVICE_CTA_RE = re.compile(
    r"(?i)\b("
    r"join\s+the\s+list|join\s+waitlist|join\s+now|sign\s+up|subscribe|"
    r"start\s+free(?:\s+pilot)?|request\s+(?:a\s+)?demo|book\s+a\s+demo|"
    r"get\s+partner[- ]?ready|partner[- ]?ready\s+plan|start\s+trial|"
    r"download\s+(?:the\s+)?app|claim\s+free\s+review|get\s+free\s+audit|"
    r"request\s+strategy\s+call"
    r")\b"
)


def _home_service_cta_pool(*, industry: str, niche: str, cta_hint: str = "") -> list[str]:
    """CTAs a homeowner would actually tap for trade / landscaping / home services."""
    hint = (cta_hint or "").strip()
    hay = f"{industry} {niche}".lower()
    if any(k in hay for k in ("landscap", "garden", "lawn", "turf", "outdoor", "backyard")):
        pool = [
            "Book Free Consultation",
            "Book Free Quote",
            "Get Garden Quote",
            "Schedule Site Visit",
            "Book Design Chat",
        ]
    elif any(k in hay for k in ("dental", "tooth", "implant", "orthodont")):
        pool = [
            "Book Consultation",
            "Book Free Assessment",
            "Book Appointment",
            "Check Availability",
        ]
    elif any(k in hay for k in ("hvac", "air con", "aircon", "plumb", "electric", "roof", "trade")):
        pool = [
            "Book Free Quote",
            "Get Free Quote",
            "Book Site Visit",
            "Schedule Assessment",
            "Request Call Back",
        ]
    else:
        pool = [
            "Book Free Quote",
            "Book Consultation",
            "Get Free Quote",
            "Book Free Assessment",
        ]
    if hint and not _MISMATCHED_HOME_SERVICE_CTA_RE.search(hint):
        pool = [hint] + [c for c in pool if c.lower() != hint.lower()]
    return pool


def enforce_cta_copy_coherence(
    *,
    cta: str,
    image_hook: str,
    image_headline: str,
    hook: str = "",
    message: str = "",
    ad_angle: str = "",
    brand_name: str = "",
    industry: str = "",
    niche: str = "",
    used_ctas: set[str] | None = None,
    cta_hint: str = "",
) -> str:
    """
    Force CTA to match the story on the image + the industry.

    Fixes cases like Social Proof about garden credentials + CTA "Join the List".
    """
    cta_out = (cta or "").strip()
    used = used_ctas or set()
    is_home = _brand_is_trade_service_provider(
        brand_name=brand_name, industry=industry, niche=niche
    ) or _resolve_niche_category(niche=niche, industry=industry) in {
        "landscaping", "home_improvement", "hvac", "plumbing", "electrical", "roofing",
        "dental_implants", "root_canal", "whitening", "orthodontics", "acute_dental_pain",
    }

    if is_home and (not cta_out or _MISMATCHED_HOME_SERVICE_CTA_RE.search(cta_out)):
        for candidate in _home_service_cta_pool(industry=industry, niche=niche, cta_hint=cta_hint):
            if candidate.lower() not in used:
                cta_out = candidate
                break
        else:
            cta_out = _home_service_cta_pool(industry=industry, niche=niche)[0]

    # Soft angle-aware swap when CTA fights the on-image story.
    combined = f"{image_hook} {image_headline} {hook} {message}".lower()
    angle = (ad_angle or "").lower()
    if is_home and angle in {"social_proof", "testimonial", "before_after"}:
        if any(k in combined for k in ("credential", "qualified", "trust", "proven", "choose", "neighbour", "homeowner")):
            preferred = "Book Free Consultation" if "landscap" in f"{industry} {niche}".lower() or "garden" in f"{industry} {niche}".lower() else "Book Free Quote"
            if _MISMATCHED_HOME_SERVICE_CTA_RE.search(cta_out) or cta_out.lower() in used:
                if preferred.lower() not in used:
                    cta_out = preferred
    return cta_out


def _is_artificial_turf_niche(*, niche: str = "", industry: str = "", text: str = "") -> bool:
    hay = f"{niche} {industry} {text}".lower()
    return any(
        k in hay
        for k in (
            "artificial turf", "synthetic turf", "fake grass", "artificial grass",
            "synthetic grass", "turf installation", "artificial lawn", "pet turf",
        )
    )


def _angle_image_lines_for_niche(
    *,
    ad_angle: str,
    niche: str,
    industry: str,
    hook: str,
    message: str,
) -> tuple[str, str] | None:
    """Angle + niche specific on-image twins — never generic landscaper credentials for turf."""
    angle = (ad_angle or "").lower().strip()
    turf = _is_artificial_turf_niche(niche=niche, industry=industry, text=f"{hook} {message}")
    hay = f"{niche} {industry} {hook} {message}".lower()

    if turf:
        if angle == "social_proof":
            return "Melbourne families already switched", "Hassle-free turf they love"
        if angle == "testimonial":
            return "Parents love this lawn switch", "No more patchy embarrassment"
        if angle == "problem_agitate_solve":
            hay_post = f"{hook} {message}".lower()
            if "winter" in hay_post:
                return "Lawn a disaster every winter?", "Switch to turf that stays green"
            if any(k in hay_post for k in ("water", "fertilis", "fertiliz", "mow", "bills")):
                return "Still paying to fight the lawn?", "Turf that ends the maintenance cycle"
            return "Brown patches every winter?", "Switch to perfect turf year-round"
        if angle == "pain_led":
            return "Still mowing patchy grass?", "Ditch the endless lawn battle"
        if angle == "before_after":
            return "From patchy to perfect turf", "Same yard. Zero maintenance"
        if angle == "myth_busting":
            return "Think artificial looks fake?", "See turf that fools the eye"
        if angle in {"offer_urgency", "fomo_scarcity"}:
            return "Ready for a turf upgrade?", "Book your free turf consult"
        return "Tired of patchy natural lawn?", "Get pristine artificial turf"

    if "landscap" in hay or "garden" in hay or "backyard" in hay:
        if angle == "social_proof":
            return "Neighbours love this garden glow-up", "Real homes. Real outdoor living"
        if angle == "problem_agitate_solve":
            return "Yard looking neglected again?", "Get a garden that finally works"
        if angle == "pain_led":
            return "Weekend mowing wearing you out?", "Reclaim your backyard weekends"
        if angle == "before_after":
            return "From overgrown to stunning", "Your backyard transformation starts here"

    if any(k in hay for k in ("hvac", "air con", "aircon", "split system")):
        if angle == "social_proof":
            return "Locals already cool again", "Trusted install. Real comfort"
        if angle == "problem_agitate_solve":
            return "AC packing it in this heat?", "Get a local install quote today"
        if angle == "pain_led":
            return "Sweating through another night?", "Fix the AC that failed you"
        if angle == "before_after":
            return "From stuffy nights to cool air", "New system. Instant relief"

    return None


_CREDENTIAL_FLUFF_RE = re.compile(
    r"(?i)\b("
    r"proven\s+landscapers?|real\s+credentials?|credentials?\s+that\s+matter|"
    r"iso\s*\d+|b\s*corp|no\s+guesswork|qualified\s+landscapers?"
    r")\b"
)


def enforce_on_image_story_match(
    *,
    image_hook: str,
    image_headline: str,
    hook: str,
    message: str,
    ad_angle: str = "",
    industry: str = "",
    niche: str = "",
) -> tuple[str, str]:
    """
    Keep on-image hook + headline related to post copy AND the assigned ad angle.

    Fixes: Social Proof for artificial turf must NOT become 'proven landscapers / credentials'.
    PAS: image_hook = problem/agitate, image_headline = solve — same niche story as the post.
    """
    ih = (image_hook or "").strip()
    ihl = (image_headline or "").strip()
    angle = (ad_angle or "").lower().strip()
    combined_post = f"{hook} {message}".lower()
    combined_img = f"{ih} {ihl}".lower()
    turf = _is_artificial_turf_niche(niche=niche, industry=industry, text=combined_post)

    # Detect wrong-story on-image lines for this niche/angle.
    wrong_credentials = bool(_CREDENTIAL_FLUFF_RE.search(combined_img)) and (
        turf or angle in {"social_proof", "problem_agitate_solve", "pain_led", "before_after"}
    )
    # Social proof about families/turf must not talk landscaper credentials.
    social_needs_peers = angle in {"social_proof", "testimonial"} and turf and not any(
        k in combined_img for k in ("family", "families", "neighbour", "parents", "switched", "chose", "love")
    )
    # PAS: hook = problem/agitate; headline = solve; stay on the same pain as the post.
    post_pas_tokens = {
        k for k in (
            "winter", "patch", "brown", "mow", "water", "fertilis", "fertiliz",
            "disaster", "tired", "bills", "mud", "dog", "pets",
        )
        if k in combined_post
    }
    img_shares_post_pain = bool(post_pas_tokens) and any(k in combined_img for k in post_pas_tokens)
    pas_has_problem_shape = any(
        k in combined_img
        for k in ("?", "tired", "still", "patch", "brown", "mow", "water", "disaster", "crazy", "fail")
    )
    pas_solve_ok = turf and (
        "turf" in combined_img or "year-round" in combined_img or "perfect" in combined_img
    )
    pas_mismatch = angle == "problem_agitate_solve" and (
        wrong_credentials
        or (turf and not pas_solve_ok and "lawn" not in combined_img)
        or not pas_has_problem_shape
        or (turf and post_pas_tokens and not img_shares_post_pain)
    )
    # Lines empty / too short / wrong story → rebuild from angle+niche or post.
    needs_rebuild = (
        not ih
        or not ihl
        or len(ih.split()) < 2
        or len(ihl.split()) < 2
        or wrong_credentials
        or social_needs_peers
        or pas_mismatch
    )

    if needs_rebuild:
        angled = _angle_image_lines_for_niche(
            ad_angle=angle, niche=niche, industry=industry, hook=hook, message=message
        )
        if angled:
            ih, ihl = angled
        else:
            derived_h, derived_m = _related_image_lines(hook, message, ad_angle=angle, niche=niche)
            ih = derived_h or ih
            ihl = derived_m or ihl

    return _billboard_words(ih, 7), _billboard_words(ihl, 8)

_ICP_FROM_CAMPAIGN_SYSTEM = f"""
You are an expert ICP strategist for AUSTRALIAN businesses.

Build the Ideal Customer Profile from:
- INDUSTRY = what the BRAND is (e.g. Mortgage Broking)
- NICHE = campaign specialty / offer angle (e.g. First Home Buyers, Refinance, Investment Loans)
- OBJECTIVE = what the ad must drive (awareness / traffic / lead_generation / conversions / purchase)
- BRAND NAME = the advertiser

CRITICAL RULES:
1) The ICP is the PERSON WHO SEES THE AD and should take the objective action — usually the brand's end customer, NOT another business in the same industry.
2) If INDUSTRY is Mortgage Broking / finance broker and OBJECTIVE is conversions / purchase / add_to_cart / lead_generation:
   → ICP = home buyers, refinancers, or property owners who need a loan — NOT other mortgage brokers.
   → Do NOT invent a B2B "broker selling lead-gen systems to other brokers" story unless NICHE explicitly says the brand sells lead-gen software/services TO brokers.
3) If INDUSTRY is Trade Services / HVAC / Heating & Cooling / Plumbing / Electrical AND the BRAND is the installer
   (e.g. "Newimage Heating & Cooling", niche "Air Conditioning Installation"):
   → ICP = homeowners / property managers who need the job (install, repair, quote) — NOT other tradie crews.
   → OBJECTIVE lead_generation = homeowner fills a form / calls for a quote from THIS brand.
   → FORBIDDEN audience: "your crews", "booked crews", "qualified leads for crews", Hipages replacement,
     selling a lead system to other AC companies. That is agency-to-tradie copy — wrong unless the brand is an agency.
4) If OBJECTIVE is lead_generation: ICP is still the end customer of the brand's service unless niche clearly
   says the product IS leads/software sold to other businesses.
5) Niche words like "Lead Generation" under a broker/trade brand usually mean the campaign goal (get enquiries) —
   still write ads for home-loan buyers / homeowners unless niche clearly means selling leads as a product.
6) Never ignore OBJECTIVE. Purchase/conversions/lead_gen = buyer ready to act on the brand's core offer.

Output plain text in this exact format (no markdown):

AVATAR NAME: <FirstName LastName — "Archetype Nickname">
IDENTITY: <2-3 sentences: role, company/household, AU location, decision power>
CURRENT REALITY: <2-3 sentences: what is happening in their world right now>
CORE PAIN: <1-2 sentences: deepest frustration>
DESIRED OUTCOME: <1-2 sentences: what they want after the solution>
KEY OBJECTION: <1 sentence>
BUYING TRIGGER: <1 sentence>
LANGUAGE THEY USE: <3-5 short Australian phrases>

When the brand IS a trade installer, use the homeowner trade archetype (not Multi-Crew Builder).
Use Multi-Crew Builder / Trust Builder ONLY when the brand sells marketing/agency services to those buyers.
Prefer the matching reference archetype's avatar, pains, language, and visual world —
do not invent a generic office buyer when Trade Services (homeowner) or Professional Services applies.
{AUSTRALIAN_ENGLISH_BRIEF_RULES}
Plain text only — no bullets, no extra sections.
""".strip()

_VARIANTS_SYSTEM = f"""
You are an award-winning Creative Director at a global advertising agency, producing
high-converting Australian digital ad creatives. Your job is NOT to generate beautiful
AI images — it is to generate ADVERTISEMENTS that convert.

{ACCC_COMPLIANCE_RULES}

{AUSTRALIAN_ENGLISH_ON_IMAGE_RULES}

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
     whitening tray; HVAC / air con → wall-mounted indoor split-system head unit, outdoor
     condenser on a concrete pad, refrigerant gauges, copper pipework, dusty vents / water stain;
     plumbing → under-sink pipes, leak, hot-water system; electrical → switchboard, wiring;
     mortgage/finance → paperwork with rate figures, house glimpsed through a
     window, keys, calculator; fitness → gym floor, equipment, training space; legal → office
     with case files, gavel/scales motif, courthouse exterior; hospitality/food → kitchen,
     plated dish, dining room; automotive → showroom, workshop bay, the vehicle itself;
     beauty → salon chair, mirror, treatment tools; real estate → property exterior, open
     home signage, for-sale board; jewellery / ecommerce jewellery → necklace/earrings try-on,
     jewellery box unboxing, ring flat-lay (never furniture or home-décor hero).
   - A GENERIC location (plain office desk, blank laptop screen, neutral hallway, empty room)
     with NO industry object anywhere in frame is a FAILURE, even if the emotion and copy are
     perfect — the viewer must recognise the industry from the background alone, not just from
     the on-image text.
   - Tiny text ON a laptop/notepad/phone does NOT count as a category cue — image models render
     it unreadable and strangers cannot see it. The physical machine/tool/location must be large
     in frame (e.g. the AC unit itself, not "AC quotes" typed on a spreadsheet).
   - REALISTIC PROP TEXT (critical — image models hallucinate fake labels):
     * NEVER print rates, prices, logos, slogans, or numbers on a laptop lid, laptop back,
       laptop chassis, phone case, calculator body, or any device exterior. That looks fake.
     * NEVER repeat the same percentage (e.g. 6.2%) more than ONCE in the whole frame.
     * If a rate must appear as a story prop: show it ONCE only — preferably handwritten or
       printed on ONE paper/letter/comparison sheet on the table. Not on the laptop + paper +
       notepad + screen all at once.
     * Prefer UNREADABLE / soft-blurred figures on screens. The story is the person's emotion
       + house/keys/paperwork — not a wall of duplicated rate stickers.
     * Do NOT invent a specific interest rate in the scene unless VERIFIED BRAND FACTS lists it.
       Without a verified rate, show bank letters / comparison paperwork with figures blurred
       or turned away from camera.
   - Service vans + smiling families with NO trade equipment in frame FAIL the stranger test
     for HVAC/plumbing/electrical — the outdoor unit, pipes, or switchboard must be visible.
   - If the story requires a non-industry location (e.g. someone self-conscious at their own
     work desk before a dental fix), you MUST still insert a bridging industry object into
     that scene (a phone screen showing a booking confirmation, a hand mirror, a takeaway cup
     from the clinic) — never leave the setting industry-neutral.
3. CATEGORY CUE + PROOF TOGETHER: the winning frame is ONE decisive moment — the industry
   object grounds the scene, and a prop, gesture, or reaction PROVES the single_message at
   a glance: a result being revealed, a burden visibly lifted, a person reacting to the benefit.
   (e.g. home-loan ad: the house visible through the window WHILE the buyer studies a document
   showing a lower rate — the stranger reads "cheaper home loan" in one glance.)
   CRITICAL — for most angles: ONE moment, ONE setting, ONE emotion.
   EXCEPTION — before_after ONLY: SIDE-BY-SIDE dual comparison is REQUIRED (dental results style).
   LEFT = before/problem + concerned expression; RIGHT = after/result + confident smile.
   Same person or same place. Do NOT collapse before_after into an after-only lifestyle shot.
4. EMOTION CHECK (every face must ACT its story role — direct them like a film director):
   - For before_after: TWO expressions in one comparison frame (LEFT concerned, RIGHT confident smile).
   - For all other angles: Choose ONE story state per image: PROBLEM state OR SOLUTION state, never both.
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
6. NICHE / PROCEDURE SPECIFICITY (when NICHE names a treatment OR product category —
   root canal, implants, whitening, jewellery, etc.):
   - The NICHE is more specific than the industry. A "Root Canal" ad is NOT a generic "dental" ad.
     A "Jewellery" niche ecommerce ad is NOT a generic home/furniture store ad — even if the brand
     kit or website also sells furniture, outdoor goods, or home accessories.
   - NICHE PRODUCT LOCK (critical): when NICHE names a product category, EVERY hook, headline,
     offer, CTA story, and image prompt MUST sell THAT niche only. Ignore other product lines in
     VERIFIED BRAND FACTS / brand kit for this campaign. Jewellery niche → jewellery only.
   - Pain-led angles must show the EXACT physical problem for THAT procedure (jaw/tooth wince,
     x-ray, sensitivity, swollen cheek) — never ambiguous office sadness that could mean anything.
   - Stranger test must name the PROCEDURE / PRODUCT CATEGORY from visuals alone before reading text.
   - If you cannot ground the scene in the niche, move to a dental clinic or home bathroom/kitchen
     moment with unmistakable dental props — do NOT default to corporate office desks.
     For jewellery: mirror try-on, unboxing pouch, flat-lay rings — never sofa / furniture staging.
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
- visual: buyer at kitchen table, bank letters pushed aside, ONE comparison sheet with a single
  lower rate circled once in green — relief starting to show on their face. Laptop lid is blank
  (no text on the chassis). No duplicate rate stickers anywhere else in frame.
WRONG: inventing a new FOMO angle on the image ("Peers are locking in better rates") that breaks the single_message.
WRONG: printing "RATE: 6.2%" on the laptop lid AND again on paper AND again on a notepad — looks fake and cluttered.
NOTE: this example only illustrates the reasoning — NEVER reuse its scene, industry, or wording.
Derive every visual from THIS campaign's industry, niche, brand, objective, angle, and ICP.

Dental implant example (niche-specific — follow this LEVEL of visual proof, never copy this exact scene):
- single_message: "Dental implants replace missing teeth permanently so you can eat and smile with confidence."
- visual: bathroom mirror moment — patient pulls cheek aside revealing a clear missing back-molar gap;
  on the counter: printed jaw x-ray with implant post circled + open implant brochure with screw-and-crown diagram.
- WRONG: partial denture case only (reads as dentures, not implants), generic office sadness, smiling portrait with no gap or implant plan visible.
- CRITICAL: each ad ANGLE needs a DIFFERENT setting/action (pain-led ≠ before/after ≠ social proof). Never reuse the same person+prop combo (e.g. Margaret + apple + kitchen) across variants.

Landscaping / Garden Design example (BEFORE/AFTER must match dental results style):
- single_message: "A neglected backyard becomes a beautiful outdoor living space — professional landscaping with lasting results."
- BEFORE/AFTER visual: SIDE-BY-SIDE split of the SAME homeowner and SAME backyard.
  LEFT — BEFORE: overgrown weeds, straggly shrubs, patchy lawn; homeowner looks concerned/frustrated.
  RIGHT — AFTER: same person smiling with pride in lush garden + paved entertaining area.
  Clear vertical contrast like Invisalign braces-vs-aligner ads.
- WRONG: after-only lifestyle paradise with no before half; tiny far-background weed whisper; peer drinks.
- For PAIN-LED angle: neglected yard DOMINATES; homeowner frustrated (single moment — not a split).

Output ONLY valid JSON:
{{
  "variants": [
    {{
      "use_cases": ["id1"],
      "intent": {{
        "audience": "one line",
        "problem": "one line",
        "action": "one line",
        "emotion": "one word or phrase",
        "single_message": "the ONE thing this creative communicates"
      }},
      "hook": "full post hook — strong and complete",
      "message": "full post headline — strong and complete",
      "image_hook": "max 6 words, catchy, same idea as hook",
      "image_headline": "max 8 words, catchy, same idea as message",
      "cta": "2-4 word button text unique to this variant",
      "offer": "caption follow-up in 2–3 sentences, never burned on the image",
      "prompt": "art-directed image prompt, one paragraph 120-260 words. For before_after: describe clear LEFT before / RIGHT after comparison. For other angles: single moment, single setting, single emotion.",
      "reasoning": "one sentence: name the industry-specific location/object visible in the background (the setting cue), what a stranger would say the image shows with text removed (must match the single_message), and how the copy reinforces it"
    }}
  ]
}}

Rules:
- Each variant MUST differ in scene, angle, hook, message, image lines, CTA, use cases, environment, props, and lighting — but each variant is ONE message told cohesively.
- When a VARIANT AD ANGLE ASSIGNMENT is provided, that variant MUST use ONLY that angle for intent + hook + visual.
- When AD STYLES / HOOK FRAMEWORKS are provided, they are MANDATORY — hooks AND visuals must clearly match them.
- If pattern_interrupt is selected: NEVER produce generic stock meeting/laptop huddle scenes; the image must feel unexpected and scroll-stopping; do NOT use the phrase "professional stock photography".
- use_cases: 1-3 ids from the catalogue only.
- prompt MUST describe the visual story FIRST (subject, action, stakes, emotion, props), THEN the exact on-image text: burn ONLY image_hook + image_headline + CTA. Never put full hook/message/offer text on the image.
- prompt MUST mention the selected ad style by name when frameworks are provided (e.g. "pattern interrupt stop-the-scroll commercial").
- ON-IMAGE COPY: industry/niche vocabulary, speaks to the ICP's fear or desire, Australian English
  (catchy Aussie billboard — not flat US corporate), never the persona's first name.
  Applies to EVERY industry — wholesale, retail, ecommerce, trade, dental, HVAC, finance, etc.
- LOCATION ON-IMAGE: use ONLY the campaign SERVICE LOCATION when naming a place. Never invent Western Sydney, Brisbane, Melbourne, or other archetype cities from reference ICPs.
- CTA RULES (critical):
  - Every variant MUST include its own `cta` field, matched to the objective's action (e.g. Book Consultation, Get Free Audit, Claim Free Review, Book Free Quote).
  - Do NOT use "Learn More" unless the campaign is pure awareness with no conversion action.
  - CTA MUST match the on-image story: if image_hook/headline talk about garden credentials / trust / transformation, CTA is Book Free Consultation or Book Free Quote — NEVER "Join the List", "Start Free Pilot", "Request Demo", or waitlist language on a local trade / landscaping / home-service ad.
  - image_hook + image_headline + CTA must read as ONE coherent message a stranger would understand in 2 seconds.
  - If a CTA HINT is provided, treat it as optional guidance — still vary CTAs across variants when it improves the angle.
  - Never repeat the exact same CTA across all variants in one batch.
- Human subjects: sharp visible faces, authentic Australian context, real emotion — not catalogue smiles.
- CHILDREN IN ADS (critical — Runway content policy): if the subject is a child or family with children, NEVER describe the child as anxious, scared, frightened, crying, distressed, grimacing, wincing, mouth-open-in-pain, or in a vulnerable medical situation. Show children as calm, curious, smiling, or happy. Dental-context children must be relaxed/content in a colourful child-friendly environment, not in a clinical chair looking worried.
- Single full-bleed photo for most angles — ONE moment, ONE setting, ONE emotion.
  EXCEPTION before_after: SIDE-BY-SIDE left/right comparison is REQUIRED (dental results style —
  LEFT before/problem + concerned face; RIGHT after/result + confident smile).
  For non-before_after angles: no collage, no dual narrative moments.

UNIQUENESS (critical):
- Follow the REQUIRED SCENE MANDATE for each variant as a starting point, then make it specific to the ICP and the single_message.
- Match the visual to what the BRAND SELLS and who the ICP is — service context beats random industry stock imagery.
- Vary camera angle, time of day, interior vs exterior, and subject action across variants.
- Avoid repeating the same scene/prop combo across variants in one batch (e.g. do not generate three café-laptop shots).
- Different AD ANGLES MUST produce visually different prompts: change location, primary action, hero prop, and emotion.
  If two variants share the same subject name + same food/prop + same room, that is a FAILED batch — rewrite one.
- NEVER start every prompt with the same canned "VISUAL PROOF" paragraph — prove the niche inside each unique scene.
""".strip()  # end _VARIANTS_SYSTEM


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


def _related_image_lines(
    hook: str,
    message: str,
    *,
    ad_angle: str = "",
    niche: str = "",
) -> tuple[str, str]:
    """
    Meaning-preserving condensed lines for the photo.
    Prefer short rewrites that keep the same idea — never invent a new angle,
    and never return a broken word-clip of the full post hook.
    """
    hook_l = (hook or "").lower()
    msg_l = (message or "").lower()
    combined = f"{hook_l} {msg_l} {(niche or '').lower()}"
    angle = (ad_angle or "").lower()

    angled = _angle_image_lines_for_niche(
        ad_angle=angle, niche=niche, industry="", hook=hook, message=message
    )
    if angled:
        return _billboard_words(angled[0], 7), _billboard_words(angled[1], 8)

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
    elif any(k in combined for k in ("jewell", "jewelr", "necklace", "earring", "bracelet", "pendant")):
        image_hook = "Jewellery that actually feels you"
        image_headline = "Shop pieces under $200"
    elif any(k in combined for k in ("air con", "aircon", "hvac", "split system", "ducted")) and "turf" not in combined:
        image_hook = "AC packing it in?"
        image_headline = "Book a local install quote"
    elif _is_artificial_turf_niche(text=combined):
        if any(k in combined for k in ("family", "families", "neighbour", "switched", "already", "parents")):
            image_hook = "Melbourne families already switched"
            image_headline = "Hassle-free turf they love"
        elif any(k in combined for k in ("patch", "brown", "winter", "mow", "water", "disaster", "tired")):
            image_hook = "Brown patches every winter?"
            image_headline = "Switch to perfect turf year-round"
        else:
            image_hook = "Tired of patchy natural lawn?"
            image_headline = "Get pristine artificial turf"
    elif any(k in combined for k in ("landscap", "garden", "backyard", "outdoor oasis", "overgrown")):
        if any(k in combined for k in ("overgrown", "transform", "oasis", "before", "after", "stunning")):
            image_hook = "From overgrown to stunning"
            image_headline = "Your backyard transformation starts here"
        else:
            image_hook = "Ready for a garden makeover?"
            image_headline = "Book a local design consult"
    elif any(k in combined for k in ("lead", "tyre", "tire kicker", "convert")) and any(
        k in combined for k in ("crew", "hipages", "tradie", "agency")
    ):
        image_hook = "Tired of tyre-kicker leads?"
        image_headline = "Attract ready-to-act buyers"
    else:
        image_hook = _billboard_words(hook, 6)
        image_headline = _billboard_words(message, 8)
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

_RATE_PCT_RE = re.compile(r"\b\d{1,2}\.\d{1,2}\s*%", re.I)
_FAKE_DEVICE_LABEL_RE = re.compile(
    r"(?is)(?:(?:rate|rates?|%\s*|interest|apr|p\.?a\.?)[^.\,\;]{0,40})?"
    r"(?:printed|stamped|written|engraved|labelled|labeled|stuck|stickered|shown|displayed|burned)"
    r"[^.\,\;]{0,40}"
    r"(?:on\s+(?:the\s+)?)?(?:laptop\s+(?:lid|back|chassis|cover|shell|exterior)|"
    r"back\s+of\s+(?:the\s+)?laptop|laptop\s+exterior|device\s+(?:lid|back|chassis))",
)
_LAPTOP_RATE_RE = re.compile(
    r"(?is)(?:laptop|notebook|macbook)[^.\,\;]{0,60}"
    r"(?:rate|%\s*|interest|\d{1,2}\.\d{1,2}\s*%)|"
    r"(?:rate|%\s*|interest|\d{1,2}\.\d{1,2}\s*%)[^.\,\;]{0,60}"
    r"(?:laptop\s+(?:lid|back|chassis|cover)|back\s+of\s+(?:the\s+)?laptop)",
)

_REALISTIC_PROP_FIX = (
    " PROP REALISM FIX (mandatory): NEVER print rates, prices, or slogans on a laptop lid, "
    "laptop back, chassis, phone case, or calculator body — those surfaces stay blank/brand-logo only. "
    "Show at most ONE interest-rate figure in the entire frame, on ONE paper/letter/comparison sheet "
    "(handwritten or printed once, optionally circled once). Do NOT repeat the same % on notepad + "
    "paper + laptop + screen. Prefer soft-blurred / unreadable figures on any digital screen."
)

_NO_INVENTED_RATE_FIX = (
    " RATE PROP FIX (mandatory): do NOT invent a specific interest rate percentage in the scene. "
    "Show bank letters or a comparison sheet with figures soft-blurred or facing away from camera. "
    "Laptop lid stays blank — no rate text on any device exterior."
)

# Image models over-literalise "circled figure on paper" into a random white sheet + red ring.
_CIRCLED_PAPER_PROP_RE = re.compile(
    r"(?is)\b("
    r"(?:single\s+)?(?:blurred\s+or\s+)?(?:single\s+)?circled\s+(?:rate\s+)?figure(?:\s+on\s+paper)?|"
    r"optionally\s+circled\s+once|"
    r"circled\s+once\s+in\s+(?:green|red|blue)|"
    r"rate\s+(?:figure\s+)?circled|"
    r"paper(?:work)?\s+with\s+(?:a\s+)?(?:red\s+)?(?:circle|stamp|seal)|"
    r"(?:red|orange)\s+(?:circle|stamp|ring)\s+on\s+(?:a\s+)?(?:paper|bill|document|invoice|sheet)|"
    r"(?:water\s+)?bill\s+with\s+(?:a\s+)?(?:red\s+)?(?:circle|stamp|highlight)|"
    r"document\s+with\s+(?:a\s+)?(?:circular\s+)?(?:seal|stamp|emblem)|"
    r"scene\s+prop\s+paperwork\s+may\s+show[^.]*"
    r")\b\.?"
)

_BAN_CIRCLED_PAPER_FIX = (
    " PROP BAN (mandatory): do NOT include any paper, bill, invoice, notepad, or phone screen "
    "with a red/orange circle, stamp, seal, ring mark, or highlighted amount. "
    "No decorative paperwork props with round marks. Tell the story with the real niche object "
    "and the person's expression — not a circled document."
)


def _is_finance_rate_niche(*, industry: str = "", niche: str = "", text: str = "") -> bool:
    hay = f"{industry} {niche} {text}".lower()
    # Trade niches never get finance circled-paper props even if "rate" appears in CTA copy.
    if any(
        k in hay
        for k in (
            "artificial turf", "air con", "hvac", "roof", "dental", "plumb",
            "landscap", "skylight", "turf", "split system",
        )
    ):
        return False
    return any(
        k in hay
        for k in (
            "mortgage", "home loan", "refinance", "broker", "lending",
            "interest rate", "bank rate", "loan rate", "financial services",
        )
    )


def enforce_no_spurious_circled_paper_prop(
    prompt: str,
    *,
    industry: str = "",
    niche: str = "",
) -> str:
    """
    Stop the model habit of putting a white paper + red circle in every ad.

    Circled rate-on-paper is ONLY for mortgage/finance rate stories.
    """
    text = (prompt or "").strip()
    if not text:
        return text
    if _is_finance_rate_niche(industry=industry, niche=niche, text=text):
        return text

    cleaned = _CIRCLED_PAPER_PROP_RE.sub(" ", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    if "PROP BAN (mandatory): do NOT include any paper" in cleaned:
        return cleaned
    return f"{cleaned} {_BAN_CIRCLED_PAPER_FIX}"


_B2B_CREW_COPY_RE = re.compile(
    r"(?i)\b("
    r"your\s+crews?|booked\s+crews?|idle\s+crews?|keep\s+(?:all\s+)?(?:teams|crews)\s+working|"
    r"qualified\s+(?:ac\s+)?(?:installation\s+)?(?:leads?|calls?)\s+to\s+crews?|"
    r"leads?\s+for\s+(?:brisbane[- ]based\s+)?crews?|"
    r"hipages|tyre[- ]?kicker\s+leads?|phone\s+ringing\s+with\s+good\s+jobs|"
    r"newimage[- ]?connected\s+crews?|busiest\s+air\s+conditioning\s+crews"
    r")\b"
)


def enforce_end_customer_audience_copy(
    text: str,
    *,
    brand_name: str,
    industry: str,
    niche: str,
    field: str = "hook",
) -> str:
    """
    When the brand IS the trade installer, rewrite B2B 'crews/leads' language
    into homeowner-facing copy so on-image lines stay related and believable.
    """
    out = (text or "").strip()
    if not out:
        return out
    if not _brand_is_trade_service_provider(brand_name=brand_name, industry=industry, niche=niche):
        return out
    if not _B2B_CREW_COPY_RE.search(out):
        return out

    niche_l = (niche or industry or "air conditioning").strip()
    # Field-aware soft rewrites that stay related to HVAC install lead gen for homeowners.
    if field in {"image_hook", "hook"}:
        return "AC packing it in this summer?"
    if field in {"image_headline", "message"}:
        return f"Get a local {niche_l} quote"
    if field == "offer":
        return (
            f"Book a free quote for {niche_l.lower()}. Local installers, clear pricing, "
            f"no lock-in — enquire today."
        )
    return out


def enforce_realistic_prop_text_in_prompt(
    prompt: str,
    *,
    brand_inputs: str = "",
    industry: str = "",
    niche: str = "",
) -> str:
    """
    Stop fake 'rate on laptop lid' and duplicated % props that look AI-generated.

    - Strip / rewrite device-exterior label language.
    - Allow at most one specific rate in the scene description when brand_inputs whitelist it.
    - If no verified rate in brand_inputs, ban specific % props entirely.
    - Circled-rate-on-paper language only for mortgage/finance niches.
    """
    text = (prompt or "").strip()
    if not text:
        return text
    if "PROP REALISM FIX" in text or "RATE PROP FIX" in text:
        return text

    whitelist = (brand_inputs or "").lower()
    rates_in_prompt = _RATE_PCT_RE.findall(text)
    has_device_rate = bool(_LAPTOP_RATE_RE.search(text) or _FAKE_DEVICE_LABEL_RE.search(text))
    finance = _is_finance_rate_niche(industry=industry, niche=niche, text=text)

    # Drop phrases that put rates on laptop exteriors.
    cleaned = _FAKE_DEVICE_LABEL_RE.sub(" ", text)
    cleaned = re.sub(
        r"(?is)\b(?:rate|interest\s+rate)\s*(?:of\s*)?\d{1,2}\.\d{1,2}\s*%\s*"
        r"(?:printed|stamped|written)?\s*(?:on|across)\s+(?:the\s+)?"
        r"(?:laptop|lid|back|chassis|screen bezel)[^.]*\.?",
        " ",
        cleaned,
    )
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()

    verified_rates = _RATE_PCT_RE.findall(whitelist)
    # Collapse many rate mentions: keep language soft if unverified.
    if rates_in_prompt and not verified_rates:
        # Remove concrete % from scene body (before TEXT-ANCHOR) so model doesn't stamp them.
        body, sep, tail = cleaned.partition(_ANCHOR_SENTINEL)
        body = _RATE_PCT_RE.sub("a competitive rate", body)
        cleaned = f"{body}{sep}{tail}".strip() if sep else body
        if finance:
            return f"{cleaned} {_NO_INVENTED_RATE_FIX}"
        return cleaned

    if finance and (has_device_rate or len(rates_in_prompt) >= 2):
        return f"{cleaned} {_REALISTIC_PROP_FIX}"

    # Even a single rate: remind one-prop-only if mortgage-ish paperwork language is dense.
    if finance and rates_in_prompt and re.search(r"(?i)\b(laptop|notepad|sticky\s*note|post-?it)\b", cleaned):
        return f"{cleaned} {_REALISTIC_PROP_FIX}"

    return cleaned


def enforce_on_image_copy_in_prompt(
    prompt: str,
    *,
    image_hook: str,
    image_headline: str,
    cta: str = "",
    full_hook: str = "",
    full_headline: str = "",
    industry: str = "",
    niche: str = "",
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

    finance = _is_finance_rate_niche(
        industry=industry, niche=niche, text=f"{cleaned} {full_hook} {full_headline}"
    )
    # NEVER tell every niche "circled rate on paper" — models turn that into a red-stamp sheet everywhere.
    if finance:
        prop_rule = (
            " Scene prop paperwork may show at most ONE blurred or single circled rate figure "
            "on paper — never duplicated, never on a laptop lid."
        )
    else:
        prop_rule = (
            " Do NOT add paper, bills, invoices, or phone screens with red/orange circles, stamps, "
            "seals, or highlighted amounts — no decorative circled-document props."
        )

    # TEXT-ANCHOR sentinel stays so idempotency check works on re-runs,
    # but the visual scene now comes FIRST so the model builds the scene before
    # processing text overlay rules — better scene fidelity with fewer artefacts.
    text_rules = (
        f" {_ANCHOR_SENTINEL} TEXT on this image ONLY: upper-third {parts[0]}"
        + (f", centre {parts[1]}" if len(parts) > 1 else "")
        + (cta_desc if button else "")
        + " No other text, slogans, signs, labels, or rate stickers anywhere — including laptop lids, "
        "device backs, calculators, sticky notes, and background posters."
        + f" ON-IMAGE COPY (final authority): render EXACTLY — {copy_list}."
        + (" CTA must look like a pill button with background colour, not plain text." if button else "")
        + " Discard any other marketing words."
        + prop_rule
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


# Meta-instruction labels written by post-processors (angle fixers, niche proof, etc.)
# that must be stripped from the visual body BEFORE the prompt reaches the image model.
# The TEXT-ANCHOR block is kept because it carries on-image copy the model must render.
_PROMPT_META_LABEL_RE = re.compile(
    r"(?is)\b("
    r"BEFORE\/AFTER\s+FIX\s*\([^)]+\)|"
    r"BEFORE\/AFTER\s+FIX\s*:|"
    r"PAIN-LED\s+FIX\s*\([^)]+\)|"
    r"PAIN-LED\s+FIX\s*:|"
    r"ANGLE\s+(?:LOGIC\s+|DIVERSITY\s+)?FIX\s*\([^)]+\)|"
    r"ANGLE\s+FIX\s*\([^)]+\)|"
    r"ANGLE\s+DIVERSITY\s*\([^)]+\):|"
    r"NICHE\s+PROOF\s*\([^)]+\)|"
    r"PAS\s*\+\s*HVAC\s+FIX\s*\([^)]*\)|"
    r"PAS\s+VISUAL\s+FIX\s*\([^)]*\)|"
    r"VISUAL\s+STORY\s*\([^)]+\)|"
    r"VISUAL\s+STORY\s+\(non-negotiable\)\s*:|"
    r"ROOFING\s+BEFORE\/AFTER\s+RULE[^.]*\.|"
    r"PROP\s+REALISM\s+FIX\s*\([^)]*\)|"
    r"RATE\s+PROP\s+FIX\s*\([^)]*\)|"
    r"DIFFERENT\s+SETTING\s+REQUIRED[^.]*\.|"
    r"INDUSTRY\s+SETTING\s+CHECK[^.]*\."
    r")"
    r"[^.]*?(?=(?:[A-Z]{2}[A-Z]+\s*[:(]|\Z|\.(?:\s+[A-Z]|\s*$)))",
)

_PROMPT_VISUAL_STORY_TAIL = re.compile(
    r"(?is)\s*VISUAL\s+STORY\s*\(non-negotiable\)\s*:\s*before\s+any\s+text\s+is\s+read.*$"
)

# Strips LLM-generated angle-name labels that image models read as literal directions.
# e.g. "This is a PAIN-LED transformation moment" → removed from scene body.
_PROMPT_INLINE_ANGLE_LABEL_RE = re.compile(
    r"(?i)\bThis\s+is\s+a\s+(?:PAIN[-\s]LED|BEFORE[-/\s]AFTER|PAS|SOCIAL[-\s]PROOF|"
    r"TESTIMONIAL|FOUNDER[-\s]LED|EDUCATIONAL|MYTH[-\s]BUSTING|CURIOSITY[-\s]HOOK|"
    r"FEAR[-\s]LOSS|FOMO|SCARCITY|CONTRARIAN|OFFER[-\s]URGENCY|URGENCY|TRUST[-\s]BUILDER)"
    r"[^.]{0,80}(?:moment|scene|angle|ad|creative|shot|frame)?[.—–\-]*\s*"
    r"(?:—\s*the\s+hero[^.]*\.|)?",
    re.IGNORECASE,
)

# Also strip orphaned phrase fragments left after meta-label removal.
_PROMPT_ORPHAN_FRAGMENT_RE = re.compile(
    r"(?:"
    r"hero\s*\(~?\d+%\+?\s+of\s+the\s+frame\)[^.]*?(?:real\s+world|outcome|cue)[^.]*\.?\s*|"
    r"person\s+experiencing\s+the\s+result\s+in\s+the\s+niche\s+real\s+world\s*\.?\s*|"
    r"show\s+the\s+ACTUAL\s+\w+[^.]*?as\s+a\s+hero\s+cue\s*\.?\s*|"
    r"show\s+ONE\s+present-time\s+improved\s+outcome\s*\.?\s*|"
    r"~?\d+%\+?\s+of\s+the\s+frame[^.]*\.\s*|"
    r"(?:^|(?<=\.\s))\s*\.\s*"
    r")",
    re.IGNORECASE,
)


def _strip_prompt_meta_labels(prompt: str) -> str:
    """
    Remove planning/enforcement meta-labels AND inline angle-name references from the prompt.

    These are written either by post-processors or by the LLM itself (e.g. "This is a
    PAIN-LED transformation moment") and must never reach the image model as literal scene
    instructions. The TEXT-ANCHOR block is preserved because it carries on-image copy.
    """
    text = (prompt or "").strip()
    if not text:
        return text
    # Split at TEXT-ANCHOR sentinel — preserve it and everything after.
    sentinel = "TEXT-ANCHOR:"
    if sentinel in text:
        body, _, anchor = text.partition(sentinel)
    else:
        body, anchor = text, ""

    # 1. Strip structured meta-label blocks (BEFORE/AFTER FIX, NICHE PROOF, etc.)
    body = _PROMPT_META_LABEL_RE.sub(" ", body)
    # 2. Strip trailing VISUAL STORY tail.
    body = _PROMPT_VISUAL_STORY_TAIL.sub(" ", body)
    # 3. Strip inline "This is a PAIN-LED transformation moment — the hero is …" phrases.
    body = _PROMPT_INLINE_ANGLE_LABEL_RE.sub(" ", body)
    # 4. Strip any orphaned fragments left by the above.
    body = _PROMPT_ORPHAN_FRAGMENT_RE.sub(" ", body)
    # 5. Collapse repeated whitespace and clean up stray punctuation.
    body = re.sub(r"\s{2,}", " ", body)
    # Remove doubled/orphaned dots and em-dashes at sentence start.
    body = re.sub(r"\.{2,}", ".", body)
    body = re.sub(r"(?<=[.!?])\s+[.—–]\s+", " ", body)
    # Remove stray sentence-initial em-dashes / bullets.
    body = re.sub(r"(?:^|\.\s+)[—–]\s+", ". ", body)
    body = body.strip(" .—–")

    if anchor:
        return f"{body} {sentinel}{anchor}".strip()
    return body


def _clamp_prompt(prompt: str, max_len: int = 4000) -> str:
    prompt = _strip_prompt_meta_labels((prompt or "").strip())
    if len(prompt) > max_len:
        return prompt[: max_len - 1] + "…"
    return prompt


def _valid_use_cases(ids: list[Any]) -> list[str]:
    return [uc for uc in (ids or []) if isinstance(uc, str) and uc in _USE_CASE_DESCRIPTIONS] or list(
        _SELECTOR_FALLBACK_USE_CASES
    )


def _derive_industry_bucket(
    *,
    campaign_name: str,
    industry: str,
    niche: str = "",
    icp_text: str = "",
) -> str:
    """Map brand industry + niche + campaign + ICP to a scene pool key."""
    ind = (industry or "").lower().strip()

    # Agency / digital marketing brand → visuals about ads, leads, targeting (the service sold).
    if ind in _AGENCY_BRAND_INDUSTRIES or "digital_marketing" in ind:
        return "digital_marketing"

    # Product / client brands: infer vertical from campaign + niche + ICP text.
    haystack = f"{campaign_name} {niche} {icp_text}".lower()

    # Niche category wins when specific (HVAC, dental implants, etc.).
    niche_cat = _resolve_niche_category(niche=niche, industry=industry)
    if niche_cat == "hvac":
        return "hvac"
    if niche_cat == "roofing":
        return "roofing"
    if niche_cat == "landscaping":
        return "landscaping"
    if niche_cat == "jewellery":
        return "jewellery"
    if niche_cat == "home_improvement":
        return "home_improvement"
    if niche_cat in {
        "root_canal", "dental_implants", "whitening", "orthodontics", "acute_dental_pain",
    }:
        return "dental"

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

    if any(kw in f"{ind} {haystack}" for kw in _INDUSTRY_KEYWORDS.get("hvac", ())):
        return "hvac"
    if any(kw in f"{ind} {haystack}" for kw in _INDUSTRY_KEYWORDS.get("dental", ())):
        return "dental"
    if "retail" in ind or ind == "dtc":
        return "ecommerce" if "dtc" in ind else "retail"
    if "local" in ind or "construction" in ind or "trade" in ind:
        return "trade"
    if "saas" in ind:
        return "pro_services"
    return "general"


def _pick_scene_mandates(
    *,
    count: int,
    campaign_name: str,
    industry: str,
    niche: str = "",
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
        niche=niche,
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
    geography: str = "",
    brand_facts: dict | None = None,
) -> str:
    """Build ICP from industry + niche + objective + brand (end-customer focused)."""
    industry_label = (industry or "").strip() or campaign_name
    niche_label = (niche or "").strip()
    objective_label = (objective_id or "conversions").strip()
    service_location = _normalize_service_location(geography) or (geography or "").strip()
    facts_block = format_brand_facts_for_llm(brand_facts)

    if not settings.OPENROUTER_API_KEY:
        hay = f"{industry_label} {niche_label} {campaign_name}".lower()
        trade_hit = any(
            kw in hay
            for kw in (
                "trade", "tradie", "plumb", "electric", "hvac", "builder",
                "local", "construction", "hipages", "roof",
            )
        )
        pro_hit = any(
            kw in hay
            for kw in ("professional", "pro services", "account", "advisory", "consult", "legal")
        )
        loc_bit = service_location or "their Australian service area"
        # Brand IS the trade business → homeowner ICP (not Shane selling-to-crews).
        if trade_hit and _brand_is_trade_service_provider(
            brand_name=brand_name, industry=industry_label, niche=niche_label
        ):
            niche_bit = niche_label or "trade service"
            return (
                f'AVATAR NAME: Jordan Blake — "The Hot-Home Homeowner"\n'
                f"IDENTITY: Homeowner or property manager in {loc_bit} who needs {niche_bit}. "
                f"Brand they should enquire with: {brand_name or 'the local trade business'}.\n"
                f"CURRENT REALITY: Home is uncomfortable (heat, broken unit, or urgent repair); "
                f"comparing local installers and wanting a clear quote without cowboy risk "
                f"(objective: {objective_label}).\n"
                f"CORE PAIN: Unreliable quotes, slow call-backs, and fear of choosing the wrong tradie.\n"
                f"DESIRED OUTCOME: A trusted local crew books the job and gets the home comfortable fast.\n"
                f'KEY OBJECTION: "Will they actually show up — and is the price fair?"\n'
                f"BUYING TRIGGER: A sleepless hot night, a unit that dies, or guests arriving.\n"
                f'LANGUAGE THEY USE: "Can you install this week?" | "How much for a split system?" | '
                f'"Are you local?" | "Do you give a fixed quote?"'
            )
        if trade_hit and _brand_sells_marketing_to_trades(
            brand_name=brand_name, industry=industry_label, niche=niche_label
        ):
            return (
                'AVATAR NAME: Shane Callahan — "The Multi-Crew Builder"\n'
                f"IDENTITY: Owner-operator of a multi-crew plumbing / trade business serving {loc_bit} "
                "(~AUD $4M+, 20+ staff). Decision maker on marketing spend; office manager is day-to-day contact.\n"
                "CURRENT REALITY: Paying for Google Ads and Hipages but still feast-or-famine lead flow; "
                "can't tell tyre-kickers from commercial jobs; competitor winning Google Maps.\n"
                "CORE PAIN: Paying for leads that don't keep crews booked — and distrust of agencies that talk jargon.\n"
                "DESIRED OUTCOME: Phone ringing with qualified commercial + residential jobs; Hipages dependency gone.\n"
                'KEY OBJECTION: "I already have an agency — prove they\'re wasting my money before I switch."\n'
                "BUYING TRIGGER: Quiet week with idle crews, or a strata contract lost to a competitor found on Google.\n"
                'LANGUAGE THEY USE: "I need the phone to ring with good jobs" | "I\'m sick of Hipages" | '
                '"Just tell me straight — is my current agency doing a good job?"'
            )
        if trade_hit:
            # Ambiguous trade industry without clear brand signal — still default to end customer.
            niche_bit = niche_label or "the service"
            return (
                f'AVATAR NAME: Jordan Blake — "The Ready Homeowner"\n'
                f"IDENTITY: Australian homeowner in {loc_bit} evaluating {niche_bit}. "
                f"Brand: {brand_name or 'local trade business'}.\n"
                f"CURRENT REALITY: Needs the job done soon; comparing local options "
                f"(objective: {objective_label}).\n"
                f"CORE PAIN: Uncertainty and wasted time on slow or unclear quotes.\n"
                f"DESIRED OUTCOME: A clear quote and a booked install/repair.\n"
                f'KEY OBJECTION: "Is this the right local crew?"\n'
                f"BUYING TRIGGER: Discomfort or urgency at home becomes obvious.\n"
                f'LANGUAGE THEY USE: "How soon can you come?" | "What will it cost?" | "Are you nearby?"'
            )
        if pro_hit:
            return (
                'AVATAR NAME: Trust Builder — "The Managing Partner"\n'
                f"IDENTITY: Managing partner at a mid-tier Australian professional services firm serving {loc_bit}; "
                "controls marketing spend and partner alignment.\n"
                "CURRENT REALITY: Referrals drying up; competitors stronger on SEO and Google Ads; "
                "worried about non-compliant or salesy marketing.\n"
                "CORE PAIN: Need partner-ready proof of ROI without creating compliance risk.\n"
                "DESIRED OUTCOME: Clear pipeline and a marketing system the coordinator can run.\n"
                'KEY OBJECTION: "Will partners buy this — and is it compliant?"\n'
                "BUYING TRIGGER: A competitor wins a client through digital visibility.\n"
                'LANGUAGE THEY USE: "Show me the ROI" | "Keep it compliant" | "Can our coordinator run this?"'
            )
        buyer_focus = (
            "Australian home buyer / refinancer comparing brokers"
            if "mortgage" in industry_label.lower() or "broker" in industry_label.lower()
            else f"Australian buyer evaluating {industry_label}"
        )
        return (
            f'AVATAR NAME: Target Buyer — "The Ready-to-Act Prospect"\n'
            f"IDENTITY: {buyer_focus}. Brand: {brand_name or 'local business'}. "
            f"Industry: {industry_label}. Niche: {niche_label or 'general'}. "
            f"Service area: {loc_bit}.\n"
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
        f"SERVICE LOCATION (authoritative geography for this campaign): {service_location or 'Not specified — do NOT invent Western Sydney, Brisbane, Melbourne, or any other city'}",
        "",
        *( [facts_block, ""] if facts_block else [] ),
        "Remember: ICP = person who sees the ad and takes the objective action "
        "(usually the brand's end customer). Do not invent B2B-to-peers copy unless niche clearly says so.",
        *(
            [
                "AUDIENCE LOCK: Brand is the TRADE INSTALLER — ICP must be a homeowner/property manager "
                "who needs the niche service. Do NOT use Multi-Crew Builder / Shane / Hipages / 'crews' ICP.",
            ]
            if _brand_is_trade_service_provider(
                brand_name=brand_name, industry=industry_label, niche=niche_label
            )
            else []
        ),
        "LOCATION RULE: Place the avatar in the SERVICE LOCATION above. "
        "Reference archetype cities (Western Sydney, Blacktown, Brisbane, Melbourne) are EXAMPLES ONLY — never copy them if they differ from SERVICE LOCATION.",
        "FACT RULE: If VERIFIED BRAND FACTS are provided, ground the ICP's reality in those real services, areas, and offers. Never invent rates, review counts, or years of experience that are not listed.",
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
    ind = (industry or "").lower()
    # Local trade / landscaping / home services — never SaaS waitlist CTAs.
    if any(
        k in ind
        for k in (
            "trade", "hvac", "plumb", "electric", "roof", "landscap", "garden",
            "construction", "local", "home improvement",
        )
    ):
        return _home_service_cta_pool(industry=industry, niche=industry, cta_hint=hint)

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
        "Book Free Quote",
        "Request Strategy Call",
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
    niche: str = "",
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
        niche=niche,
    )

    for i in range(variant_count):
        scene = mandates[i % len(mandates)]
        niche_word = (industry or campaign_name or "leads").split()[0][:18]
        hook = f"Your best {niche_word} results are slipping away to competitors who package the whole offer"
        if hook in existing_hooks:
            hook = f"Still chasing cold {niche_word} while bigger players win the relationship?"
        message = f"{brand} helps you keep clients with a clearer, integrated next step this week"
        image_hook, image_headline = _related_image_lines(
            hook,
            message,
            ad_angle=(angle_assignments[i] if angle_assignments and i < len(angle_assignments) else ""),
            niche=niche,
        )
        cta_text = cta_options[i % len(cta_options)]
        offer = (
            f"{offer_base}. "
            f"You get clarity without the guesswork, so you can act with confidence — claim the next step now."
        )
        prompt = enforce_niche_visual_proof_in_prompt(
            enforce_no_spurious_circled_paper_prop(
                enforce_on_image_copy_in_prompt(
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
                    industry=industry,
                    niche=niche,
                ),
                industry=industry,
                niche=niche,
            ),
            niche=niche,
            industry=industry,
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
    geography: str = "",
    brand_facts: dict | None = None,
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
    industry_label = (industry or "").strip() or campaign_name
    niche_label = (niche or "").strip()
    angle_assignments = assign_angles_to_variants(
        frameworks,
        count,
        objective_id,
        industry=industry_label,
        niche=niche_label,
        campaign_name=campaign_name,
    )
    service_location = (geography or "").strip()
    facts_block = format_brand_facts_for_llm(brand_facts)
    facts_whitelist = brand_facts_whitelist_text(brand_facts)
    # Business rule: if user didn't pick a location, fall back to scraped service area.
    if not service_location and isinstance(brand_facts, dict):
        areas = [str(a).strip() for a in (brand_facts.get("service_areas") or []) if str(a).strip()]
        locs = [str(a).strip() for a in (brand_facts.get("locations") or []) if str(a).strip()]
        service_location = ", ".join((areas or locs)[:3])
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
        geography=service_location,
        brand_facts=brand_facts,
    )

    scene_mandates = _pick_scene_mandates(
        count=count,
        campaign_name=campaign_name,
        industry=industry_label,
        niche=niche_label,
        icp_text=icp_text,
        avoid_snippets=prompts_avoid,
        hook_frameworks=frameworks,
    )

    niche_visual_mandate = _build_niche_visual_mandate(
        niche=niche_label,
        industry=industry_label,
    )

    if not settings.OPENROUTER_API_KEY:
        variants = _fallback_variants(
            campaign_name=campaign_name,
            brand_name=brand_name,
            industry=industry_label,
            niche=niche_label,
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
    offer_for_model = offer
    if _is_jewellery_niche(niche=niche_label, industry=industry_label) and _FURNITURE_HOME_DRIFT_RE.search(
        offer or ""
    ):
        offer_for_model = enforce_niche_product_focus_copy(
            offer or "", niche=niche_label, industry=industry_label, field="offer"
        )
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
        f"6. SERVICE LOCATION (authoritative — use ONLY this for any place name in copy/prompt): "
        f"{service_location or 'Not set — do NOT invent Western Sydney, Brisbane, Melbourne, or any other city on-image'}",
        *( [_state_climate_hint(service_location), ""] if _state_climate_hint(service_location) else [] ),
        *(
            [
                "AUDIENCE LOCK (critical): This brand is the TRADE INSTALLER. "
                "Every hook, headline, image_hook, image_headline, offer, and prompt must speak to "
                "HOMEOWNERS / property managers who need the niche service — NEVER to other crews, "
                "Hipages buyers, or 'booked crews know the system' B2B lead-gen pitches.",
                "",
            ]
            if _brand_is_trade_service_provider(
                brand_name=brand_name, industry=industry_label, niche=niche_label
            )
            else []
        ),
        *( [facts_block, ""] if facts_block else [
            "VERIFIED BRAND FACTS: none provided — do NOT invent rates, review counts, customer volumes, or years of experience.",
            "",
        ] ),
        "",
        f"CREATIVE FORMAT: {'carousel (swipe story)' if is_carousel else 'static (standalone ads)'}",
        f"CAMPAIGN LABEL: {campaign_name}",
        f"SCENE POOL: {_derive_industry_bucket(campaign_name=campaign_name, industry=industry_label, niche=niche_label, icp_text=icp_text)}",
        f"CTA HINT (optional shared guidance — still invent a distinct CTA per variant): {cta or 'none — invent action CTAs from campaign + ICP'}",
        f"OFFER HINT (caption only — do NOT put in image): {offer_for_model or 'infer from ICP and campaign'}",
        f"ASPECT RATIO: {image_aspect_ratio}",
        f"VARIANT / CARD COUNT: {count}",
        "",
        *( [niche_visual_mandate, ""] if niche_visual_mandate else [] ),
        "LOCATION RULE (critical): If SERVICE LOCATION is set, any local claim in hook / image_hook / "
        "image_headline / offer / prompt MUST use that exact area. NEVER copy Western Sydney, Blacktown, "
        "Brisbane, Melbourne, or other archetype cities from the ICP reference. If SERVICE LOCATION is "
        "blank, omit specific suburb/city names from on-image text entirely.",
        "STEP 1 — for each variant, first derive the campaign intent (audience, problem, action, emotion, single_message) from the inputs above and the ICP.",
        "STEP 2 — design the visual and the copy TOGETHER so the image alone communicates 70-80% of the single_message and the on-image text reinforces the rest.",
        "STEP 3 — run the STRANGER TEST on every scene: with all text removed, a stranger must answer BOTH 'what is this ad about?' (a clear category cue from the industry/niche must be visible in the frame — e.g. a house for home loans) AND 'what is being promised?' (the benefit must be provable on camera). Never drop the category object from the scene, and never show ONLY the category without the promise.",
        f"STEP 3b — MANDATORY on EVERY variant, no exceptions: ground the setting in the {industry_label or 'this'} industry's own world (its typical location, tools, or objects) so a viewer instantly recognises the industry from the background alone, even before reading the on-image text. A plain office desk / blank laptop / neutral room with zero industry cues is a FAILED variant — fix it by adding a real object or location from this industry into the frame.",
        "STEP 3c — Tiny text on laptop/notepad/phone screens does NOT count as niche proof. The stranger must recognise the niche from LARGE physical objects (AC unit, pipes, switchboard, dental x-ray, etc.).",
        "STEP 3d — PROP REALISM: never print rates/prices on a laptop lid or device exterior. "
        "For mortgage/finance ONLY: at most ONE rate figure on one paper sheet (optionally circled). "
        "For all other niches: NEVER add papers/bills with red circles, stamps, or highlighted amounts.",
        "",
        "CONTEXT RULES:",
        "- Write for the ICP (end customer who takes the objective action).",
        "- If brand is a mortgage/finance broker and objective is conversions/purchase/lead_generation: speak to home buyers / refinancers — NOT other brokers.",
        "- If brand is a Trade Services / HVAC / Heating & Cooling / plumbing installer (e.g. Newimage Heating & Cooling) "
        "and niche is Air Conditioning Installation: speak to HOMEOWNERS who need install/repair — "
        "NOT other AC crews. Forbidden: 'your crews', 'booked crews', 'qualified leads for crews', Hipages-to-tradie pitches.",
        "- If niche is roofing / roof restoration / skylight: before_after means SIDE-BY-SIDE "
        "LEFT dark/leak/stain concern | RIGHT bright restored skylight/roof + relieved homeowner "
        "(dental results style) — not after-only certificate portrait. A warranty certificate can support "
        "the story but cannot replace visible roof/skylight proof.",
        "- BEFORE/AFTER (universal — any industry): dental-results SIDE-BY-SIDE required — "
        "LEFT before/problem + concerned face | RIGHT after/result + confident smile. "
        "BANNED: after-only lifestyle shot; tiny far-background before whisper.",
        "- On-image hook + headline MUST be clearly related to the post hook/headline AND speak to the same audience "
        "(homeowner pain → homeowner on-image line). Catchy is good; wrong-audience catchy is a fail.",
        "- BRAND FACTS RULE: Specific rates, review scores, customer counts, years in business, and named services "
        "may ONLY come from VERIFIED BRAND FACTS. If missing, use soft copy (competitive rates, local homeowners, etc.).",
        "- Match the visual to services listed in VERIFIED BRAND FACTS when present — BUT if NICHE names a "
        "product category (e.g. Jewellery), sell ONLY that niche. Ignore other brand-kit categories "
        "(furniture, outdoor goods, home décor) for this campaign's copy and prompts.",
        "- Niche informs the offer angle; do not invent a different business model (installer ≠ lead-gen SaaS).",
        (
            "JEWELLERY NICHE LOCK (critical): Niche is Jewellery. Every hook, headline, image_hook, "
            "image_headline, offer, CTA story, and prompt must be about jewellery (necklace, rings, "
            "earrings, bracelet, gift unboxing). BANNED: furniture, sofas, outdoor goods, home refresh, "
            "home décor collections — even if brand facts mention them."
            if _is_jewellery_niche(niche=niche_label, industry=industry_label)
            else ""
        ),
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
        "AUSTRALIAN ENGLISH (every industry): catchy Aussie billboard voice — not flat US corporate. "
        "Spelling: organise/colour/centre. Prefer Ring us / Book free quote over Call Now / Learn More when it fits.",
        "ON-IMAGE must match the assigned ad angle + niche: social_proof = peers/families proof (NOT credentials fluff); "
        "problem_agitate_solve = problem question on image_hook + solve on image_headline; "
        "artificial turf = talk turf/lawn patches — never generic 'proven landscapers / real credentials'.",
        "Burn ONLY image_hook + image_headline + CTA into the prompt — never the full hook/message/offer.",
        "ANGLE MEANING IS UNIVERSAL: before_after, pain_led, PAS, social_proof, testimonial, urgency, etc. "
        "must work the same way in any industry. First obey the angle semantics, then prove the niche with that "
        "industry's physical objects and setting. Do NOT turn angle logic into industry-specific trust fluff.",
        "Each variant needs its own action CTA on the image button — do not default every variant to Learn More.",
        "If pattern_interrupt is selected, every prompt must feel like a stop-the-scroll Pattern Interrupt — not stock photography.",
        "The prompt must describe a scene that SHOWS the single_message (problem, transformation, or outcome) — never a pretty background for text. No generic stock-photo scenes (smiling person at laptop, handshake, team huddle) unless they carry real story props.",
        "EXPRESSIONS: pain-led = discomfort only; before_after = LEFT concerned + RIGHT confident smile in a "
        "side-by-side comparison (dental results style). Other angles = one emotion only.",
        "ANGLE UNIQUENESS: each variant's image prompt must be obviously different from the others — different room, different primary action, different hero prop. Do NOT reuse the same kitchen + apple + jaw-hold combo across angles.",
        f"INDUSTRY SETTING CHECK (apply to EVERY variant, not just some): before finalising each prompt, confirm the background/location/props visibly belong to the {industry_label or 'campaign'} industry AND the {niche_label or 'campaign'} niche. If a variant's setting could belong to ANY industry (plain desk, blank laptop, neutral room), add a real object or location from this niche's world before writing the final prompt.",
        (
            "PAIN-LED ANGLE RULE: when pain_led is assigned, the pain must be LITERAL and NICHE-SPECIFIC — "
            "show the exact physical/situational pain for this treatment (e.g. root canal = jaw wince + x-ray + "
            "cold sensitivity), not generic sadness or work stress. NO solution smile in the pain-led frame."
            if "pain_led" in angle_assignments
            else ""
        ),
        (
            "PROBLEM-AGITATE-SOLVE RULE: when problem_agitate_solve is assigned, ONE frame must show "
            "PROBLEM props + AGITATE cues + SOLVE arriving. On-image: image_hook = problem/agitate "
            "(not trust fluff); image_headline = the solve. "
            "BANNED: calm person reading a clean quote with only a tiny niche object in the far background — "
            "that is solve-only, not PAS."
            if "problem_agitate_solve" in angle_assignments
            else ""
        ),
        (
            "BEFORE/AFTER ANGLE RULE (universal — match dental results ads): SIDE-BY-SIDE comparison REQUIRED. "
            "LEFT HALF = BEFORE (problem props + concerned expression). "
            "RIGHT HALF = AFTER (transformed result + confident smile). Same person/place. "
            "Landscaping example: left overgrown weeds/frustrated homeowner | right lush garden/smiling homeowner. "
            "BANNED: after-only lifestyle paradise; tiny far-background before whisper; social-proof peer huddle."
            if "before_after" in angle_assignments
            else ""
        ),
        (
            "HVAC / AIR-CON RULE (every angle): each prompt MUST include a physical indoor split-system "
            "head unit OR outdoor condenser/compressor as a HERO/midground prop (not a tiny window speck). "
            "BANNED: laptop quote spreadsheets alone; happy families + service vans with no AC equipment visible."
            if _resolve_niche_category(niche=niche_label, industry=industry_label) == "hvac"
            else ""
        ),
        "Return ONLY the JSON object. Do not add markdown commentary, headings, or explanation after the closing brace.",
    ])

    fallback_reason = "template fallback"
    try:
        client = _get_openrouter_client()
        model = (
            # Prefer stronger models for creative variant planning — Haiku is too weak here.
            settings.OPENROUTER_MODEL_CLAUDE_SCRIPT
            or settings.OPENROUTER_MODEL_VISION
            or settings.OPENROUTER_MODEL_OPENAI
            or settings.OPENROUTER_MODEL_CLAUDE
        )
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
                assigned_angle = (
                    angle_assignments[i]
                    if angle_assignments and i < len(angle_assignments)
                    else str(item.get("ad_angle") or "").strip()
                )
                image_hook = _billboard_words(str(item.get("image_hook") or ""), 6)
                image_headline = _billboard_words(str(item.get("image_headline") or ""), 8)
                if not image_hook or not image_headline:
                    derived_h, derived_m = _related_image_lines(
                        hook, message, ad_angle=assigned_angle, niche=niche_label
                    )
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
                # Installer / landscaper brands shouldn't use SaaS CTAs like "Request a Demo" / "Join the List".
                if _brand_is_trade_service_provider(
                    brand_name=brand_name, industry=industry_label, niche=niche_label
                ) and re.search(
                    r"(?i)\b(demo|trial|start\s+free|book\s+a\s+demo|join\s+the\s+list|join\s+waitlist)\b",
                    cta_line,
                ):
                    cta_line = "Book Free Quote"
                used_ctas.add(cta_line.lower())
                offer_line = str(item.get("offer") or offer or cta or "").strip()
                prompt = _clamp_prompt(str(item.get("prompt") or ""))
                if not hook or not message or not prompt:
                    continue
                # Service area from brief — never burn Western Sydney/Brisbane from ICP archetypes.
                hook = enforce_service_location_in_text(hook, geography=service_location)
                message = enforce_service_location_in_text(message, geography=service_location)
                image_hook = enforce_service_location_in_text(image_hook, geography=service_location)
                image_headline = enforce_service_location_in_text(
                    image_headline, geography=service_location
                )
                offer_line = enforce_service_location_in_text(offer_line, geography=service_location)
                prompt = enforce_service_location_in_text(prompt, geography=service_location)
                # ACCC compliance — strip unverifiable stats, invented rates, fake social proof.
                # Whitelist figures that appear in the offer OR scraped brand facts.
                _brand_src = str(offer or "") + " " + facts_whitelist
                hook = enforce_accc_compliance(hook, brand_inputs=_brand_src)
                message = enforce_accc_compliance(message, brand_inputs=_brand_src)
                image_hook = enforce_accc_compliance(image_hook, brand_inputs=_brand_src)
                image_headline = enforce_accc_compliance(image_headline, brand_inputs=_brand_src)
                offer_line = enforce_accc_compliance(offer_line, brand_inputs=_brand_src)
                # Australian English — every industry (spelling + flat US CTA swaps).
                hook = enforce_australian_english_copy(hook)
                message = enforce_australian_english_copy(message)
                image_hook = enforce_australian_english_copy(image_hook)
                image_headline = enforce_australian_english_copy(image_headline)
                offer_line = enforce_australian_english_copy(offer_line)
                cta_line = enforce_australian_english_copy(cta_line)
                # Niche product lock — jewellery niche must not drift into furniture/home décor.
                hook = enforce_niche_product_focus_copy(
                    hook, niche=niche_label, industry=industry_label, field="hook"
                )
                message = enforce_niche_product_focus_copy(
                    message, niche=niche_label, industry=industry_label, field="message"
                )
                image_hook = enforce_niche_product_focus_copy(
                    image_hook, niche=niche_label, industry=industry_label, field="image_hook"
                )
                image_headline = enforce_niche_product_focus_copy(
                    image_headline, niche=niche_label, industry=industry_label, field="image_headline"
                )
                offer_line = enforce_niche_product_focus_copy(
                    offer_line, niche=niche_label, industry=industry_label, field="offer"
                )
                cta_line = enforce_niche_product_focus_copy(
                    cta_line, niche=niche_label, industry=industry_label, field="cta"
                )
                if _is_jewellery_niche(niche=niche_label, industry=industry_label) and (
                    _FURNITURE_HOME_DRIFT_RE.search(str(item.get("hook") or ""))
                    or _FURNITURE_HOME_DRIFT_RE.search(str(item.get("message") or ""))
                    or _FURNITURE_HOME_DRIFT_RE.search(str(item.get("image_hook") or ""))
                    or _FURNITURE_HOME_DRIFT_RE.search(str(item.get("image_headline") or ""))
                ):
                    derived_h, derived_m = _related_image_lines(
                        hook, message, ad_angle=assigned_angle, niche=niche_label
                    )
                    image_hook = derived_h or image_hook
                    image_headline = derived_m or image_headline
                    image_hook = _billboard_words(image_hook, 7)
                    image_headline = _billboard_words(image_headline, 8)
                # Trade installer brands → homeowner copy (never "your crews / leads for crews").
                hook = enforce_end_customer_audience_copy(
                    hook, brand_name=brand_name, industry=industry_label, niche=niche_label, field="hook"
                )
                message = enforce_end_customer_audience_copy(
                    message, brand_name=brand_name, industry=industry_label, niche=niche_label, field="message"
                )
                image_hook = enforce_end_customer_audience_copy(
                    image_hook, brand_name=brand_name, industry=industry_label, niche=niche_label, field="image_hook"
                )
                image_headline = enforce_end_customer_audience_copy(
                    image_headline, brand_name=brand_name, industry=industry_label, niche=niche_label, field="image_headline"
                )
                offer_line = enforce_end_customer_audience_copy(
                    offer_line, brand_name=brand_name, industry=industry_label, niche=niche_label, field="offer"
                )
                # If we rewrote hooks for audience, keep on-image lines related.
                if _brand_is_trade_service_provider(
                    brand_name=brand_name, industry=industry_label, niche=niche_label
                ):
                    derived_h, derived_m = _related_image_lines(
                        hook, message, ad_angle=assigned_angle, niche=niche_label
                    )
                    if _B2B_CREW_COPY_RE.search(str(item.get("image_hook") or "")):
                        image_hook = derived_h or image_hook
                    if _B2B_CREW_COPY_RE.search(str(item.get("image_headline") or "")):
                        image_headline = derived_m or image_headline
                    image_hook = _billboard_words(image_hook, 7)
                    image_headline = _billboard_words(image_headline, 8)
                # On-image hook + headline must match each other AND the post copy / angle.
                image_hook, image_headline = enforce_on_image_story_match(
                    image_hook=image_hook,
                    image_headline=image_headline,
                    hook=hook,
                    message=message,
                    ad_angle=assigned_angle,
                    industry=industry_label,
                    niche=niche_label,
                )
                image_hook = enforce_australian_english_copy(image_hook)
                image_headline = enforce_australian_english_copy(image_headline)
                # CTA must match the on-image story (no "Join the List" on a landscaping trust ad).
                used_ctas.discard(cta_line.lower())
                cta_line = enforce_cta_copy_coherence(
                    cta=cta_line,
                    image_hook=image_hook,
                    image_headline=image_headline,
                    hook=hook,
                    message=message,
                    ad_angle=assigned_angle,
                    brand_name=brand_name,
                    industry=industry_label,
                    niche=niche_label,
                    used_ctas=used_ctas,
                    cta_hint=cta,
                )
                cta_line = enforce_australian_english_copy(cta_line)
                used_ctas.add(cta_line.lower())
                # Angle meaning must hold across any industry; niche proof comes after.
                prompt = enforce_generic_angle_logic_in_prompt(
                    prompt,
                    ad_angle=assigned_angle,
                    niche=niche_label,
                    industry=industry_label,
                )
                # Niche proof only if missing — never paste the same fixed scene onto every angle.
                prompt = enforce_niche_visual_proof_in_prompt(
                    prompt,
                    niche=niche_label,
                    industry=industry_label,
                    ad_angle=assigned_angle,
                )
                prompt = enforce_niche_product_focus_in_prompt(
                    prompt,
                    niche=niche_label,
                    industry=industry_label,
                )
                # Stop fake "rate on laptop lid" and duplicated % props.
                prompt = enforce_realistic_prop_text_in_prompt(
                    prompt,
                    brand_inputs=_brand_src,
                    industry=industry_label,
                    niche=niche_label,
                )
                prompt = enforce_angle_scene_diversity(
                    prompt,
                    ad_angle=assigned_angle,
                    prior_prompts=[v.prompt for v in variants],
                    variant_index=i,
                    niche=niche_label,
                    industry=industry_label,
                )
                prompt = enforce_pas_angle_in_prompt(
                    prompt,
                    ad_angle=assigned_angle,
                    niche=niche_label,
                    industry=industry_label,
                )
                # Pin EXACT on-image lines into the prompt (strip any inventted slogans).
                prompt = enforce_on_image_copy_in_prompt(
                    prompt,
                    image_hook=image_hook,
                    image_headline=image_headline,
                    cta=cta_line,
                    full_hook=hook,
                    full_headline=message,
                    industry=industry_label,
                    niche=niche_label,
                )
                prompt = enforce_no_spurious_circled_paper_prop(
                    prompt,
                    industry=industry_label,
                    niche=niche_label,
                )
                intent = item.get("intent") if isinstance(item.get("intent"), dict) else {}
                single_message = str((intent or {}).get("single_message") or "").strip()
                # single_message goes into reasoning only — NOT appended to the image prompt.
                # Appending it to the prompt body causes the image model to read planning labels
                # like "PAIN-LED transformation moment" as literal scene directions.
                reasoning_line = str(item.get("reasoning") or "").strip()
                if single_message and single_message.lower() not in reasoning_line.lower():
                    reasoning_line = (
                        f"Single message: {single_message}" + (f" — {reasoning_line}" if reasoning_line else "")
                    )
                # Final clean pass: strip planning meta labels.
                prompt = _strip_prompt_meta_labels(prompt)
                # Re-apply before/after AFTER strip — dental-style comparison must reach the image model.
                if (assigned_angle or "").strip().lower() == "before_after":
                    prompt = _inject_before_after_comparison_before_anchor(
                        prompt, niche=niche_label, industry=industry_label
                    )
                # Keep circled-paper ban after strip (must reach the image model).
                prompt = enforce_no_spurious_circled_paper_prop(
                    prompt,
                    industry=industry_label,
                    niche=niche_label,
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
                        ad_angle=assigned_angle,
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
                        niche=niche_label,
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
        niche=niche_label,
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
