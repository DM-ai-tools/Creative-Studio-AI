import json
import logging
import re

from app.core.config import settings

logger = logging.getLogger(__name__)
from app.services.media.registry import get_image_provider, get_video_provider


class AIService:
    def __init__(self):
        self._client = None

    def _get_client(self):
        if self._client is None:
            import openai

            headers = {"X-Title": settings.APP_NAME}
            if settings.OPENROUTER_HTTP_REFERER:
                headers["HTTP-Referer"] = settings.OPENROUTER_HTTP_REFERER

            self._client = openai.OpenAI(
                api_key=settings.OPENROUTER_API_KEY,
                base_url=settings.OPENROUTER_BASE_URL,
                default_headers=headers,
            )
        return self._client

    def _resolve_model(self, model: str) -> str:
        if model == "claude":
            return settings.OPENROUTER_MODEL_CLAUDE
        return settings.OPENROUTER_MODEL_OPENAI

    def _resolve_provider_model(self, model: str, default: str) -> str:
        if model in {"claude", "openai", "default"}:
            return default
        return model

    async def generate_ad_copy(
        self,
        brand_voice: str,
        forbidden_words: list[str],
        brief: dict,
        format_type: str,
        model: str = "claude",
    ) -> dict:
        if not settings.OPENROUTER_API_KEY:
            return self._mock_ad_copy(brief, format_type)

        system_prompt = f"""You are an expert Meta Ads copywriter. Generate ad creative copy that is:
- On-brand: {brand_voice or 'Engaging and professional'}
- Format-optimized: {format_type} ad
- Never uses these words: {', '.join(forbidden_words) if forbidden_words else 'none'}

Return ONLY valid JSON with these fields:
{{
  "hook": "scroll-stopping opening line (max 15 words)",
  "headline": "main headline (max 8 words)",
  "body_copy": "2-3 sentences of persuasive body copy",
  "cta": "call to action text (2-4 words)",
  "hashtags": ["hashtag1", "hashtag2", "hashtag3"]
}}"""

        user_prompt = f"""Create a {format_type} Meta Ad for:
Product: {brief.get('product_name', '')}
Objective: {brief.get('objective', '')}
Target Audience: {brief.get('target_audience', '')}
Tone: {brief.get('ad_copy_tone', 'Professional')}
CTA Goal: {brief.get('cta', 'Shop Now')}
Key Benefits: {json.dumps(brief.get('key_benefits', {}))}"""

        try:
            client = self._get_client()
            response = client.chat.completions.create(
                model=self._resolve_model(model),
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                max_tokens=600,
                response_format={"type": "json_object"},
            )
            raw = response.choices[0].message.content or ""
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
        except Exception:
            pass

        return self._mock_ad_copy(brief, format_type)

    async def generate_image_asset(
        self,
        *,
        prompt: str,
        tenant_id: str,
        model: str,
        format_type: str,
        logo_url: str | None = None,
        logo_on_light_url: str | None = None,
    ) -> dict:
        provider = get_image_provider(model)
        return await provider.generate(
            prompt=prompt,
            tenant_id=tenant_id,
            model=model,
            format_type=format_type,
            logo_url=logo_url,
            logo_on_light_url=logo_on_light_url,
        )

    async def generate_video_storyboard(
        self,
        *,
        brief: dict,
        copy: dict,
        format_type: str,
        model: str,
        tenant_id: str = "",
        source_image_url: str | None = None,
        duration_seconds: int | None = None,
        logo_url: str | None = None,
        logo_on_light_url: str | None = None,
    ) -> dict:
        from app.services.brand_prompt import build_image_prompt

        # Resolve on_light from brief/logo_variations if not explicitly passed
        _on_light = logo_on_light_url or brief.get("logo_on_light_url")
        if not _on_light:
            _vars = brief.get("logo_variations")
            if isinstance(_vars, dict):
                _on_light = _vars.get("on_light")
        brand_ctx = {
            "brand_name": brief.get("brand_name"),
            "primary_color": brief.get("primary_color"),
            "secondary_color": brief.get("secondary_color"),
            "logo_url": logo_url or brief.get("logo_url"),
            "logo_on_light_url": _on_light,
            "logo_variations": brief.get("logo_variations"),
        }
        if not brand_ctx.get("logo_url"):
            from app.services.brand_logo import resolve_video_logo_urls
            _rlogo, _rlight = resolve_video_logo_urls(brief=brief, brand=brand_ctx)
            if _rlogo:
                brand_ctx["logo_url"] = _rlogo
            if _rlight:
                brand_ctx["logo_on_light_url"] = _rlight
        if not brand_ctx.get("logo_url"):
            logger.warning(
                "generate_video_storyboard: no brand kit logo_url on brief — upload logo on Brand Kit"
            )
        prompt = build_image_prompt(
            brand=brand_ctx,
            brief=brief,
            copy=copy,
            format_type=format_type,
        )
        from app.services.video_duration import resolve_video_duration_seconds
        from app.services.video_script_skeleton import (
            build_veo_prompt_from_skeleton,
            ensure_production_skeleton,
        )

        duration = resolve_video_duration_seconds(brief, override=duration_seconds)
        production_skeleton = await ensure_production_skeleton(
            brief,
            copy,
            duration=duration,
            format_type=format_type,
        )
        brief = {**brief, "video_script_skeleton": production_skeleton}
        from app.services.media.higgsfield_models import is_higgsfield_video_model

        if is_higgsfield_video_model(model):
            from app.services.video_script_skeleton import build_higgsfield_motion_prompt

            motion = build_higgsfield_motion_prompt(
                production_skeleton,
                brief=brief,
                copy=copy,
                format_type=format_type,
                duration=duration,
            )
        else:
            motion = build_veo_prompt_from_skeleton(
                production_skeleton,
                brief=brief,
                copy=copy,
                format_type=format_type,
                duration=duration,
            )
        provider = get_video_provider(model)
        result = await provider.generate(
            prompt=motion,
            brief=brief,
            copy=copy,
            format_type=format_type,
            model=model,
            tenant_id=tenant_id,
            source_image_url=source_image_url,
            duration_seconds=duration_seconds,
        )
        from app.services.video_portrait import is_vertical_format

        if result.get("status") == "done" and result.get("url") and tenant_id:
            if is_vertical_format(format_type):
                from app.services.video_portrait import normalize_portrait_video_file

                fitted = normalize_portrait_video_file(
                    str(result["url"]),
                    tenant_id=tenant_id,
                    format_type=format_type,
                )
                if fitted:
                    result["url"] = fitted
                    result["portrait_normalized"] = True

        if result.get("status") == "done" and result.get("url") and tenant_id:
            from app.services.brand_logo import resolve_video_logo_urls
            from app.services.video_logo_overlay import finalize_video_with_brand_logo

            resolved_logo, resolved_on_light = resolve_video_logo_urls(
                brief=brief,
                brand=brand_ctx,
                logo_url=logo_url,
                logo_on_light_url=logo_on_light_url,
            )
            from app.services.video_subtitles import resolve_spoken_script_for_subtitles

            spoken_for_subs = resolve_spoken_script_for_subtitles(brief, result, copy=copy)
            try:
                result = finalize_video_with_brand_logo(
                    result,
                    brief=brief,
                    format_type=format_type,
                    tenant_id=tenant_id,
                    brand=brand_ctx,
                    logo_url=resolved_logo,
                    logo_on_light_url=resolved_on_light,
                    spoken_script=spoken_for_subs,
                    duration_seconds=float(
                        result.get("requested_duration_seconds")
                        or result.get("duration_seconds")
                        or duration
                    ),
                )
            except Exception as exc:
                result = {
                    **result,
                    "logo_applied": False,
                    "subtitles_applied": False,
                    "finalize_error": str(exc),
                }
        return result

    async def run_compliance_check(
        self,
        copy: dict,
        forbidden_words: list[str],
        industry: str,
    ) -> dict:
        all_text = " ".join([
            copy.get("hook", ""),
            copy.get("headline", ""),
            copy.get("body_copy", ""),
            copy.get("cta", ""),
        ]).lower()

        errors = []
        warnings = []

        for word in forbidden_words:
            if re.search(r"\b" + re.escape(word.lower()) + r"\b", all_text):
                errors.append(f"Forbidden word used: '{word}'")

        superlative_patterns = [r"\bbest ever\b", r"\b#1\b", r"\bguaranteed\b", r"\bcures?\b"]
        for pat in superlative_patterns:
            if re.search(pat, all_text):
                warnings.append("Potentially non-compliant claim detected")
                break

        passed = len(errors) == 0
        score = 1.0 if passed and not warnings else (0.7 if passed else 0.0)

        return {
            "passed": passed,
            "errors": errors,
            "warnings": warnings,
            "score": score,
        }

    def _mock_ad_copy(self, brief: dict, format_type: str) -> dict:
        product = brief.get("product_name", "our product")
        cta = brief.get("cta", "Shop Now")

        hooks_by_format = {
            "reel": f"Stop scrolling — {product} just changed everything",
            "video": f"What if {product} could transform your day?",
            "static": f"Introducing {product}",
            "carousel": f"Discover the full {product} collection",
        }

        return {
            "hook": hooks_by_format.get(format_type, f"Discover {product}"),
            "headline": f"{product} — Built for You",
            "body_copy": (
                f"Experience the difference with {product}. "
                f"Crafted for those who demand quality, it delivers results you can see. "
                f"Join thousands of satisfied customers today."
            ),
            "cta": cta,
            "hashtags": [
                f"#{product.replace(' ', '')}",
                "#TryItToday",
                "#NewArrivals",
            ],
        }


ai_service = AIService()
