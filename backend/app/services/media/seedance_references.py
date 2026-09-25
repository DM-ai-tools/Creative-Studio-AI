"""Bind image identities to their actual ordered Seedance attachments."""

from __future__ import annotations

# Roles safe to resubmit when BytePlus privacy filter rejects photoreal people.
_PRIVACY_SAFE_ROLES = frozenset({"product", "logo", "scene"})


def reference_manifest(brief: dict, source_url: str | None) -> list[dict[str, str]]:
    assets = brief.get("reference_assets") or []
    selected: dict[str, str] = {}

    def add(url: str | None, role: str) -> None:
        url = str(url or "").strip()
        if url and url not in selected:
            selected[url] = role

    add(brief.get("continuity_reference_url"), "continuity")
    # An explicitly selected character is the strongest identity anchor. Product
    # and logo remain authoritative for their own identities if URLs overlap with
    # an approved composition.
    for asset in assets:
        if asset.get("role") == "character":
            add(asset.get("url"), asset["role"])
    add(brief.get("cast_reference_url"), "cast")
    add(brief.get("product_reference_url"), "product")
    add(brief.get("logo_reference_url"), "logo")
    for asset in assets:
        if asset.get("role") == "scene":
            add(asset.get("url"), asset["role"])
    for url in brief.get("additional_reference_urls") or []:
        add(url, "reference")
    if len(selected) > 9:
        internal_urls = {
            str(brief.get("cast_reference_url") or "").strip(),
            str(brief.get("continuity_reference_url") or "").strip(),
        } - {""}
        if internal_urls:
            available = max(1, 9 - len(internal_urls))
            raise ValueError(
                "Long-video continuity reserves reference slots for the persistent cast and "
                f"previous chapter frame. Keep at most {available} supplied character, product, "
                "scene, logo and supporting references."
            )
        raise ValueError("Seedance supports at most 9 reference images. Remove unused references.")
    # Approved compositions are secondary; never displace supplied identity anchors.
    for url in [source_url, *(brief.get("storyboard_image_urls") or [])]:
        if len(selected) < 9:
            add(url.get("url") if isinstance(url, dict) else url, "storyboard")
    order = {"character": 0, "cast": 1, "continuity": 2, "product": 3, "scene": 4, "logo": 5, "reference": 6, "storyboard": 7}
    return sorted(
        ({"url": url, "role": role} for url, role in selected.items()),
        key=lambda asset: order[asset["role"]],
    )


def filter_manifest_for_privacy_retry(manifest: list[dict[str, str]]) -> list[dict[str, str]]:
    """Keep non-portrait anchors (product/logo/scene) after a privacy rejection."""
    return [asset for asset in manifest if asset.get("role") in _PRIVACY_SAFE_ROLES]


def reference_instructions(assets: list[dict[str, str]]) -> str:
    if not assets:
        return ""
    roles = {
        "scene": "SCENE: use only for location, palette, lighting and world continuity. Do not copy product or character identity from this image.",
        "product": "PRODUCT: authoritative product identity. Preserve its silhouette, construction, proportions, materials and colours in every shot. Do not substitute furniture or objects from other references. Follow the brief's quantity.",
        "character": "CHARACTER: preserve this person's face, build, identity and wardrobe across shots unless the brief requests a change. Do not take product design or location from this portrait.",
        "cast": "CAST ANCHOR: persistent identity from the first completed chapter. Preserve the visible people's faces, age, build, hair and wardrobe across the whole film; use the CONTINUITY FRAME for their current pose and scene position.",
        "continuity": "CONTINUITY FRAME: exact final frame of the previous chapter. Begin from its pose, camera axis, lighting, wardrobe, props and scene state, then continue forward without replaying the prior action. Character and product anchors remain authoritative for identity.",
        "logo": "BRAND: authoritative logo shape, colours and typography only. Follow the finishing instructions about whether branding is composited later; do not copy its background into the scene.",
        "reference": "SUPPORTING REFERENCE: use only as directed in the brief. Never override the labelled product, character or scene anchors.",
        "opening": "APPROVED OPENING FRAME: begin from this exact composition, subject, location and scene state, then move naturally into the timed story.",
        "storyboard": "APPROVED COMPOSITION: use for shot composition and visual style. Supplied product and character anchors remain authoritative if this generated still differs.",
    }
    return "\n\nREFERENCE IMAGE BINDINGS (attachment order):\n" + "\n".join(
        f"Image {i}: {roles[asset['role']]}" for i, asset in enumerate(assets, 1)
    ) + "\nFollow all timed shots in order with consistent identities. A reference is not an instruction to freeze the video."
