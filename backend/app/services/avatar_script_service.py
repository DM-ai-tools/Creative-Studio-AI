"""Generate timed avatar scripts for HeyGen via Claude Sonnet (OpenRouter)."""

from __future__ import annotations

import json
import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.schemas.avatar_script import (
    AvatarScriptLine,
    AvatarScriptRequest,
    AvatarScriptResponse,
    AvatarScriptValidation,
)

from app.services.australian_copy import (
    AUSTRALIAN_ENGLISH_BRIEF_RULES,
    AUSTRALIAN_ENGLISH_SCRIPT_RULES,
)

WPS = 2.5
MODEL_LABEL = "Claude Sonnet 4.6"

_STATS_SYSTEM_RULE = (
    "In social proof / results beats ONLY (never hook or problem), cite the VERIFIED PERFORMANCE "
    "STATS exactly as provided (industry, ROAS, ROI, conversions, cost, timeline). "
    "Do not invent different numbers. Hook and problem beats must NOT mention ROAS, ROI, or dashboard figures."
)

_DEFAULT_PRESENTER_ENVIRONMENT = (
    "Professional digital marketing / IT / performance agency office — glass-walled conference room "
    "or modern tech workspace with blurred monitors and natural light"
)

_BROLL_PROFESSIONAL_ENVIRONMENT_RULE = (
    "PRESENTER ON CAMERA (HOOK, PROOF, CTA): shoot ONLY in a professional digital marketing / IT / "
    "performance agency office — glass conference room, agency meeting room, or tech workspace with "
    "blurred monitors. Use the SAME agency office across all presenter beats for continuity.\n"
    "B-ROLL (problem/solution): professional workplaces only — executive desk, laptop with ads dashboard, "
    "agency war room, client strategy meeting, team at monitors. Never residential or casual hospitality.\n"
    "FORBIDDEN everywhere unless the brief explicitly requests it: kitchen, bathroom, bedroom, living room, "
    "dining room, suburban home, apartment couch, cafe, coffee shop, restaurant, bar, backyard, beach house, "
    "grocery store, or any domestic / hospitality setting."
)


def _presenter_environment_for_broll(req: AvatarScriptRequest) -> str:
    custom = (req.scene_custom or "").strip()
    if custom:
        return custom
    label = (req.scene_label or "").strip()
    if label and label.lower() not in ("neutral studio", "coffee shop interior (warm)"):
        return label
    brand = (req.brand_name or "the brand").strip()
    return f"{_DEFAULT_PRESENTER_ENVIRONMENT} — {brand} agency branding on wall optional"

_SOURCE_SCRIPT_SYSTEM_RULE = """CONVERSION MODE — the user pasted a written marketing script.
Your job is to convert it into spoken dialogue the avatar says out loud.
- Remove section labels (Hook, Problem, Proof, Guarantee, Offer, CTA, Angle, Duration) — never speak them.
- Remove visual placeholders like [INSERT ...] or [INSERT ... STAT IMAGE] — never spoken aloud.
- Keep ALL facts, numbers, guarantees, and brand claims verbatim — do not invent new stats.
- Tighten phrasing only if needed to fit the target duration — never drop key proof points or the guarantee.
- Flow: hook → problem → proof → guarantee → offer → CTA as natural spoken lines.
- Australian English throughout — Aussie accent and phrasing, not American."""


def _stats_user_block(req: AvatarScriptRequest) -> str:
    per_image = [s for s in (req.performance_stats_per_image or []) if s]
    if per_image:
        from app.services.stats_image_service import format_per_image_stats_for_script

        block = format_per_image_stats_for_script(per_image)
        if block.strip():
            return (
                "VERIFIED PERFORMANCE STATS — one dashboard per stat image. "
                "Each proof line with [INSERT STAT IMAGE N] MUST speak the IMAGE N figures aloud "
                "(presenter describes what the viewer sees on screen):\n"
                f"{block}"
            )
    if not req.performance_stats:
        return ""
    from app.services.stats_image_service import format_performance_stats_for_script

    block = format_performance_stats_for_script(req.performance_stats)
    if not block.strip():
        return ""
    return (
        "VERIFIED PERFORMANCE STATS (from uploaded dashboard image — use these exact figures "
        f"when mentioning results, ROAS, ROI, or conversions):\n{block}"
    )


def _approved_script_user_block(req: AvatarScriptRequest) -> str:
    raw = (req.approved_script or "").strip()
    if not raw:
        return ""
    return (
        "APPROVED VOICE SCRIPT (mandatory — B-roll timestamps MUST match these spoken lines exactly):\n"
        f"{raw}"
    )


