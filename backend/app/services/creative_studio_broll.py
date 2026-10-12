"""Parse GPT Image 2 B-roll plans and build per-chapter Seedance segment timelines."""

from __future__ import annotations

import math
import re
from typing import Any

SEEDANCE_MIN_SEGMENT_SECONDS = 4.0

_BROLL_BLOCK = re.compile(
    r"(?is)IMAGE\s+(\d+)\s*[-–—]\s*([^\n]+)\n"
    r"(?:[^\n]*\n)*?"
    r"(?:Scene timing:\s*\n?\s*)?"
    r"(\d{1,2}(?::\d{2}(?:\.\d+)?|\.\d+)?|\d+(?:\.\d+)?)\s*[–—\-:\s]+\s*"
    r"(\d{1,2}(?::\d{2}(?:\.\d+)?|\.\d+)?|\d+(?:\.\d+)?)\s*(?:s|seconds?)?\b"
    r"(?:[^\n]*\n)*?"
    r"(?:Image generation prompt:\s*\n?)?"
    r"(.+?)(?=\n(?:Use:|Do not reuse|\-{3,}|IMAGE\s+\d+\s*[-–—]|\Z))"
)

_BACKGROUND_IMAGE_HEADER = re.compile(
    r"(?im)^[ \t]*(?:\d+[.)][ \t]*)?(?:GENERATED[ \t]+)?"
    r"BACKGROUND[ \t]+IMAGE[ \t]+(\d+)[ \t]*$"
)

_BROLL_READABLE_PREFIX = (
    "CRITICAL — READABLE ON-SCREEN TEXT: Large sharp English typography on the monitor or "
    "dashboard. Spell every requested word correctly. No abstract charts-only layouts unless "
    "specific labels are also shown. "
)

_BROLL_READABLE_SUFFIX = (
    " Single square 1:1 photoreal commercial still. Any on-screen words, numbers, labels "
    "or UI copy requested above must render with correct English spelling, grammar, "
    "punctuation and numerals — sharp and legible at a glance. No gibberish, no pseudo-text, "
    "no malformed letters, no random symbols, no blurred UI copy. Premium dark charcoal "
    "workspace, subtle blue/green accents, matte finish."
)

_BROLL_ABSTRACT_SUFFIX = (
    " Single square 1:1 photoreal commercial still. Avoid readable generated UI copy; "
    "use abstract charts, icons and coloured bars, or intentionally soft-blurred labels "
    "where words are not required. Premium dark charcoal workspace, subtle blue/green "
    "accents, matte finish."
)


def brief_prefers_abstract_broll(brief: str) -> bool:
    """True when the brief explicitly asks to hide or blur on-screen text."""
    low = str(brief or "").lower()
    return bool(
        re.search(
            r"(?i)(?:blur(?:red)?|unreadable|abstract ui|no readable|avoid readable|"
            r"do not (?:show|render|place) readable|hide (?:all )?text|"
            r"text[- ]free|without readable)",
            low,
        )
    )


def image_prompt_wants_readable_text(prompt: str, *, brief: str = "") -> bool:
    """Default True for B-roll stills. Opt out only when this image prompt asks for blur."""
    prompt_blob = str(prompt or "").lower()
    if re.search(
        r"(?i)(?:blur(?:red)?|unreadable|abstract ui|no readable|avoid readable|"
        r"do not (?:show|render|place) readable|hide (?:all )?text|without readable text|"
        r"intentionally (?:blurred|soft|defocused))",
        prompt_blob,
    ):
        return False
    if re.search(
        r"(?i)(?:readable|legible|sharp text|show (?:the )?text|correct spelling|"
        r"labels|headline|dashboard numbers|on-screen copy|typography)",
        f"{prompt_blob} {brief}".lower(),
    ):
        return True
    # B-roll defaults to readable text even when older briefs mention global blur rules.
    return True


def _parse_time(value: str) -> float:
    raw = str(value or "").strip().lower().replace("s", "").strip()
    if not raw:
        return 0.0
    if ":" in raw:
        mins, secs = raw.split(":", 1)
        return float(mins) * 60.0 + float(secs)
    return float(raw)


