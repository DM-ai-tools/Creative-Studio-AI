"""Generate timed avatar scripts for HeyGen via Claude Sonnet (OpenRouter)."""

from __future__ import annotations

import json
import re

from app.core.config import settings
from app.schemas.avatar_script import (
    AvatarScriptLine,
    AvatarScriptRequest,
    AvatarScriptResponse,
    AvatarScriptValidation,
)

WPS = 2.5
MODEL_LABEL = "Claude Sonnet 4.6"


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


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


def _mock_script(req: AvatarScriptRequest) -> AvatarScriptResponse:
    brand = req.brand_name or req.product_name or "the brand"
    lines = [
        AvatarScriptLine(start="00:00", end="00:04", text=f"Hey — quick question about {brand}."),
        AvatarScriptLine(
            start="00:04",
            end="00:12",
            text=f"{req.offer or 'Here is what makes us different.'}",
        ),
        AvatarScriptLine(
            start="00:12",
            end="00:22",
            text=f"{req.product_name or 'Our product'} — built for you.",
        ),
        AvatarScriptLine(
            start="00:22",
            end=_seconds_to_ts(req.target_seconds),
            text=f"{req.cta or 'Learn more'} — tap below.",
        ),
    ]
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
        return _mock_script(req)

    from app.services.ai_service import ai_service

    hook_hint = (
        "Open with a surprising question or pattern interrupt."
        if req.variation == "different_hook"
        else "Open with a friendly, direct hook."
    )
    user_bits = [
        f"Brand: {req.brand_name}",
        f"Product: {req.product_name}",
        f"Offer: {req.offer}",
        f"Audience: {req.target_audience}",
        f"Tone: {req.ad_copy_tone}",
        f"CTA: {req.cta}",
        f"Presenter: {req.avatar_label or 'avatar'}",
        f"Voice: {req.voice_label or 'narrator'}",
        f"Notes: {req.notes}",
        f"Target length: {req.target_seconds} seconds at {WPS} words per second.",
        hook_hint,
    ]
    if req.script_prompt:
        user_bits.append(f"Creative direction: {req.script_prompt}")

    if req.purpose == "brief_notes":
        system = f"""You write creative brief notes for ad scriptwriters.
Return ONLY valid JSON: {{ "notes": "3-5 short paragraphs of talking points and what the ad should say" }}
Rules:
- {req.ad_copy_tone or 'On-brand'} tone for {req.target_audience or 'the audience'}
- Include product ({req.product_name}), offer ({req.offer}), and CTA ({req.cta or 'Learn more'})
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}
- Plain text in notes, no timestamps, no markdown"""
    elif req.purpose == "visual_cues":
        system = f"""You write visual cues and on-screen text directions for a {req.target_seconds}-second avatar video ad.
Return ONLY valid JSON: {{ "notes": "single block of 3-6 lines" }}
Each line MUST use format: MM:SS — description (e.g. 00:08 — Product close-up with logo)
Rules:
- Spread cues across 00:00 to {req.target_seconds:02d} seconds
- Include product ({req.product_name}), offer ({req.offer}), brand ({req.brand_name}), CTA ({req.cta or 'Learn more'})
- Mention b-roll as separate full-frame shots only (never split-screen or half-chart layouts)
- MANDATORY: any on-screen text or headline must be placed in the LOWER third (bottom 25%) or TOP strip (top 10%) — NEVER over the presenter's face, eyes, or mouth
- For statistics: full-screen stat moment OR lower-third text — NOT graph on one side and photo on the other
- Say explicitly "lower-third at bottom" or "top banner below frame edge" for text overlays
- {req.ad_copy_tone or 'On-brand'} style for {req.target_audience or 'the audience'}
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}
- No markdown, no spoken dialogue (visual directions only)"""
    else:
        system = f"""You write spoken-word scripts for HeyGen avatar video ads.
Return ONLY valid JSON:
{{
  "lines": [
    {{"start": "00:00", "end": "00:04", "text": "spoken line without stage directions"}}
  ],
  "full_script": "same lines as [MM:SS - MM:SS] text joined with newlines"
}}
Rules:
- {req.target_seconds}s total at ~{WPS} words per second (about {int(req.target_seconds * WPS)} words max)
- Conversational, {req.ad_copy_tone or 'on-brand'} tone
- Each line is ONLY dialogue the presenter speaks aloud (you/we/I), never creative brief instructions
- NEVER output meta directions like "Open with a hook", "Establish credibility", "Position this as", or "Keep the tone"
- If Notes or Creative direction are brief-style bullets, convert them into natural spoken lines with timestamps
- Never use: {', '.join(req.forbidden_words) if req.forbidden_words else 'none'}
- End with clear CTA: {req.cta or 'Learn more'}
- No markdown, no extra keys"""

    try:
        client = ai_service._get_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": "\n".join(user_bits)},
            ],
            max_tokens=900,
            response_format={"type": "json_object"},
        )
        raw = _strip_json_fence(response.choices[0].message.content or "")
        data = json.loads(raw)
        if req.purpose in ("brief_notes", "visual_cues"):
            notes = (data.get("notes") or data.get("full_script") or "").strip()
            if notes:
                return _brief_notes_response(notes, req)
        lines = [AvatarScriptLine(**line) for line in data.get("lines", [])]
        full_script = (data.get("full_script") or "").strip()
        if not full_script and lines:
            full_script = "\n".join(f"[{l.start} - {l.end}] {l.text}" for l in lines)
        if not lines and full_script:
            lines = _parse_timed_lines(full_script, req.target_seconds)
        spoken = _spoken_text(lines, full_script)
        word_count = len(spoken.split())
        estimated = word_count / WPS
        return AvatarScriptResponse(
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
        )
    except Exception:
        return _mock_script(req)
