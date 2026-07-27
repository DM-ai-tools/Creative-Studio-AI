"""CreativeStudio AI MCP server.

Exposes CreativeStudio tools to Claude Cowork (Streamable HTTP) and
Claude Desktop / Claude Code (stdio).
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Optional

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from creativestudio_mcp.client import CreativeStudioError, get_client

load_dotenv()

_MCP_HOST = os.getenv("MCP_HOST", "0.0.0.0")
_MCP_PORT = int(os.getenv("MCP_PORT", "8100"))

mcp = FastMCP(
    "CreativeStudio AI",
    instructions=(
        "You are connected to CreativeStudio AI, a multi-tenant Meta Ads creative "
        "platform. Use these tools to manage brands, briefs, AI-generated ad variants, "
        "scripts, performance insights, and Meta exports. Prefer listing brands first "
        "when creating briefs. Generation jobs run asynchronously — after generate_variants, "
        "poll get_brief or list_variants until variants complete."
    ),
    host=_MCP_HOST,
    port=_MCP_PORT,
    # Stateless mode works better with Claude Cowork (cloud → your server, no sticky session).
    stateless_http=True,
)


def _ok(data: Any) -> str:
    return get_client().dump(data)


def _err(exc: Exception) -> str:
    if isinstance(exc, CreativeStudioError):
        return f"Error ({exc.status_code}): {exc}"
    return f"Error: {exc}"


# ── Health / account ──────────────────────────────────────────────────────────


@mcp.tool()
def health_check() -> str:
    """Check that the CreativeStudio API is reachable."""
    try:
        client = get_client()
        # API root health lives outside /api/v1
        base = client.api_url.rsplit("/api/v1", 1)[0]
        r = client._client.get(f"{base}/health")
        return _ok(r.json())
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_me() -> str:
    """Return the authenticated CreativeStudio user and tenant."""
    try:
        return _ok(get_client().request("GET", "/auth/me"))
    except Exception as e:
        return _err(e)


# ── Brands ────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_brands() -> str:
    """List all brands for the current tenant."""
    try:
        return _ok(get_client().request("GET", "/brands/"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_brand(brand_id: str) -> str:
    """Get a brand by ID."""
    try:
        return _ok(get_client().request("GET", f"/brands/{brand_id}"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def create_brand(
    name: str,
    website: str = "",
    industry: str = "",
    description: str = "",
) -> str:
    """Create a new brand."""
    try:
        payload: dict[str, Any] = {"name": name}
        if website:
            payload["website"] = website
        if industry:
            payload["industry"] = industry
        if description:
            payload["description"] = description
        return _ok(get_client().request("POST", "/brands/", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def update_brand(
    brand_id: str,
    name: Optional[str] = None,
    website: Optional[str] = None,
    industry: Optional[str] = None,
    description: Optional[str] = None,
) -> str:
    """Update brand fields. Only pass fields you want to change."""
    try:
        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if website is not None:
            payload["website"] = website
        if industry is not None:
            payload["industry"] = industry
        if description is not None:
            payload["description"] = description
        return _ok(get_client().request("PUT", f"/brands/{brand_id}", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_brand_kit(brand_id: str) -> str:
    """Get the brand kit (colors, fonts, voice, logos) for a brand."""
    try:
        return _ok(get_client().request("GET", f"/brands/{brand_id}/kit"))
    except Exception as e:
        return _err(e)


# ── Briefs ────────────────────────────────────────────────────────────────────


@mcp.tool()
def list_briefs(
    status: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> str:
    """List creative briefs. Optional status filter e.g. draft, submitted, running, completed."""
    try:
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if status:
            params["status"] = status
        return _ok(get_client().request("GET", "/briefs/", params=params))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_brief(brief_id: str) -> str:
    """Get a brief by ID, including variant summary and generation status."""
    try:
        return _ok(get_client().request("GET", f"/briefs/{brief_id}"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def create_brief(
    brand_id: str,
    title: str,
    objective: str = "",
    target_audience: str = "",
    product_name: str = "",
    formats: Optional[list[str]] = None,
    ad_copy_tone: str = "Professional",
    cta: str = "Shop Now",
) -> str:
    """Create a new creative brief. formats examples: image, video, carousel, stories."""
    try:
        payload: dict[str, Any] = {
            "brand_id": brand_id,
            "title": title,
            "objective": objective,
            "target_audience": target_audience,
            "product_name": product_name,
            "formats": formats or [],
            "ad_copy_tone": ad_copy_tone,
            "cta": cta,
        }
        return _ok(get_client().request("POST", "/briefs/", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def update_brief(
    brief_id: str,
    title: Optional[str] = None,
    objective: Optional[str] = None,
    target_audience: Optional[str] = None,
    product_name: Optional[str] = None,
    formats: Optional[list[str]] = None,
    ad_copy_tone: Optional[str] = None,
    cta: Optional[str] = None,
) -> str:
    """Update a brief. Only pass fields you want to change."""
    try:
        payload: dict[str, Any] = {}
        for key, value in {
            "title": title,
            "objective": objective,
            "target_audience": target_audience,
            "product_name": product_name,
            "formats": formats,
            "ad_copy_tone": ad_copy_tone,
            "cta": cta,
        }.items():
            if value is not None:
                payload[key] = value
        return _ok(get_client().request("PUT", f"/briefs/{brief_id}", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def delete_brief(brief_id: str) -> str:
    """Permanently delete a brief."""
    try:
        get_client().request("DELETE", f"/briefs/{brief_id}")
        return _ok({"deleted": True, "brief_id": brief_id})
    except Exception as e:
        return _err(e)


@mcp.tool()
def submit_brief(brief_id: str) -> str:
    """Mark a brief as submitted (ready for generation)."""
    try:
        return _ok(get_client().request("POST", f"/briefs/{brief_id}/submit"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def generate_variants(
    brief_id: str,
    formats: Optional[list[str]] = None,
    count_per_format: int = 2,
    ai_model: str = "claude",
    image_model: Optional[str] = None,
    video_model: Optional[str] = None,
    video_duration_seconds: Optional[int] = None,
    heygen_avatar_id: Optional[str] = None,
    heygen_voice_id: Optional[str] = None,
    avatar_script: Optional[str] = None,
) -> str:
    """Start AI generation for a brief. Job runs in the background — poll get_brief afterward."""
    try:
        payload: dict[str, Any] = {
            "count_per_format": count_per_format,
            "ai_model": ai_model,
        }
        if formats is not None:
            payload["formats"] = formats
        if image_model:
            payload["image_model"] = image_model
        if video_model:
            payload["video_model"] = video_model
        if video_duration_seconds is not None:
            payload["video_duration_seconds"] = video_duration_seconds
        if heygen_avatar_id:
            payload["heygen_avatar_id"] = heygen_avatar_id
        if heygen_voice_id:
            payload["heygen_voice_id"] = heygen_voice_id
        if avatar_script:
            payload["avatar_script"] = avatar_script
        return _ok(get_client().request("POST", f"/briefs/{brief_id}/generate", json_body=payload))
    except Exception as e:
        return _err(e)


# ── Variants ──────────────────────────────────────────────────────────────────


@mcp.tool()
def list_variants(
    brief_id: Optional[str] = None,
    status: Optional[str] = None,
    compliance_status: Optional[str] = None,
) -> str:
    """List ad variants. Filter by brief_id, status, or compliance_status."""
    try:
        params: dict[str, Any] = {}
        if brief_id:
            params["brief_id"] = brief_id
        if status:
            params["status"] = status
        if compliance_status:
            params["compliance_status"] = compliance_status
        return _ok(get_client().request("GET", "/variants/", params=params or None))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_variant(variant_id: str) -> str:
    """Get a single variant with hooks, copy, media, and compliance details."""
    try:
        return _ok(get_client().request("GET", f"/variants/{variant_id}"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def approve_variant(variant_id: str) -> str:
    """Approve a variant for use / Meta export."""
    try:
        return _ok(get_client().request("POST", f"/variants/{variant_id}/approve"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def reject_variant(variant_id: str) -> str:
    """Reject a variant."""
    try:
        return _ok(get_client().request("POST", f"/variants/{variant_id}/reject"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def regenerate_variant(variant_id: str) -> str:
    """Regenerate a variant with AI."""
    try:
        return _ok(get_client().request("POST", f"/variants/{variant_id}/regenerate"))
    except Exception as e:
        return _err(e)


# ── Performance ───────────────────────────────────────────────────────────────


@mcp.tool()
def get_dashboard_stats() -> str:
    """Get dashboard KPIs (briefs, variants, performance summaries)."""
    try:
        return _ok(get_client().request("GET", "/performance/dashboard"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_top_performers(limit: int = 10) -> str:
    """List top-performing ad variants."""
    try:
        return _ok(get_client().request("GET", "/performance/top-performers", params={"limit": limit}))
    except Exception as e:
        return _err(e)


@mcp.tool()
def get_fatigue_alerts() -> str:
    """List creative fatigue alerts for underperforming / aging ads."""
    try:
        return _ok(get_client().request("GET", "/performance/fatigue-alerts"))
    except Exception as e:
        return _err(e)


# ── Generation helpers ────────────────────────────────────────────────────────


@mcp.tool()
def get_generation_catalog(refresh: bool = False) -> str:
    """List available image/video/avatar/voice models for generation."""
    try:
        params = {"refresh": True} if refresh else None
        return _ok(get_client().request("GET", "/generation/catalog", params=params))
    except Exception as e:
        return _err(e)


@mcp.tool()
def generate_avatar_script(
    script_prompt: str = "",
    product_name: str = "",
    offer: str = "",
    brand_name: str = "",
    target_audience: str = "",
    ad_copy_tone: str = "Professional",
    cta: str = "Shop Now",
    target_seconds: int = 30,
    purpose: str = "avatar_script",
) -> str:
    """Generate an avatar talking-head script (or brief notes / visual cues / b-roll)."""
    try:
        payload = {
            "script_prompt": script_prompt,
            "product_name": product_name,
            "offer": offer,
            "brand_name": brand_name,
            "target_audience": target_audience,
            "ad_copy_tone": ad_copy_tone,
            "cta": cta,
            "target_seconds": target_seconds,
            "purpose": purpose,
        }
        return _ok(get_client().request("POST", "/generation/avatar-script", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def generate_strategy_preview(
    campaign_name: str = "",
    brand_name: str = "",
    product_name: str = "",
    offer: str = "",
    target_audience: str = "",
    ad_copy_tone: str = "Professional",
    cta: str = "Shop Now",
    objective: str = "",
    formats: Optional[list[str]] = None,
    website_url: str = "",
) -> str:
    """Generate a campaign strategy preview (hooks, angles, creative direction)."""
    try:
        payload: dict[str, Any] = {
            "campaign_name": campaign_name,
            "brand_name": brand_name,
            "product_name": product_name,
            "offer": offer,
            "target_audience": target_audience,
            "ad_copy_tone": ad_copy_tone,
            "cta": cta,
            "objective": objective,
            "formats": formats or [],
            "website_url": website_url,
        }
        return _ok(get_client().request("POST", "/generation/strategy-preview", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def suggest_models(
    campaign_name: str = "",
    objective: str = "",
    formats: Optional[list[str]] = None,
    target_audience: str = "",
    product_name: str = "",
    duration_seconds: int = 30,
) -> str:
    """Ask CreativeStudio which AI image/video models to use for a campaign."""
    try:
        payload: dict[str, Any] = {
            "campaign_name": campaign_name,
            "objective": objective,
            "formats": formats or [],
            "target_audience": target_audience,
            "product_name": product_name,
            "duration_seconds": duration_seconds,
        }
        return _ok(get_client().request("POST", "/generation/suggest-models", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def generate_website_script(
    url: str,
    target_seconds: int = 30,
    brand_name: str = "",
    product_name: str = "",
    offer: str = "",
    ad_copy_tone: str = "Professional",
    cta: str = "Shop Now",
    target_audience: str = "",
) -> str:
    """Scrape a website and generate an avatar ad script from it."""
    try:
        payload = {
            "url": url,
            "target_seconds": target_seconds,
            "brand_name": brand_name,
            "product_name": product_name,
            "offer": offer,
            "ad_copy_tone": ad_copy_tone,
            "cta": cta,
            "target_audience": target_audience,
        }
        return _ok(get_client().request("POST", "/generation/website-script", json_body=payload))
    except Exception as e:
        return _err(e)


@mcp.tool()
def generate_icp_script(
    target_audience: str,
    offer: str = "",
    product_name: str = "",
    brand_name: str = "",
    ad_copy_tone: str = "Professional",
    cta: str = "Shop Now",
    target_seconds: int = 30,
) -> str:
    """Generate an ICP-focused avatar script from audience + offer."""
    try:
        payload = {
            "target_audience": target_audience,
            "offer": offer,
            "product_name": product_name,
            "brand_name": brand_name,
            "ad_copy_tone": ad_copy_tone,
            "cta": cta,
            "target_seconds": target_seconds,
        }
        return _ok(get_client().request("POST", "/generation/icp-script", json_body=payload))
    except Exception as e:
        return _err(e)


# ── Meta Ads ──────────────────────────────────────────────────────────────────


@mcp.tool()
def get_meta_status() -> str:
    """Check Meta Ads connection status for this tenant."""
    try:
        return _ok(get_client().request("GET", "/meta/status"))
    except Exception as e:
        return _err(e)


@mcp.tool()
def export_to_meta(
    variant_ids: list[str],
    campaign_name: str,
    ad_set_name: str = "",
) -> str:
    """Export approved variants to Meta Ads as a campaign draft."""
    try:
        payload: dict[str, Any] = {
            "variant_ids": variant_ids,
            "campaign_name": campaign_name,
        }
        if ad_set_name:
            payload["ad_set_name"] = ad_set_name
        return _ok(get_client().request("POST", "/meta/export", json_body=payload))
    except Exception as e:
        return _err(e)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="CreativeStudio AI MCP server")
    parser.add_argument(
        "--transport",
        choices=("stdio", "http", "sse"),
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="stdio for Claude Desktop; http (Streamable HTTP) for Claude Cowork",
    )
    parser.add_argument("--host", default=os.getenv("MCP_HOST", "0.0.0.0"))
    parser.add_argument("--port", type=int, default=int(os.getenv("MCP_PORT", "8100")))
    args = parser.parse_args(argv)

    mcp.settings.host = args.host
    mcp.settings.port = args.port

    if args.transport == "stdio":
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        mcp.run(transport="sse")
    else:
        # Streamable HTTP — required for Claude Cowork custom connectors
        mcp.run(transport="streamable-http")


if __name__ == "__main__":
    main(sys.argv[1:])