def parse_broll_images(brief: str) -> list[dict[str, Any]]:
    """Extract IMAGE N blocks with timing and GPT still prompts from a production brief."""
    text = str(brief or "")
    items: list[dict[str, Any]] = []
    for match in _BROLL_BLOCK.finditer(text):
        index = int(match.group(1))
        title = re.sub(r"\s+", " ", str(match.group(2) or f"Image {index}")).strip()
        start = _parse_time(match.group(3))
        end = _parse_time(match.group(4))
        if end <= start:
            end = start + 1.5
        prompt = re.sub(r"\s+", " ", str(match.group(5) or "").strip())
        prompt = re.sub(r"(?is)^purpose:\s*.+?(?=create a|\Z)", "", prompt).strip()
        wants_readable = image_prompt_wants_readable_text(prompt, brief=text)
        suffix = _BROLL_READABLE_SUFFIX if wants_readable else _BROLL_ABSTRACT_SUFFIX
        if prompt:
            if wants_readable and _BROLL_READABLE_PREFIX.strip() not in prompt:
                prompt = f"{_BROLL_READABLE_PREFIX}{prompt}"
            if suffix.strip() not in prompt:
                prompt = f"{prompt}{suffix}"
        items.append(
            {
                "index": index,
                "title": title[:120],
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "image_prompt": prompt[:2200],
                "wants_readable_text": wants_readable,
            }
        )

    # Long-form master prompts often describe supporting images as
    # "GENERATED BACKGROUND IMAGE 1" instead of "IMAGE 1 - ...". Parse those
    # blocks directly so the chat pipeline creates a B-roll board instead of
    # treating the full presenter brief as one GPT Image prompt.
    background_headers = list(_BACKGROUND_IMAGE_HEADER.finditer(text))
    for position, header in enumerate(background_headers):
        index = int(header.group(1))
        stop = (
            background_headers[position + 1].start()
            if position + 1 < len(background_headers)
            else len(text)
        )
        block = text[header.end():stop]
        name_match = re.search(
            r"(?is)\bNAME:\s*(.+?)(?=\n\s*(?:USE DURING|SUPPORTS|IMAGE GENERATION PROMPT):)",
            block,
        )
        timing_match = re.search(
            r"(?is)\bUSE DURING:\s*(?:Approximately\s*)?"
            r"(\d{1,2}(?::\d{2}(?:\.\d+)?|\.\d+)?|\d+(?:\.\d+)?)\s*"
            r"[–—\-]\s*"
            r"(\d{1,2}(?::\d{2}(?:\.\d+)?|\.\d+)?|\d+(?:\.\d+)?)",
            block,
        )
        prompt_match = re.search(
            r"(?is)\bIMAGE GENERATION PROMPT:\s*(.+?)"
            r"(?=\n\s*(?:VIDEO MOTION:|Do not reuse|={10,}|\Z))",
            block,
        )
        if not timing_match or not prompt_match:
            continue
        title = re.sub(
            r"\s+", " ",
            str(name_match.group(1) if name_match else f"Background image {index}").strip(),
        )
        start = _parse_time(timing_match.group(1))
        end = _parse_time(timing_match.group(2))
        if end <= start:
            end = start + 1.5
        prompt = re.sub(r"\s+", " ", str(prompt_match.group(1) or "").strip())
        wants_readable = image_prompt_wants_readable_text(prompt, brief=text)
        suffix = _BROLL_READABLE_SUFFIX if wants_readable else _BROLL_ABSTRACT_SUFFIX
        if prompt:
            if wants_readable and _BROLL_READABLE_PREFIX.strip() not in prompt:
                prompt = f"{_BROLL_READABLE_PREFIX}{prompt}"
            if suffix.strip() not in prompt:
                prompt = f"{prompt}{suffix}"
        items.append(
            {
                "index": index,
                "title": title[:120],
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "image_prompt": prompt[:2200],
                "wants_readable_text": wants_readable,
            }
        )
    by_index = {int(item["index"]): item for item in items}
    return [by_index[key] for key in sorted(by_index.keys())]


def broll_items_for_chapter(
    plan: list[dict[str, Any]],
    *,
    chapter_start: float,
    chapter_end: float,
) -> list[dict[str, Any]]:
    return [
        item
        for item in plan
        if float(item["start"]) >= chapter_start - 0.02
        and float(item["end"]) <= chapter_end + 0.02
    ]


