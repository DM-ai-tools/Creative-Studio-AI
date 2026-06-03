"""Parse HeyGen avatar/voice options from settings and expand public look groups."""

from __future__ import annotations

import json
import logging
import re
import time
from threading import Lock
from typing import Any

import httpx

from app.core.config import settings
from app.schemas.generation import CatalogOption

logger = logging.getLogger(__name__)

# Public HeyGen avatar *group* id from app.heygen.com URL (?avatarId=...) — resolved to a look id at generate time
VESPRI_GROUP_ID = "25777ee579284b9d9081bc95c49c5f00"
VESPRI_AVATAR_ID = VESPRI_GROUP_ID  # alias for UI / .env
VESPRI_CATALOG = CatalogOption(id=VESPRI_GROUP_ID, label="Vespri (Female)", gender="female")

_HEX_ID = re.compile(r"^[0-9a-f]{32}$", re.IGNORECASE)


def _parse_options(raw: str) -> list[CatalogOption]:
    raw = (raw or "").strip()
    if not raw:
        return []

    if raw.startswith("["):
        try:
            items = json.loads(raw)
        except json.JSONDecodeError:
            items = []
        out: list[CatalogOption] = []
        for item in items:
            if isinstance(item, dict) and item.get("id"):
                gender = (item.get("gender") or "").strip().lower() or None
                out.append(
                    CatalogOption(
                        id=str(item["id"]),
                        label=str(item.get("label") or item["id"]),
                        gender=gender,
                    )
                )
        return out

    out = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        if ":" in part:
            opt_id, label = part.split(":", 1)
        else:
            opt_id, label = part, part
        out.append(CatalogOption(id=opt_id.strip(), label=label.strip()))
    return out


def _fetch_avatar_group_poses(group_id: str) -> list[CatalogOption]:
    if not settings.HEYGEN_API_KEY:
        return []
    base = settings.HEYGEN_BASE_URL.rstrip("/")
    url = f"{base}/v2/avatar_group/{group_id}/avatars"
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(url, headers={"X-Api-Key": settings.HEYGEN_API_KEY})
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("HeyGen avatar group %s lookup failed: %s", group_id, exc)
        return []

    data = payload.get("data") if isinstance(payload, dict) else None
    avatars = []
    if isinstance(data, dict):
        avatars = data.get("avatars") or data.get("avatar_list") or []
    elif isinstance(data, list):
        avatars = data

    options: list[CatalogOption] = []
    for avatar in avatars:
        if not isinstance(avatar, dict):
            continue
        avatar_id = avatar.get("avatar_id") or avatar.get("id")
        if not avatar_id:
            continue
        name = avatar.get("avatar_name") or avatar.get("name") or str(avatar_id)
        gender = (avatar.get("gender") or "").strip().lower() or None
        gender_label = f" ({gender.title()})" if gender else ""
        options.append(
            CatalogOption(
                id=str(avatar_id),
                label=f"{name}{gender_label}",
                gender=gender,
            )
        )
    return options


def _fetch_v3_group_poses(option: CatalogOption) -> list[CatalogOption]:
    """Expand public avatar groups (e.g. Vespri) into selectable look ids."""
    looks = _fetch_v3_looks_for_group(option.id)
    if not looks:
        return []

    completed = [
        look
        for look in looks
        if look.get("id") and (look.get("status") or "completed").lower() == "completed"
    ]
    if not completed:
        completed = [look for look in looks if look.get("id")]
    if not completed:
        return []

    portrait_n = 0
    landscape_n = 0
    options: list[CatalogOption] = []
    parent_gender = (option.gender or "").strip().lower() or None

    for look in completed:
        look_id = str(look["id"])
        orient = (look.get("preferred_orientation") or "").strip().lower()
        if orient == "portrait":
            portrait_n += 1
            pos = f"Position {portrait_n} (portrait)"
        elif orient == "landscape":
            landscape_n += 1
            pos = f"Position {landscape_n} (landscape)"
        else:
            pos = f"Look {len(options) + 1}"

        gender = (look.get("gender") or "").strip().lower() or parent_gender
        options.append(
            CatalogOption(
                id=look_id,
                label=f"{option.label} — {pos}",
                gender=gender,
            )
        )
    return options


