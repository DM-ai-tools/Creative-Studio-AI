"""Keep editorial copy out of generated pixels; compose approved graphics once."""
from __future__ import annotations

import re
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from app.services.creative_studio_timeline import SHOT_HEADER
from app.services.ffmpeg_util import require_ffmpeg
from app.services.file_service import file_service
from app.services.video_subtitles import _ensure_local_video
from app.services.logo_overlay import file_url_to_local_path


_EDITORIAL_ONLY = re.compile(
    r"(?i)\b(?:on[ -]screen|end card|title card|caption|subtitle|logo|wordmark|"
    r"typograph|website|cta|voice[ -]?over|narrat(?:ion|or)|speak only)\b"
)


def extract_brand_terms(text: str) -> list[str]:
    """Find campaign names so generated pixels can stay clean and unbranded."""
    candidates: list[str] = []
    patterns = (
        (r"for\s+\*\*([^*\n]{2,80})\*\*", re.I),
        (r"uploaded\s+\*\*([^*\n]{2,80}?)\s+logo\b", re.I),
        (r"\b([A-Z][A-Za-z0-9&']+(?:\s+[A-Z][A-Za-z0-9&']+){0,4})\s+(?:logo|branding|staff)\b", 0),
    )
    stopwords = {"a", "the", "subtle", "original", "uploaded", "under", "as"}
    for pattern, flags in patterns:
        for match in re.finditer(pattern, text or "", flags):
            name = re.sub(r"\s+", " ", match.group(1)).strip(" *.,:-")
            words = name.split()
            while words and words[0].lower() in stopwords:
                words.pop(0)
            name = " ".join(words)
            if name.lower().endswith(" as the exact original brand"):
                name = name[: -len(" as the exact original brand")].strip()
            if name and name.lower() not in {item.lower() for item in candidates}:
                candidates.append(name)
    return candidates[:8]


def sanitize_visual_direction(text: str, *, brand_terms: list[str] | None = None) -> str:
    """Keep scene action while removing text/logo instructions from mixed prose."""
    cleaned: list[str] = []
    terms = list(brand_terms or extract_brand_terms(text))
    for raw in (text or "").splitlines():
        line = raw.strip()
        if not line:
            continue
        # Scene headings are structural timeline data. Words such as CTA,
        # BRAND or LOGO in a title must never delete its time range.
        if SHOT_HEADER.fullmatch(line):
            cleaned.append(line)
            continue
        # Markdown-wrapped campaign names are metadata, not scenery.
        line = re.sub(r"(?i)\bfor\s+\*\*[^*\n]{2,80}\*\*", "for the business", line)
        # A useful scene action and a logo request often share one sentence.
        # Remove only the logo clause so the authored location/action survives.
        line = re.sub(
            r"(?i)(?:^|,\s*|\s+)(?:using|use|with|featuring|displaying|showing|show|include)\s+"
            r"(?:the\s+)?(?:uploaded|attached|supplied|official|original|exact\s+original\s+)*"
            r"[^.;\n]{0,120}\b(?:logo|wordmark|branding)\b[^.;\n]*[.;]?",
            ". ",
            line,
        )
        line = re.sub(r"(?i)\bVIDEO\s+SPECIFICATIONS\s*:.*$", "", line)
        for term in terms:
            line = re.sub(re.escape(term), "the business", line, flags=re.I)
        line = re.sub(r"(?i)^the video should promote\b.*$", "", line)
        line = re.sub(r"\s+", " ", line).strip(" .,-")
        if not line:
            continue
        # Drop standalone production-copy instructions; retain mixed lines with
        # concrete people, setting, product, camera or action direction.
        if _EDITORIAL_ONLY.search(line) and not re.search(
            r"(?i)\b(?:person|people|woman|man|family|worker|homeowner|product|"
            r"room|kitchen|yard|office|camera|light|hand|walk|sit|stand|open)\b",
            line,
        ):
            continue
        cleaned.append(line)
    return "\n".join(cleaned)