_PRESENTER_SECTION_HEADER = re.compile(
    r"(?im)^[ \t]*(?:#{1,6}[ \t]*)?(?:=+[ \t]*)?"
    r"([A-Z][A-Z0-9 /&()'_-]{2,100})(?:[ \t]*=+)?[ \t]*$"
)
_PRESENTER_SECTION_WORDS = (
    "presenter",
    "character",
    "cast",
    "talent",
    "avatar",
    "identity lock",
    "voice lock",
)
_PRESENTER_SECTION_EXCLUSIONS = (
    "voiceover",
    "exact script",
    "b-roll",
    "broll",
    "timeline",
    "chapter",
    "scene",
    "image",
    "proof",
    "cta",
    "post-production",
)
_PRESENTER_LINE_HINT = re.compile(
    r"(?i)\b(?:presenter|character|cast|talent|avatar|identity lock|"
    r"female|male|woman|man|wardrobe|blazer|shirt|dress|hair|skin tone|"
    r"direct[- ]to[- ]camera|office|showroom|studio|voice lock|accent)\b"
)
_PRESENTER_LINE_BLOCK = re.compile(
    r"(?i)(?:\bIMAGE\s+\d+\b|\bB-?ROLL\b|\bPROOF\b|\bCTA\b|"
    r"\bEND CARD\b|\bDASHBOARD\b|\bMONTAGE\b|\bCUTAWAY\b|"
    r"\d{1,2}:\d{2}\s*[–—-]\s*\d{1,2}:\d{2})"
)

_PRODUCT_ONLY_BRIEF = re.compile(
    r"(?im)(?:"
    r"^\s*VIDEO\s+MODE\s*:\s*PRODUCT[- ]ONLY\s*$|"
    r"^\s*PRESENTER\s*:\s*(?:NONE|NO|NOT REQUIRED)\s*$|"
    r"\bPRODUCT[- ]ONLY\s+(?:VIDEO|COMMERCIAL|FILM|FOOTAGE|VISUALS?)\b|"
    r"\bPRODUCT\s+ALONE\s+(?:VIDEO|COMMERCIAL|FILM|FOOTAGE|VISUALS?)\b|"
    r"\bONLY\s+(?:THE\s+)?PRODUCT\s+(?:IS|SHOULD BE|MUST BE)\s+(?:VISIBLE|SHOWN|FEATURED)\b|"
    r"\bNO\s+(?:ON[- ]CAMERA\s+)?(?:PRESENTER|SPOKESPERSON|HOST|AVATAR)\s+"
    r"(?:IN|ON|THROUGHOUT)\s+(?:THE\s+)?(?:VIDEO|FILM|SCREEN)\b|"
    r"\bDO NOT\s+(?:SHOW|INCLUDE)\s+(?:A\s+|ANY\s+|THE\s+)?"
    r"(?:PRESENTER|SPOKESPERSON|HOST|AVATAR|ON[- ]CAMERA TALENT)\s+"
    r"(?:IN|ON|THROUGHOUT)\s+(?:THE\s+)?(?:VIDEO|FILM|SCREEN)\b"
    r")"
)


def brief_requests_product_only(prompt: str) -> bool:
    """Return True only for an explicit no-presenter/product-only instruction.

    B-roll instructions such as "no presenter", "no presenter still" or "do not
    generate a presenter image with GPT" do not activate this mode because those
    briefs may still ask Seedance to create the presenter itself.
    """
    return bool(_PRODUCT_ONLY_BRIEF.search(str(prompt or "")))


def presenter_identity_context(prompt: str, *, max_chars: int = 2400) -> str:
    """Extract reusable cast context without leaking the chapter shot list."""
    text = str(prompt or "").strip()
    if not text:
        return ""
    headers = list(_PRESENTER_SECTION_HEADER.finditer(text))
    selected: list[str] = []
    for index, header in enumerate(headers):
        title = re.sub(r"\s+", " ", header.group(1)).strip()
        low_title = title.lower()
        if not any(word in low_title for word in _PRESENTER_SECTION_WORDS):
            continue
        if any(word in low_title for word in _PRESENTER_SECTION_EXCLUSIONS):
            continue
        stop = headers[index + 1].start() if index + 1 < len(headers) else len(text)
        body = text[header.end():stop].strip()
        safe_lines = [
            line.strip()
            for line in body.splitlines()
            if line.strip()
            and not _PRESENTER_LINE_BLOCK.search(line)
            and not re.match(r"(?i)^VOICEOVER\s*:", line.strip())
            and not re.match(r'^\s*[\"“].+[\"”]\s*$', line.strip())
        ]
        if safe_lines:
            selected.append(f"{title}:\n" + "\n".join(safe_lines))
    if not selected:
        selected = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
            and _PRESENTER_LINE_HINT.search(line)
            and not _PRESENTER_LINE_BLOCK.search(line)
        ]
    value = "\n".join(dict.fromkeys(selected)).strip()
    return value[:max_chars].rstrip()


