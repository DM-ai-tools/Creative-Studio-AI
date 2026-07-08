"""Generate a Dual-Mode ICP profile then use it to write an avatar script."""

from __future__ import annotations

import logging

from app.core.config import settings
from app.schemas.avatar_script import (
    AvatarScriptRequest,
    AvatarScriptResponse,
    IcpScriptRequest,
    IcpScriptResponse,
)
from app.services.avatar_script_service import generate_avatar_script
from app.services.australian_copy import AUSTRALIAN_ENGLISH_BRIEF_RULES, AUSTRALIAN_ENGLISH_SCRIPT_RULES

logger = logging.getLogger(__name__)

ICP_SYSTEM_PROMPT = f"""
You are an expert ICP strategist and buyer-psychology analyst for AUSTRALIAN businesses.
Your job is to create a concise but specific Ideal Customer Profile (ICP) that will be used
immediately to write a video ad script in Australian English.

You MUST produce the ICP in the following condensed format (plain text, no markdown headers):

AVATAR NAME: <FirstName LastName — "Archetype Nickname">
IDENTITY: <2-3 sentences: role/life-stage, company size or household, location in Australia, decision power>
CURRENT REALITY: <2-3 sentences: what is happening in their world right now>
CORE PAIN: <1-2 sentences: the deepest frustration driving them to look for a solution>
DESIRED OUTCOME: <1-2 sentences: what they want to achieve / feel after the solution>
KEY OBJECTION: <1 sentence: the #1 thing holding them back>
BUYING TRIGGER: <1 sentence: the specific event that would push them to act now>
LANGUAGE THEY USE: <3-5 short phrases an Australian would actually say out loud — reckon, keen, heaps, etc.>

Rules:
- Keep every section tight — this goes directly into script writing.
- Make the avatar feel like a real Australian person (not a generic demographic).
- Infer missing details (state, business model, maturity) from the offer and audience — do not ask.
- Australian English spelling and phrasing throughout.
{AUSTRALIAN_ENGLISH_BRIEF_RULES}
- Plain text only — no markdown, no bullet symbols, no extra sections.
""".strip()


async def _build_icp(req: IcpScriptRequest) -> str:
    """Call the LLM to produce a concise ICP profile."""
    if not settings.OPENROUTER_API_KEY:
        return (
            f"AVATAR NAME: {req.target_audience or 'Target Customer'} — \"The Ideal Buyer\"\n"
            f"IDENTITY: A motivated buyer interested in {req.offer or req.product_name or 'this offer'}.\n"
            f"CURRENT REALITY: They are actively searching for a solution to their problem.\n"
            f"CORE PAIN: Time, cost, and uncertainty about outcomes.\n"
            f"DESIRED OUTCOME: A fast, trustworthy solution that delivers results.\n"
            f"KEY OBJECTION: Not sure if this is the right fit.\n"
            f"BUYING TRIGGER: A referral or compelling ad that addresses their exact situation.\n"
            f"LANGUAGE THEY USE: \"Is this right for me?\" | \"How much does it cost?\" | \"How fast can I start?\""
        )

    from app.services.ai_service import ai_service

    user_content = "\n".join([
        f"Audience: {req.target_audience or 'Not specified'}",
        f"Offer / Key Message: {req.offer or 'Not specified'}",
        f"Product / Service: {req.product_name or 'Not specified'}",
        f"Brand: {req.brand_name or 'Not specified'}",
        f"Ad tone: {req.ad_copy_tone or 'Professional, friendly'}",
        f"CTA: {req.cta or 'Learn more'}",
        f"Video length: {req.target_seconds} seconds",
    ])

    if req.performance_stats:
        from app.services.stats_image_service import format_performance_stats_for_script

        stats_text = format_performance_stats_for_script(req.performance_stats)
        if stats_text.strip():
            user_content += f"\n\nVerified performance stats (from dashboard image):\n{stats_text}"

    try:
        client = ai_service._get_client()
        response = client.chat.completions.create(
            model=settings.OPENROUTER_MODEL_CLAUDE_SCRIPT,
            messages=[
                {"role": "system", "content": ICP_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_tokens=900,
        )
        icp_text = (response.choices[0].message.content or "").strip()
        if len(icp_text) < 100:
            raise ValueError("ICP response too short")
        return icp_text
    except Exception:
        logger.exception("ICP generation failed — using fallback")
        return (
            f"AVATAR NAME: Buyer — \"The Motivated Customer\"\n"
            f"IDENTITY: A buyer looking for {req.offer or req.product_name or 'this solution'}. "
            f"Audience: {req.target_audience or 'general'}.\n"
            f"CURRENT REALITY: Actively comparing options and reading reviews.\n"
            f"CORE PAIN: Wasted time and money on solutions that didn't deliver.\n"
            f"DESIRED OUTCOME: Clear results, fast onboarding, ongoing support.\n"
            f"KEY OBJECTION: \"I've tried things like this before and it didn't work.\"\n"
            f"BUYING TRIGGER: A specific pain point hits and the cost of doing nothing becomes obvious.\n"
            f"LANGUAGE THEY USE: \"Show me proof\" | \"How long does it take?\" | \"Is there a guarantee?\""
        )


async def build_icp_profile(req: IcpScriptRequest) -> str:
    """Public entry: build ICP text from campaign inputs."""
    return await _build_icp(req)


async def generate_icp_script(req: IcpScriptRequest) -> IcpScriptResponse:
    """Step 1 — build ICP. Step 2 — use ICP to write avatar script."""
    icp_text = await _build_icp(req)

    script_req = AvatarScriptRequest(
        purpose="avatar_script",
        product_name=req.product_name,
        offer=req.offer,
        brand_name=req.brand_name,
        target_audience=req.target_audience,
        ad_copy_tone=req.ad_copy_tone,
        cta=req.cta,
        target_seconds=req.target_seconds,
        avatar_label=req.avatar_label,
        voice_label=req.voice_label,
        forbidden_words=req.forbidden_words,
        variation=req.variation,
        performance_stats=req.performance_stats,
        source_script=req.source_script,
        icp_context=icp_text,
        script_prompt=(
            f"IMPORTANT RULES FOR THIS SCRIPT:\n"
            f"1. The AVATAR NAME in the ICP below is the CUSTOMER PERSONA name — do NOT address the viewer by that name. Always use 'you' or 'your business' instead.\n"
            f"2. The brand delivering this ad is '{req.brand_name}'. Mention '{req.brand_name}' by name at least 2 times naturally (e.g. 'at {req.brand_name}', 'the {req.brand_name} team', '{req.brand_name}'s free audit').\n"
            f"3. Use the ICP insights below to shape the pain points, language, and emotional triggers — but never say the persona's name out loud.\n"
            f"4. AUSTRALIAN ENGLISH ONLY — every line must sound like natural Aussie spoken dialogue (accent, idioms, spelling). Not American English.\n\n"
            f"{AUSTRALIAN_ENGLISH_SCRIPT_RULES}\n\n"
            f"ICP PROFILE:\n{icp_text}"
        ),
    )

    script = await generate_avatar_script(script_req)

    return IcpScriptResponse(icp_text=icp_text, script=script)