def natural_capture_directive(brief: str) -> str:
    """Concrete capture physics that avoid glossy, posed AI-ad imagery."""
    text = (brief or "").lower()
    if re.search(r"\b(?:ugc|selfie|creator|phone camera|smartphone|social video)\b", text):
        return (
            "Captured as authentic handheld smartphone footage with a 26mm-equivalent lens, "
            "normal auto-exposure, available window/daylight, slight hand movement, natural "
            "skin texture and ordinary lived-in detail. Relaxed unscripted body language."
        )
    return (
        "Captured as grounded live-action documentary footage on a 35mm lens at f/4, using "
        "available daylight and practical lights with restrained handheld or shoulder movement. "
        "Natural skin texture, believable weight and contact, mild sensor grain and normal "
        "exposure roll-off. People behave naturally and never pose like catalogue models."
    )


def brand_surface_lock() -> str:
    """Keep provider footage neutral so verified branding can be added in finishing."""
    return (
        "BRAND-SURFACE LOCK: The approved opening frame is authoritative for every visible "
        "mark and every plain surface. Clothing, uniforms, cartons, products, vehicles, "
        "screens, paperwork, signs and buildings that are plain in that frame must remain "
        "completely plain in every generated frame. Do not invent, replace, approximate or "
        "hallucinate any logo, badge, emblem, company name, wordmark, label or branded "
        "colour-block uniform. Do not infer a manufacturer from the product. A spoken brand "
        "name is audio-only and must never become a visual mark. Verified brand artwork and "
        "campaign text are composited after video generation."
    )


def compile_picture_prompt(brief: str, *, duration: int) -> str:
    """Remove editorial sections, including copy/times that models render as labels.

    Preserve the authored product/cast/location and every shot action. Shot timings
    are director metadata only; overlay/VO schedules never enter the picture task.
    """
    skip_section = False
    skip_copy = False
    output = []
    omit_sections = {
        "on-screen copy and graphic direction", "voiceover performance and synchronisation",
        "generation workflow and final checks",
    }
    resume_sections = {"camera, lighting and finishing", "music and sound mix"}
    for raw in brief.splitlines():
        line = raw.strip()
        if not line:
            continue
        lower = line.lower().rstrip(":")
        if lower in omit_sections:
            skip_section = True
            continue
        if lower in resume_sections:
            skip_section = False
            skip_copy = False
        if skip_section:
            continue
        if SHOT_HEADER.fullmatch(line):
            skip_copy = False
            output.append(line)
            continue
        if re.match(r"(?i)(?:on-screen text|voice[ -]?over(?: begins|\s*[,(:])|VO\s*[:(]|reveal the complete end card)", line):
            skip_copy = True
            continue
        if skip_copy:
            # End narration/text paragraphs at a concrete camera/action section.
            if re.match(r"(?i)(?:transition:|camera:|light:|sound:)", line):
                skip_copy = False
            else:
                continue
        if re.search(r"(?i)campaign idea|on[ -]screen|end card|typograph|website|caption|narrat|voiceover|speak only|shop now", line):
            continue
        if re.search(r"(?i)\b(?:https?://|www\.)|\b[\w-]+\.(?:com|net|org)(?:\.[a-z]+)?\b", line):
            continue
        output.append(line)
    picture = sanitize_visual_direction(
        "\n".join(output), brand_terms=extract_brand_terms(brief)
    )
    picture = re.sub(
        r"(?i)\b(?:hyperrealistic|ultra-realistic|photorealistic|masterpiece|award-winning|stunning)\b",
        "live-action",
        picture,
    )
    return (
        f"Generate {duration} seconds of clean live-action footage. The time ranges below are "
        "editing instructions, never visible content. No numerals, timestamps, counters, "
        "captions, logos, writing, titles, websites or graphic overlays anywhere. Packaging "
        "is plain and unbranded. All advertising graphics are composited separately.\n\n"
        + picture
        + "\n\n" + natural_capture_directive(brief)
        + "\n\nClean picture only. Preserve the product and people, with deliberate cuts between shots. "
        "No visible text or graphics. No glossy synthetic skin, mannequin posing, exaggerated "
        "reactions, impossible hand contact, rubbery motion, floating objects or beauty-filter look. "
        "Audio is ambience, subtle instrumental music and foley only; "
        "no speech or singing. Narration is added in post-production."
        + "\n\n" + brand_surface_lock()
    )