def presenter_text_to_video_prompt(
    *,
    duration: float,
    chapter_motion_prompt: str = "",
    from_continuity: bool = False,
) -> str:
    """Build an isolated presenter call without replaying the chapter edit."""
    identity = presenter_identity_context(chapter_motion_prompt)
    continuity = (
        "CAST CONTINUITY: Match the attached continuity reference — same fictional presenter, "
        "wardrobe, hair, location and lighting. Do not recast or restyle.\n"
        if from_continuity
        else (
            "TEXT-TO-VIDEO PRESENTER: No presenter still. Generate one fictional commercial "
            "presenter from the identity requirements below; never copy a real person's identity.\n"
        )
    )
    scope = (
        "PRESENTER-ONLY SEGMENT: Keep one continuous presenter performance for this entire call. "
        "Do not cut away to, preview, recreate or animate any separately scheduled B-roll, approved "
        "still, proof image, product card, dashboard close-up, montage, CTA, end card, or later scene. "
        "Do not invent an internal edit. The compositor adds those assets in their own timeline slots. "
        "Use natural direct-to-camera delivery, restrained gestures, realistic blinking and stable "
        "wardrobe, location, lighting and camera direction. Speak only the narration supplied after "
        "this instruction.\n"
    )
    prompt = (
        continuity
        + scope
        + (f"IDENTITY / WARDROBE / LOCATION LOCK:\n{identity}\n" if identity else "")
        + f"Hold this beat for ~{duration:g}s before the next cut."
    )
    return prompt[:6000]


def broll_motion_prompt(
    *,
    title: str,
    duration: float,
    kind: str,
    preserve_text: bool = False,
) -> str:
    label = title or kind
    if preserve_text or kind == "proof":
        return (
            f"Animate the attached approved still only — do not redraw or replace it. "
            f"{label}. Preserve every existing letter, number, label and layout exactly. "
            "Do not add, remove, blur or misspell any text. Subtle premium motion only: "
            f"slow push-in or gentle parallax. Hold ~{duration:g}s. Matte paid-social look."
        )
    return (
        f"Animate the attached approved still only — do not redraw or replace it. "
        f"{label}. Subtle premium commercial motion: slow push-in or gentle parallax. "
        f"Do not add new readable text or logos. Hold composition for ~{duration:g}s. "
        "Matte premium paid-social look."
    )


def product_motion_prompt(
    *,
    title: str,
    duration: float,
    preserve_text: bool = False,
) -> str:
    """Animate an approved product/scene still without introducing a presenter."""
    text_lock = (
        "Preserve every existing letter, number, label and layout exactly. "
        if preserve_text
        else "Do not add any new readable text or logo. "
    )
    return (
        "PRODUCT-ONLY SEGMENT: Animate the attached approved product or scene still only. "
        "Do not introduce a presenter, spokesperson, avatar, talking head or new person. "
        "Preserve the exact product design, geometry, colour, materials, proportions and branding. "
        "Do not replace, redesign, morph or duplicate the product. Preserve any contextual people "
        "already present in the approved still without adding new people. "
        f"{text_lock}{title or 'Product scene'}. Use subtle realistic commercial motion only: "
        f"slow push-in, gentle parallax or restrained product movement. Hold ~{duration:g}s."
    )