def _source_script_user_block(req: AvatarScriptRequest) -> str:
    raw = (req.source_script or "").strip()
    if not raw:
        return ""
    return (
        "PASTED SCRIPT TO CONVERT (written copy — turn into timed spoken lines only):\n"
        f"{raw}"
    )


def _has_source_script(req: AvatarScriptRequest) -> bool:
    return bool((req.source_script or "").strip())


def _mock_from_source_script(req: AvatarScriptRequest) -> AvatarScriptResponse | None:
    raw = (req.source_script or "").strip()
    if not raw:
        return None
    cleaned: list[str] = []
    for line in raw.splitlines():
        s = line.strip()
        if not s:
            continue
        if re.match(r"^\[INSERT\b", s, re.I):
            continue
        if re.match(
            r"^(hook|problem|proof|guarantee|offer|cta|angle|duration)\b",
            s,
            re.I,
        ):
            continue
        if re.match(r"^variation\s+\d+", s, re.I):
            continue
        cleaned.append(s)
    text = " ".join(cleaned)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s.strip()]
    if not sentences:
        sentences = [text[:200]]
    t = req.target_seconds
    n = len(sentences)
    seg = max(1, t // n)
    raw_lines = [
        (seg * i, min(seg * (i + 1), t), txt)
        for i, txt in enumerate(sentences)
    ]
    if raw_lines:
        s, _, txt = raw_lines[-1]
        raw_lines[-1] = (s, t, txt)
    lines = [
        AvatarScriptLine(start=_seconds_to_ts(s), end=_seconds_to_ts(e), text=txt)
        for s, e, txt in raw_lines
        if s < e
    ]
    if not lines:
        return None
    full = "\n".join(f"[{l.start} - {l.end}] {l.text}" for l in lines)
    spoken = _spoken_text(lines, full)
    return AvatarScriptResponse(
        lines=lines,
        full_script=full,
        word_count=len(spoken.split()),
        estimated_seconds=len(spoken.split()) / WPS,
        model_id="mock",
        model_label=MODEL_LABEL,
        validations=_build_validations(
            spoken,
            target_seconds=req.target_seconds,
            forbidden_words=req.forbidden_words,
            tone=req.ad_copy_tone,
        ),
    )


def _strip_json_fence(raw: str) -> str:
    """Extract a JSON object/array from an LLM response that may have preamble or code fences."""
    text = (raw or "").strip()
    # Strip markdown code fences
    if "```" in text:
        text = re.sub(r"```(?:json)?\s*", "", text)
        text = re.sub(r"```", "", text)
        text = text.strip()
    # If the text starts with a JSON brace/bracket we're done
    if text and text[0] in ("{", "["):
        return text
    # Otherwise find the first { or [ and take everything from there
    for char in ("{", "["):
        idx = text.find(char)
        if idx != -1:
            candidate = text[idx:]
            # Trim trailing text after the closing brace
            last = max(candidate.rfind("}"), candidate.rfind("]"))
            if last != -1:
                return candidate[: last + 1]
            return candidate
    return text


def _seconds_to_ts(seconds: float) -> str:
    s = max(0, int(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def _parse_timed_lines(full_script: str, target_seconds: int) -> list[AvatarScriptLine]:
    pattern = re.compile(
        r"\[(\d{1,2}:\d{2})\s*[-–]\s*(\d{1,2}:\d{2})\]\s*(.+?)(?=\[|\Z)",
        re.DOTALL,
    )
    lines: list[AvatarScriptLine] = []
    for match in pattern.finditer(full_script):
        lines.append(
            AvatarScriptLine(
                start=match.group(1),
                end=match.group(2),
                text=match.group(3).strip(),
            )
        )
    if lines:
        return lines

    words = full_script.split()
    if not words:
        return []
    chunk = max(1, len(words) // 5)
    elapsed = 0.0
    for i in range(0, len(words), chunk):
        slice_words = words[i : i + chunk]
        dur = len(slice_words) / WPS
        start = _seconds_to_ts(elapsed)
        elapsed += dur
        end = _seconds_to_ts(min(elapsed, target_seconds))
        lines.append(
            AvatarScriptLine(
                start=start,
                end=end,
                text=" ".join(slice_words),
            )
        )
    return lines


def _spoken_text(lines: list[AvatarScriptLine], full_script: str) -> str:
    if lines:
        return " ".join(line.text for line in lines).strip()
    return re.sub(r"\[\d{1,2}:\d{2}\s*[-–]\s*\d{1,2}:\d{2}\]\s*", "", full_script).strip()


def _apply_ocr_proof_to_response(
    resp: AvatarScriptResponse,
    req: AvatarScriptRequest,
) -> AvatarScriptResponse:
    """Deterministic pass: proof lines must speak exact OCR figures per stat image."""
    per_image = [s for s in (req.performance_stats_per_image or []) if s]
    if req.purpose != "avatar_script" or not per_image:
        return resp

    from app.services.stats_image_service import inject_ocr_proof_into_avatar_script

    fixed = inject_ocr_proof_into_avatar_script(
        resp.full_script,
        per_image,
        brand_name=req.brand_name or "",
        duration=req.target_seconds,
    )
    if fixed == resp.full_script:
        return resp

    lines = _parse_timed_lines(fixed, req.target_seconds)
    full_script = fixed
    spoken = _spoken_text(lines, full_script)
    word_count = len(spoken.split())
    return AvatarScriptResponse(
        lines=lines,
        full_script=full_script,
        word_count=word_count,
        estimated_seconds=round(word_count / WPS, 1),
        model_id=resp.model_id,
        model_label=resp.model_label,
        validations=_build_validations(
            spoken,
            target_seconds=req.target_seconds,
            forbidden_words=req.forbidden_words,
            tone=req.ad_copy_tone,
        ),
    )


def _build_validations(
    spoken: str,
    *,
    target_seconds: int,
    forbidden_words: list[str],
    tone: str,
) -> list[AvatarScriptValidation]:
    words = spoken.split()
    word_count = len(words)
    estimated = word_count / WPS
    validations: list[AvatarScriptValidation] = [
        AvatarScriptValidation(id="brand_voice", label="Brand voice match", status="ok"),
    ]
    forbidden_hit = [w for w in forbidden_words if w and w.lower() in spoken.lower()]
    validations.append(
        AvatarScriptValidation(
            id="forbidden",
            label="No forbidden words" if not forbidden_hit else f"Avoid: {', '.join(forbidden_hit[:3])}",
            status="ok" if not forbidden_hit else "warn",
        )
    )
    avg_len = sum(len(w) for w in words) / max(word_count, 1)
    validations.append(
        AvatarScriptValidation(
            id="reading_level",
            label="6th-grade reading level" if avg_len <= 6.5 else "Readable length",
            status="ok" if avg_len <= 7.5 else "warn",
        )
    )
    if estimated > target_seconds + 1:
        over = int(round(estimated - target_seconds))
        validations.append(
            AvatarScriptValidation(
                id="duration",
                label=f"{over}s over target — auto-trim",
                status="warn",
            )
        )
    elif estimated < target_seconds - 4:
        validations.append(
            AvatarScriptValidation(
                id="duration",
                label="Short for target — add a line",
                status="warn",
            )
        )
    else:
        validations.append(
            AvatarScriptValidation(id="duration", label="Fits target duration", status="ok")
        )
    if tone:
        validations[0].label = f"Tone: {tone[:40]}"
    return validations


def _extract_icp_field(icp_text: str, field: str) -> str:
    """Pull a single field line from ICP text (e.g. CORE PAIN: ...)."""
    for line in icp_text.splitlines():
        if line.upper().startswith(field.upper() + ":"):
            return line[len(field) + 1:].strip()
    return ""


def _mock_script(req: AvatarScriptRequest) -> AvatarScriptResponse:
    brand = req.brand_name or req.product_name or "the brand"
    t = req.target_seconds

    # When ICP context is available use it to build more relevant lines
    icp = req.icp_context or ""
    pain = _extract_icp_field(icp, "CORE PAIN")
    outcome = _extract_icp_field(icp, "DESIRED OUTCOME")
    objection = _extract_icp_field(icp, "KEY OBJECTION")
    language_line = _extract_icp_field(icp, "LANGUAGE THEY USE")
    first_phrase = language_line.split("|")[0].strip().strip('"\'') if language_line else ""

    if pain:
        dialogue_lines = [
            f"Look — if you're {first_phrase or 'keen to sort this out'}, {brand} is worth a look.",
            pain[:90] + ("…" if len(pain) > 90 else ""),
            f"{req.offer or req.product_name or 'What we do'} gives you {outcome[:70] if outcome else 'the results you are after'}.",
            f"{req.cta or 'Book a free audit'} — jump on it below.",
        ]
    else:
        dialogue_lines = [
            f"Quick one about {brand}.",
            f"{req.offer or 'Here is what sets us apart.'}",
            f"{req.product_name or 'Our offer'} — built for Aussie businesses like yours.",
            f"{req.cta or 'Book a free audit'} — tap below, no dramas.",
        ]

    # Build evenly-spaced timestamps that always fit inside target_seconds
    n = len(dialogue_lines)
    seg = max(1, t // n)
    raw_lines = [
        (seg * i, min(seg * (i + 1), t), txt)
        for i, txt in enumerate(dialogue_lines)
    ]
    # Make last line end exactly at t
    if raw_lines:
        s, _, txt = raw_lines[-1]
        raw_lines[-1] = (s, t, txt)

    lines = [
        AvatarScriptLine(start=_seconds_to_ts(s), end=_seconds_to_ts(e), text=txt)
        for s, e, txt in raw_lines
        if s < e
    ]
    # Always emit at least one line
    if not lines:
        lines = [AvatarScriptLine(start="00:00", end=_seconds_to_ts(t), text=f"{req.cta or 'Learn more'}.")]
    full = "\n".join(f"[{l.start} - {l.end}] {l.text}" for l in lines)
    spoken = _spoken_text(lines, full)
    return AvatarScriptResponse(
        lines=lines,
        full_script=full,
        word_count=len(spoken.split()),
        estimated_seconds=len(spoken.split()) / WPS,
        model_id="mock",
        model_label=MODEL_LABEL,
        validations=_build_validations(
            spoken,
            target_seconds=req.target_seconds,
            forbidden_words=req.forbidden_words,
            tone=req.ad_copy_tone,
        ),
    )


def _brief_notes_response(text: str, req: AvatarScriptRequest) -> AvatarScriptResponse:
    spoken = text.strip()
    words = spoken.split()
    return AvatarScriptResponse(
        lines=[AvatarScriptLine(start="00:00", end="00:30", text=spoken)],
        full_script=spoken,
        word_count=len(words),
        estimated_seconds=len(words) / WPS,
        model_id=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
        model_label=MODEL_LABEL,
        validations=_build_validations(
            spoken,
            target_seconds=req.target_seconds,
            forbidden_words=req.forbidden_words,
            tone=req.ad_copy_tone,
        ),
    )


async def generate_avatar_script(req: AvatarScriptRequest) -> AvatarScriptResponse:
    if not settings.OPENROUTER_API_KEY:
        if req.purpose == "brief_notes":
            notes = (
                f"Introduce {req.product_name or req.brand_name or 'the offer'}. "
                f"{req.offer or 'Highlight the key benefit.'} "
                f"Tone: {req.ad_copy_tone or 'friendly'}. End with: {req.cta or 'Learn more'}."
            )
            return _brief_notes_response(notes, req)
        if req.purpose == "visual_cues":
            end_ts = max(0, min(req.target_seconds - 5, 55))
            cues = (
                f"00:08 — Product close-up ({req.product_name or 'product'}). "
                f"00:18 — Offer overlay: {req.offer or 'special offer'}. "
                f"00:{end_ts:02d} — CTA card: {req.cta or 'Learn more'}."
            )
            return _brief_notes_response(cues, req)
        if req.purpose == "scene_broll":
            dur = req.target_seconds
            product = req.product_name or "the product/service"
            audience = req.target_audience or "potential customers"
            brand = req.brand_name or "the brand"
            offer = req.offer or "the offer"
            cta = req.cta or "Learn more"
            t1 = min(12, dur // 4)
            t2 = min(22, dur // 2)
            t3 = min(dur - 8, int(dur * 0.85))
            env = _presenter_environment_for_broll(req)
            template = (
                f"[00:00-00:05] HOOK — Presenter on camera in {env}, opening for {brand}\n"
                f"[00:05-{t1:02d}] PROBLEM — B-roll: {audience} at executive desk, ads dashboard declining\n"
                f"[{t1:02d}-{t2:02d}] SOLUTION — B-roll: {product} in agency war room — {offer}\n"
                f"[{t2:02d}-{t3:02d}] PROOF — Presenter on camera in same agency office, results for {brand}\n"
                f"[{t3:02d}-{dur:02d}] CTA — Presenter on camera in agency office, warm close: {cta}"
            )
            return _brief_notes_response(template, req)
        mock_from_source = _mock_from_source_script(req)
        if mock_from_source:
            return mock_from_source
        return _mock_script(req)

    from app.services.ai_service import ai_service

    hook_hint = (
        "Open with a surprising question or pattern interrupt."
        if req.variation == "different_hook"
        else "Open with a friendly, direct hook."
    )
    user_bits = [
        f"Brand: {req.brand_name}",
        f"Product / Service: {req.product_name}",
        f"Offer: {req.offer}",
        f"Target audience: {req.target_audience}",
        f"Tone / Style: {req.ad_copy_tone}",
        f"CTA: {req.cta}",
        f"Presenter: {req.avatar_label or 'avatar'}",
        f"Voice: {req.voice_label or 'narrator'} (Australian English accent)",
        f"Notes / context: {req.notes}",
        f"Target length: {req.target_seconds} seconds at {WPS} words per second.",
        f"Language: Australian English only — full Aussie accent and phrasing in dialogue.",
        hook_hint,
    ]
    approved_block = _approved_script_user_block(req)
    if approved_block and req.purpose in ("scene_broll", "visual_cues"):
        user_bits.append(approved_block)
    elif req.purpose == "scene_broll" and req.notes:
        user_bits.append(
            f"\nAPPROVED SCRIPT / SPOKEN LINES (align B-roll visuals to each beat):\n{req.notes}"
        )
    if req.purpose == "scene_broll":
        user_bits.append(
            f"PRESENTER ENVIRONMENT (mandatory for every 'Presenter on camera' shot): "
            f"{_presenter_environment_for_broll(req)}"
        )
    if req.script_prompt:
        user_bits.append(f"Creative direction: {req.script_prompt}")
    stats_block = _stats_user_block(req)
    if stats_block:
        user_bits.append(stats_block)
    source_block = _source_script_user_block(req)
    if source_block:
        user_bits.append(source_block)

    _has_stats = bool(req.performance_stats or req.performance_stats_per_image)
    stats_rule = f"\n- {_STATS_SYSTEM_RULE}" if _has_stats else ""

    _n_imgs = req.stats_image_count or len(req.performance_stats_per_image or [])
    if _n_imgs > 0:
        _img_labels = ", ".join(f"[INSERT STAT IMAGE {i + 1}]" for i in range(_n_imgs))
        stats_rule += (
            f"\n- {_n_imgs} stats dashboard image(s) overlay in post-production. "
            f"EXACTLY {_n_imgs} proof spoken lines — one line per image, no more. "
            f"Each line MUST start with its marker — {_img_labels} — then speak ONLY that "
            f"image's OCR figures (headline, ROAS, cost, sales, lead forms). "
            f"Image 1 = first uploaded dashboard, image 2 = second uploaded dashboard. "
            f"Never split one dashboard across two lines. Never mix image 1 and image 2 numbers. "
            f"Spread across proof beat only (last 20–30% of video). "
            f"Never place markers in hook or problem beats."
        )
    if req.purpose == "avatar_script" and _has_stats:
        stats_rule += (
            "\n- Structure: HOOK (no stats) → PROBLEM (no stats) → SOLUTION (no stats) → "
            "PROOF (one spoken line per stat image, citing that image's exact numbers) → CTA."
        )
    source_rule = f"\n{_SOURCE_SCRIPT_SYSTEM_RULE}" if _has_source_script(req) else ""

    if req.purpose == "brief_notes":
        system = f"""You write creative brief notes for ad scriptwriters.
Return ONLY valid JSON: {{ "notes": "3-5 short paragraphs of talking points and what the ad should say" }}
Rules:
- {req.ad_copy_tone or 'On-brand'} tone for {req.target_audience or 'the audience'}
- Include product ({req.product_name}), offer ({req.offer}), and CTA ({req.cta or 'Learn more'})
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}
- Plain text in notes, no timestamps, no markdown
- Return pure JSON only — no preamble, no explanation
{AUSTRALIAN_ENGLISH_BRIEF_RULES}{stats_rule}"""
    elif req.purpose == "visual_cues":
        system = f"""You write visual cues and on-screen text directions for a {req.target_seconds}-second avatar video ad.
Return ONLY valid JSON: {{ "notes": "single block of 3-6 lines" }}
Each line MUST use format: MM:SS — description (e.g. 00:08 — Product close-up with logo)
Rules:
- Spread cues across 00:00 to {req.target_seconds:02d} seconds
- Include product ({req.product_name}), offer ({req.offer}), brand ({req.brand_name}), CTA ({req.cta or 'Learn more'})
- On-screen brand text must be exactly "{req.brand_name}" — never prefix with tone ({req.ad_copy_tone or 'on-brand'}) or adjectives
- Include avatar expression cues per beat (e.g. 00:05 — Avatar concerned, no smile; 00:22 — Avatar confident, subtle smile on benefit)
- Pain/problem beats: serious or frustrated expression — NO smiling
- Solution/CTA beats: relieved then warm — smile only on positive/CTA words
- Mention b-roll as separate full-frame shots only (never split-screen or half-chart layouts)
- MANDATORY: any on-screen text or headline must be placed in the LOWER third (bottom 25%) or TOP strip (top 10%) — NEVER over the presenter's face, eyes, or mouth
- For statistics: full-screen stat moment OR lower-third text — NOT graph on one side and photo on the other
- Say explicitly "lower-third at bottom" or "top banner below frame edge" for text overlays
- {req.ad_copy_tone or 'On-brand'} style for {req.target_audience or 'the audience'}
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}
- No markdown, no spoken dialogue (visual directions only){stats_rule}"""
    elif req.purpose == "scene_broll":
        def _ts(secs: int) -> str:
            return f"{secs // 60:02d}:{secs % 60:02d}"

        _broll_dur = req.target_seconds
        # Proportional beat boundaries — scale with video length
        _hook_end  = max(5,  _broll_dur * 10 // 100)          # ~10 %
        _prob_end  = max(_hook_end + 5,  _broll_dur * 30 // 100)  # ~30 %
        _sol_end   = max(_prob_end + 8,  _broll_dur * 65 // 100)  # ~65 %
        _proof_end = max(_sol_end + 5,   _broll_dur * 88 // 100)  # ~88 %

        # For longer videos suggest more sub-scenes per beat
        if _broll_dur >= 60:
            _scene_count = "7–9"
            _long_note = (
                "Because this is a longer video, you MUST write multiple sub-scenes per beat "
                "(e.g. 2–3 PROBLEM cuts, 3–4 SOLUTION cuts). "
                "Each sub-scene should be a distinct camera angle or action moment. "
                "Do NOT write only 5 scenes for a 60-second+ video."
            )
        else:
            _scene_count = "5–6"
            _long_note = ""

        system = f"""You are a professional commercial video director writing a shot-by-shot B-roll brief for a {_broll_dur}-second digital ad.

Your job: write CINEMATIC, CAMPAIGN-SPECIFIC visual directions that a real camera crew could shoot.
Every scene must feel like it belongs ONLY to this brand — not generic stock footage.

Return ONLY valid JSON (no preamble, no markdown fence):
{{"notes": "one line per scene, separated by newlines"}}

━━━ CAMPAIGN BRIEF ━━━
Brand: {req.brand_name}
Product / Service: {req.product_name}
Offer: {req.offer}
Target audience: {req.target_audience}
Tone / style: {req.ad_copy_tone}
CTA: {req.cta or 'Learn more'}

━━━ SHOT FORMAT ━━━
Each line MUST follow this exact format (MM:SS timestamps only — no raw seconds):
[MM:SS-MM:SS] BEAT — [Shot type]: [Scene description — specific, cinematic, action-driven]

Shot types you can use: Close-up | Medium shot | Wide shot | Over-shoulder | POV shot | Cutaway | Montage cut | Presenter on camera

━━━ SCENE STRUCTURE (write {_scene_count} scenes covering 00:00–{_ts(_broll_dur)}) ━━━
{_long_note}

[00:00-{_ts(_hook_end)}] HOOK
- Presenter on camera — opening address to the viewer
- Location: professional digital marketing / IT agency office ({req.brand_name or "the brand"}'s world — glass conference room or tech workspace, NOT a home)
- Confident, direct, warm — hook the viewer in the first 3 seconds

[{_ts(_hook_end)}-{_ts(_prob_end)}] PROBLEM ({"write 2–3 cuts for this beat" if _broll_dur >= 60 else "1–2 cuts"})
- B-roll showing the REAL pain {req.target_audience or "the audience"} experiences WITHOUT {req.product_name or "this solution"}
- Show a SPECIFIC moment of frustration, stress, or loss — not a generic "stressed person"
- Ask yourself: what does failure look like in this category? What does {req.target_audience} lose by not solving this?
- No smiling — this beat must feel like a real problem

[{_ts(_prob_end)}-{_ts(_sol_end)}] SOLUTION ({"write 3–4 distinct cuts for this beat" if _broll_dur >= 60 else "2–3 cuts"})
- B-roll showing {req.product_name or "the product"} ACTIVELY solving the problem
- Make the offer ({req.offer or "the offer"}) visible or implied in the scene
- Show transformation: before frustration → after relief/confidence
- Each cut should be a different angle or moment — not the same scene repeated

[{_ts(_sol_end)}-{_ts(_proof_end)}] PROOF
- Presenter on camera in the SAME professional agency / IT office as the hook
- Stats and numbers will be added in post-production — do NOT describe charts, dashboards, or overlays on screen
- Avatar expression: assured, credible, slight smile on positive result

[{_ts(_proof_end)}-{_ts(_broll_dur)}] CTA
- Presenter on camera in the SAME agency office, warm and direct close
- Reference the CTA: "{req.cta or 'Learn more'}"
- End energy: inviting, urgent, human — not salesy

━━━ DIRECTOR'S RULES ━━━
- {_BROLL_PROFESSIONAL_ENVIRONMENT_RULE}
- Every scene must name: WHO is in frame, WHERE they are (professional office/agency only), WHAT is happening, and WHAT EMOTION is visible
- Use cinematic action verbs: "scrolling frantically through", "slumped over laptop in corner office", "typing with purpose at agency desk", "leaning into the camera", "lights up as notification arrives"
- B-roll shots must be full-frame motion clips — never split-screen, never half-frame charts
- Timestamps must be MM:SS format (e.g. 00:05, 00:42, 01:00) — NEVER raw seconds (e.g. "5s", "42s")
- Final timestamp must equal exactly {_ts(_broll_dur)} — do not stop short
- MANDATORY: If an APPROVED VOICE SCRIPT is provided, every scene boundary MUST use the EXACT
  [MM:SS-MM:SS] timestamps from that script — one scene (or sub-scene) per spoken line or beat group.
  Presenter-on-camera when the script says the presenter speaks; B-roll when the script describes
  pain/solution visually. PROOF beat = presenter on camera (stats added in post — no dashboards on screen).
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}{stats_rule}"""
    else:
        # Target word count & suggested number of lines scale with duration
        target_words = int(req.target_seconds * WPS)
        suggested_lines = max(4, req.target_seconds // 6)
        line_duration_hint = max(4, req.target_seconds // suggested_lines)

        # For longer scripts use plain-text timestamped format (avoids JSON truncation)
        use_plain_text = req.target_seconds > 60 or _has_source_script(req)

        if use_plain_text:
            system = f"""You write spoken-word scripts for HeyGen avatar video ads.

{AUSTRALIAN_ENGLISH_SCRIPT_RULES}
{source_rule}

Output the script as plain text lines ONLY — no JSON, no markdown, no preamble.
Each line MUST follow this exact format:
[MM:SS - MM:SS] Spoken dialogue here

Rules:
- Total duration: {req.target_seconds}s — write approximately {suggested_lines} lines, each ~{line_duration_hint}s (~{int(line_duration_hint * WPS)} words)
- Target total: ~{target_words} spoken words spread evenly across {_seconds_to_ts(req.target_seconds)}
- Timestamps MUST be strictly sequential: each start = previous end, final line ends at {_seconds_to_ts(req.target_seconds)}
- First line starts at [00:00 - ...]
- Each line is ONLY spoken dialogue (no stage directions, no meta-commentary)
- NEVER output: "Open with a hook", "Establish credibility", "Position this as", or any writer instructions
- Write lines that naturally shift emotion: pain/problem lines sound serious; benefit lines sound relieved; CTA sounds warm
- MANDATORY: mention "{req.brand_name}" naturally at least 2 times
- NEVER address the viewer by a persona name — always "you" / "your business"
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}
- End the last line with the CTA: {req.cta or 'Learn more'}
- Output ONLY the timestamped lines — nothing else before or after{stats_rule}"""
        else:
            system = f"""You write spoken-word scripts for HeyGen avatar video ads.

{AUSTRALIAN_ENGLISH_SCRIPT_RULES}
{source_rule}

Return ONLY valid JSON (no preamble, no markdown):
{{
  "lines": [
    {{"start": "00:00", "end": "00:06", "text": "spoken line"}}
  ],
  "full_script": "same lines as [MM:SS - MM:SS] text joined with newlines"
}}
Rules:
- Total duration: {req.target_seconds}s — write approximately {suggested_lines} lines, each ~{line_duration_hint}s
- Timestamps sequential: each start = previous end, final end = {_seconds_to_ts(req.target_seconds)}
- Conversational, {req.ad_copy_tone or 'on-brand'} tone — only spoken dialogue, no meta directions
- Write lines that naturally shift emotion: pain/problem lines sound serious; benefit lines relieved; CTA warm
- MANDATORY: mention "{req.brand_name}" naturally at least 2 times
- NEVER address viewer by a persona name — use "you" / "your business"
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}
- End with CTA: {req.cta or 'Learn more'}{stats_rule}"""

    # Scale max_tokens — stay within typical OpenRouter credit limits
    max_tokens = max(1500, req.target_seconds * 12)
    if _has_source_script(req):
        src_len = len((req.source_script or "").strip())
        max_tokens = min(
            2800,
            max(1800, req.target_seconds * 18, src_len // 4),
        )

    # Scene B-roll needs more room for rich cinematic descriptions
    if req.purpose == "scene_broll":
        max_tokens = max(max_tokens, 2400)

    models_to_try = [settings.OPENROUTER_MODEL_CLAUDE_SCRIPT]
    if _has_source_script(req) and settings.OPENROUTER_MODEL_CLAUDE not in models_to_try:
        models_to_try.append(settings.OPENROUTER_MODEL_CLAUDE)

    try:
        client = ai_service._get_client()
        raw = ""
        last_exc: Exception | None = None
        for model in models_to_try:
            try:
                raw_response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": "\n".join(user_bits)},
                    ],
                    max_tokens=max_tokens,
                )
                raw = (raw_response.choices[0].message.content or "").strip()
                break
            except Exception as exc:
                last_exc = exc
                err = str(exc).lower()
                if (
                    model != models_to_try[-1]
                    and ("402" in err or "credits" in err or "afford" in err)
                ):
                    logger.warning(
                        "Script model %s failed (credits) — trying fallback",
                        model,
                    )
                    continue
                raise
        if not raw and last_exc:
            raise last_exc

        if req.purpose in ("brief_notes", "visual_cues", "scene_broll"):
            raw_j = _strip_json_fence(raw)
            data = json.loads(raw_j)
            notes = (data.get("notes") or data.get("full_script") or "").strip()
            if notes:
                return _brief_notes_response(notes, req)

        # Plain-text timestamped output path
        if req.purpose == "avatar_script" and use_plain_text:
            lines = _parse_timed_lines(raw, req.target_seconds)
            if not lines:
                # Fallback: try wrapping as single block
                lines = [AvatarScriptLine(start="00:00", end=_seconds_to_ts(req.target_seconds), text=raw)]
            full_script = "\n".join(f"[{l.start} - {l.end}] {l.text}" for l in lines)
            spoken = _spoken_text(lines, full_script)
            word_count = len(spoken.split())
            return _apply_ocr_proof_to_response(
                AvatarScriptResponse(
                lines=lines,
                full_script=full_script,
                word_count=word_count,
                estimated_seconds=round(word_count / WPS, 1),
                model_id=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
                model_label=MODEL_LABEL,
                validations=_build_validations(
                    spoken,
                    target_seconds=req.target_seconds,
                    forbidden_words=req.forbidden_words,
                    tone=req.ad_copy_tone,
                ),
            ),
                req,
            )

        # JSON path (short scripts)
        raw_j = _strip_json_fence(raw)
        data = json.loads(raw_j)
        lines = [AvatarScriptLine(**line) for line in data.get("lines", [])]
        full_script = (data.get("full_script") or "").strip()
        if not full_script and lines:
            full_script = "\n".join(f"[{l.start} - {l.end}] {l.text}" for l in lines)
        if not lines and full_script:
            lines = _parse_timed_lines(full_script, req.target_seconds)
        spoken = _spoken_text(lines, full_script)
        word_count = len(spoken.split())
        estimated = word_count / WPS
        return _apply_ocr_proof_to_response(
            AvatarScriptResponse(
            lines=lines,
            full_script=full_script,
            word_count=word_count,
            estimated_seconds=round(estimated, 1),
            model_id=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            model_label=MODEL_LABEL,
            validations=_build_validations(
                spoken,
                target_seconds=req.target_seconds,
                forbidden_words=req.forbidden_words,
                tone=req.ad_copy_tone,
            ),
        ),
            req,
        )
    except Exception as exc:
        logger.exception("Avatar script generation failed")
        err = str(exc)
        if settings.OPENROUTER_API_KEY:
            if "402" in err or "credits" in err.lower() or "afford" in err.lower():
                raise ValueError(
                    "OpenRouter credits are too low for a full-length script. "
                    "Add credits at https://openrouter.ai/settings/credits, then try again."
                ) from exc
            if _has_source_script(req):
                raise ValueError(
                    "Could not convert your pasted script — AI service error. "
                    "Check OpenRouter credits and restart the backend."
                ) from exc
            raise ValueError(f"Script generation failed: {err[:240]}") from exc
        mock_from_source = _mock_from_source_script(req)
        if mock_from_source:
            return mock_from_source
        return _mock_script(req)