def media_dimensions(path: Path) -> tuple[int, int]:
    # Bundled Windows FFmpeg is available even when ffprobe is not.
    proc = subprocess.run([require_ffmpeg(), "-hide_banner", "-i", str(path)],
                          capture_output=True, text=True, timeout=30)
    match = re.search(r"Stream #.*Video:.*?\b(\d{2,5})x(\d{2,5})\b", proc.stderr)
    if not match:
        raise ValueError("Cannot determine actual video dimensions; refusing guessed graphic placement")
    return int(match[1]), int(match[2])


def compose_campaign_graphics(video_url: str, events: list[tuple[float, float, str]],
                              *, tenant_id: str, logo_url: str | None = None) -> tuple[str, bool]:
    """Render approved strings literally as PNGs and one logo only on the end card."""
    if not events:
        return video_url, False
    source = _ensure_local_video(video_url, tenant_id=tenant_id)
    if not source:
        raise ValueError("Video unavailable for graphics finishing")
    width, height = media_dimensions(source)
    logo_path = file_url_to_local_path(logo_url) if logo_url else None
    if logo_url and not logo_path:
        raise ValueError("Supplied logo unavailable; reattach the logo")
    font_path = next((p for p in [Path('C:/Windows/Fonts/arial.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')] if p.is_file()), None)
    if not font_path:
        raise ValueError("A TrueType font is required for exact campaign typography")
    with tempfile.TemporaryDirectory(prefix="cs_graphics_") as tmp:
        work = Path(tmp)
        cmd = [require_ffmpeg(), '-y', '-i', str(source)]
        filters = []
        previous = '0:v'
        for index, (start, end, text) in enumerate(events, 1):
            canvas = Image.new('RGBA', (width, height))
            draw = ImageDraw.Draw(canvas)
            lines = text.split(r'\N')
            final = len(lines) > 1
            # End-card wordmark is replaced by the official logo, never duplicated.
            use_logo = bool(final and logo_path)
            if use_logo:
                lines = lines[1:]
            font_size = max(16, round(height * (0.030 if final else 0.040)))
            while True:
                font = ImageFont.truetype(str(font_path), font_size)
                widest = max(draw.textlength(line, font=font) for line in lines)
                if widest <= width * 0.80 or font_size <= 12:
                    break
                font_size -= 1
            padding = round(height * 0.015)
            step = round(font_size * 1.4)
            logo = None
            if use_logo:
                logo = Image.open(logo_path).convert('RGBA')
                logo.thumbnail((round(width * 0.18), round(height * 0.065)), Image.Resampling.LANCZOS)
            panel_w = int(max(widest, logo.width if logo else 0) + 4 * padding)
            panel_h = step * len(lines) + 2 * padding + (logo.height + padding if logo else 0)
            left = (width - panel_w) // 2
            top = round(height * 0.92) - panel_h
            draw.rounded_rectangle((left, top, left + panel_w, top + panel_h),
                                   radius=padding, fill=(255, 255, 255, 235))
            y = top + padding
            if logo:
                canvas.alpha_composite(logo, ((width - logo.width) // 2, y))
                y += logo.height + padding
            for line in lines:
                draw.text((width // 2, y), line, font=font, anchor='mt', fill=(28, 30, 33, 255))
                y += step
            png = work / f'graphic-{index}.png'
            canvas.save(png)
            cmd += ['-loop', '1', '-i', str(png)]
            label = f'graphic{index}'
            filters.append(f'[{previous}][{index}:v]overlay=0:0:enable=\'gte(t,{start:.3f})*lt(t,{end:.3f})\':shortest=1[{label}]')
            previous = label
        output = work / 'finished.mp4'
        cmd += ['-filter_complex', ';'.join(filters), '-map', f'[{previous}]', '-map', '0:a?',
                '-c:v', 'libx264', '-crf', '18', '-preset', 'fast', '-pix_fmt', 'yuv420p',
                '-c:a', 'copy', '-movflags', '+faststart', str(output)]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if proc.returncode:
            raise RuntimeError('Campaign graphics failed: ' + proc.stderr[-500:])
        saved = file_service.save_bytes(output.read_bytes(), tenant_id, 'generated', '.mp4', 'video/mp4')
        return saved['file_url'], True