def _expand_avatar_option(option: CatalogOption) -> list[CatalogOption]:
    if re.fullmatch(r"\d+", option.id):
        poses = _fetch_avatar_group_poses(option.id)
        if poses:
            return [
                CatalogOption(
                    id=pose.id,
                    label=f"{option.label} — {pose.label}" if option.label else pose.label,
                    gender=pose.gender,
                )
                for pose in poses
            ]
    if _HEX_ID.match(option.id) and (
        option.id == VESPRI_GROUP_ID or "vespri" in option.label.lower()
    ):
        poses = _fetch_v3_group_poses(option)
        if poses:
            return poses
    return [option]


_AVATAR_CATALOG_CACHE: tuple[float, list[CatalogOption], list[CatalogOption]] | None = None
_AVATAR_CATALOG_LOCK = Lock()
_AVATAR_CATALOG_TTL_SEC = 3600


def get_heygen_avatar_catalog_split() -> tuple[list[CatalogOption], list[CatalogOption]]:
    """(featured standalone looks, expanded pose libraries). Cached — avoids slow HeyGen API on every page."""
    global _AVATAR_CATALOG_CACHE
    if not settings.HEYGEN_API_KEY:
        return [], []

    now = time.time()
    with _AVATAR_CATALOG_LOCK:
        if _AVATAR_CATALOG_CACHE and now - _AVATAR_CATALOG_CACHE[0] < _AVATAR_CATALOG_TTL_SEC:
            return _AVATAR_CATALOG_CACHE[1], _AVATAR_CATALOG_CACHE[2]
    featured: list[CatalogOption] = []
    poses: list[CatalogOption] = []
    for option in _parse_options(settings.HEYGEN_AVATAR_OPTIONS):
        expanded = _expand_avatar_option(option)
        if len(expanded) == 1 and expanded[0].id == option.id:
            featured.append(expanded[0])
        else:
            poses.extend(expanded)
    if not featured and not poses and settings.HEYGEN_AVATAR_ID:
        featured.append(
            CatalogOption(id=str(settings.HEYGEN_AVATAR_ID), label="Default avatar")
        )
    featured = [o for o in featured if "vespri" not in o.label.lower()]
    has_vespri_poses = any("vespri" in p.label.lower() for p in poses)
    if not has_vespri_poses:
        featured.insert(0, VESPRI_CATALOG)
    with _AVATAR_CATALOG_LOCK:
        _AVATAR_CATALOG_CACHE = (now, featured, poses)
    logger.info(
        "HeyGen avatar catalog built (%d featured, %d poses)",
        len(featured),
        len(poses),
    )
    return featured, poses


def get_heygen_avatar_featured() -> list[CatalogOption]:
    featured, _ = get_heygen_avatar_catalog_split()
    return featured


def get_heygen_avatar_options() -> list[CatalogOption]:
    featured, poses = get_heygen_avatar_catalog_split()
    return featured + poses


def get_heygen_voice_options() -> list[CatalogOption]:
    if not settings.HEYGEN_API_KEY:
        return []
    options = _parse_options(settings.HEYGEN_VOICE_OPTIONS)
    if not options and settings.HEYGEN_VOICE_ID:
        options.append(CatalogOption(id=settings.HEYGEN_VOICE_ID, label="Default voice"))
    return options


def _heygen_headers() -> dict[str, str]:
    return {"X-Api-Key": settings.HEYGEN_API_KEY}