def build_chapter_broll_segments(
    *,
    chapter_index: int,
    chapter_start: float,
    chapter_end: float,
    opening_still_url: str,
    proof_still_url: str | None,
    broll_plan: list[dict[str, Any]],
    approved_broll: dict[int, str],
    chapter_motion_prompt: str = "",
) -> list[dict[str, Any]]:
    """
    Build ordered Seedance segments for one chapter. Each segment uses exactly one
    approved still as first_frame (presenter, B-roll dashboard, or uploaded proof).
    """
    if chapter_end <= chapter_start:
        raise ValueError("Chapter duration must be positive")

    brolls = broll_items_for_chapter(
        broll_plan, chapter_start=chapter_start, chapter_end=chapter_end
    )
    product_only = brief_requests_product_only(chapter_motion_prompt)
    segments: list[dict[str, Any]] = []
    cursor = chapter_start

    def append_segment(
        *,
        url: str,
        start: float,
        end: float,
        kind: str,
        title: str = "",
        motion: str = "",
        preserve_text: bool = False,
        text_to_video: bool = False,
        use_continuity: bool = False,
    ) -> None:
        duration = float(end) - float(start)
        if duration < 0.08:
            return
        still_url = str(url or "").strip()
        use_t2v = bool(text_to_video) or (kind == "presenter" and not still_url)
        if not still_url and not use_t2v:
            return
        if use_t2v and kind == "presenter":
            # A presenter call receives cast context only. The compositor appends
            # each approved B-roll/proof still once in its own scheduled slot.
            motion = presenter_text_to_video_prompt(
                duration=duration,
                chapter_motion_prompt=chapter_motion_prompt,
                from_continuity=use_continuity,
            )
        elif kind == "product":
            motion = product_motion_prompt(
                title=title or "Product scene",
                duration=duration,
                preserve_text=preserve_text,
            )
        segments.append(
            {
                "first_frame_url": still_url or None,
                "text_to_video": use_t2v,
                "use_continuity": bool(use_continuity),
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(duration, 3),
                "provider_duration": max(
                    SEEDANCE_MIN_SEGMENT_SECONDS,
                    math.ceil(duration),
                ),
                "kind": kind,
                "title": title,
                "preserve_text": preserve_text or kind == "proof",
                "prompt": motion
                or broll_motion_prompt(
                    title=title or kind,
                    duration=duration,
                    kind=kind,
                    preserve_text=preserve_text or kind == "proof",
                ),
            }
        )

    if not brolls:
        append_segment(
            url=opening_still_url,
            start=chapter_start,
            end=chapter_end,
            kind="product" if product_only else "chapter",
            title="Product hero" if product_only else f"Chapter {chapter_index + 1}",
            motion=chapter_motion_prompt,
            text_to_video=(
                not product_only and not bool(str(opening_still_url or "").strip())
            ),
        )
        return segments

    # Clip 2 hook: uploaded stat screenshot (Reference upload), not a GPT presenter still.
    if (
        chapter_index == 1
        and proof_still_url
        and brolls
        and float(brolls[0]["start"]) > chapter_start + 0.08
    ):
        proof_end = min(float(brolls[0]["start"]), chapter_start + 3.0)
        append_segment(
            url=proof_still_url,
            start=chapter_start,
            end=proof_end,
            kind="proof",
            title="Proof stat",
            preserve_text=True,
        )
        cursor = proof_end

    first_presenter_in_chapter = True
    last_visual_url = str(opening_still_url or "").strip()
    last_visual_title = "Product hero"
    last_visual_preserve = False
    for item in brolls:
        b_start = float(item["start"])
        b_end = float(item["end"])
        b_url = str(approved_broll.get(int(item["index"])) or "").strip()
        if not b_url:
            continue
        preserve = bool(item.get("wants_readable_text"))
        if b_start > cursor + 0.08:
            if product_only:
                # Product-only briefs fill every unscheduled beat from an approved
                # product/scene still. They never fall through to presenter T2V.
                append_segment(
                    url=last_visual_url or b_url,
                    start=cursor,
                    end=b_start,
                    kind="product",
                    title=last_visual_title if last_visual_url else str(item.get("title") or "Product scene"),
                    preserve_text=last_visual_preserve if last_visual_url else preserve,
                )
            else:
                # Presenter beats are text-to-video — BytePlus blocks photoreal face stills.
                append_segment(
                    url="",
                    start=cursor,
                    end=b_start,
                    kind="presenter",
                    title="Presenter",
                    text_to_video=True,
                    use_continuity=chapter_index >= 1 and first_presenter_in_chapter,
                    motion=chapter_motion_prompt,
                )
                first_presenter_in_chapter = False
        append_segment(
            url=b_url,
            start=b_start,
            end=b_end,
            kind="broll",
            title=str(item.get("title") or f"B-roll {item['index']}"),
            preserve_text=preserve,
        )
        cursor = b_end
        last_visual_url = b_url
        last_visual_title = str(item.get("title") or f"B-roll {item['index']}")
        last_visual_preserve = preserve

    if cursor < chapter_end - 0.08:
        tail_kind = "product" if product_only else "presenter"
        tail_url = last_visual_url if product_only else ""
        if proof_still_url and chapter_index == 0 and cursor >= chapter_start + 8.0:
            tail_url = proof_still_url
            tail_kind = "proof"
        append_segment(
            url=tail_url,
            start=cursor,
            end=chapter_end,
            kind=tail_kind,
            title=(
                "Proof stat"
                if tail_kind == "proof"
                else last_visual_title
                if tail_kind == "product"
                else "Presenter"
            ),
            text_to_video=tail_kind == "presenter",
            motion=(
                broll_motion_prompt(
                    title="Proof stat",
                    duration=chapter_end - cursor,
                    kind="proof",
                    preserve_text=True,
                )
                if tail_kind == "proof"
                else ""
                if tail_kind == "product"
                else chapter_motion_prompt
            ),
            preserve_text=(
                True if tail_kind == "proof" else last_visual_preserve if tail_kind == "product" else False
            ),
        )

    if not segments:
        append_segment(
            url=opening_still_url,
            start=chapter_start,
            end=chapter_end,
            kind="chapter",
            title=f"Chapter {chapter_index + 1}",
            motion=chapter_motion_prompt,
            text_to_video=not bool(str(opening_still_url or "").strip()),
        )
    return segments