def _fetch_v3_looks_for_group(group_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
    if not settings.HEYGEN_API_KEY:
        return []
    base = settings.HEYGEN_BASE_URL.rstrip("/")
    url = f"{base}/v3/avatars/looks"
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(
                url,
                headers=_heygen_headers(),
                params={"group_id": group_id, "limit": limit},
            )
            response.raise_for_status()
            payload = response.json()
    except Exception as exc:
        logger.warning("HeyGen v3 looks for group %s failed: %s", group_id[:12], exc)
        return []

    data = payload.get("data") if isinstance(payload, dict) else None
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    return []


def _fetch_v3_look_by_id(look_id: str) -> dict[str, Any] | None:
    if not settings.HEYGEN_API_KEY:
        return None
    base = settings.HEYGEN_BASE_URL.rstrip("/")
    try:
        with httpx.Client(timeout=60.0) as client:
            response = client.get(
                f"{base}/v3/avatars/looks/{look_id}",
                headers=_heygen_headers(),
            )
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json().get("data")
            return data if isinstance(data, dict) else None
    except Exception as exc:
        logger.warning("HeyGen v3 look %s lookup failed: %s", look_id[:12], exc)
        return None


def _pick_v3_look_id(looks: list[dict[str, Any]], *, prefer_portrait: bool) -> str:
    candidates = [
        look
        for look in looks
        if look.get("id") and (look.get("status") or "completed").lower() == "completed"
    ]
    if not candidates:
        candidates = [look for look in looks if look.get("id")]
    if not candidates:
        raise ValueError("HeyGen returned no usable looks for this avatar group")

    if prefer_portrait:
        for look in candidates:
            if (look.get("preferred_orientation") or "").lower() == "portrait":
                return str(look["id"])
    return str(candidates[0]["id"])


def resolve_heygen_avatar_id(
    avatar_id: str | None,
    *,
    prefer_portrait: bool = True,
) -> str:
    """Map UI/env ids to a v3-ready look id (HeyGen Video Agent `avatar_id`)."""
    look_id, _ = resolve_heygen_avatar_and_voice(avatar_id, prefer_portrait=prefer_portrait)
    return look_id


def resolve_heygen_avatar_and_voice(
    avatar_id: str | None,
    *,
    prefer_portrait: bool = True,
) -> tuple[str, str | None]:
    """
    Resolve catalog selection to API look id + optional default voice.

    - Numeric ids: v2 avatar group → first pose id.
    - 32-char hex from HeyGen URL: usually *group_id* → GET /v3/avatars/looks?group_id=.
    - Other hex ids: try as look id via GET /v3/avatars/looks/{id}.
    """
    raw = (avatar_id or settings.HEYGEN_AVATAR_ID or "").strip()
    if not raw:
        raise ValueError("HeyGen avatar is not configured")

    if re.fullmatch(r"\d+", raw):
        poses = _fetch_avatar_group_poses(raw)
        if not poses:
            raise ValueError(
                f"HeyGen avatar group {raw} has no poses — pick Sofia/Florin from the pose dropdown"
            )
        return poses[0].id, None

    if _HEX_ID.match(raw) or (len(raw) >= 20 and not raw.isdigit()):
        looks = _fetch_v3_looks_for_group(raw)
        if looks:
            look_id = _pick_v3_look_id(looks, prefer_portrait=prefer_portrait)
            voice = next(
                (str(l["default_voice_id"]) for l in looks if l.get("id") == look_id and l.get("default_voice_id")),
                None,
            )
            logger.info(
                "HeyGen resolved group %s → look %s (portrait=%s)",
                raw[:12],
                look_id[:12],
                prefer_portrait,
            )
            return look_id, voice

        existing = _fetch_v3_look_by_id(raw)
        if existing and existing.get("id"):
            voice = existing.get("default_voice_id")
            return str(existing["id"]), str(voice) if voice else None

        raise ValueError(
            f"HeyGen avatar '{raw[:12]}…' was not found. For Vespri use group id "
            f"{VESPRI_GROUP_ID} from the HeyGen public avatar URL, then restart the backend."
        )

    return raw, None
