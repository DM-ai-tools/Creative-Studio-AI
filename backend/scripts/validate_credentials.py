"""Validate Meta and media generation credentials without printing secrets."""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

BACKEND_ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = BACKEND_ROOT / ".env"


def mask(value: str | None) -> str:
    if not value:
        return "(missing)"
    value = value.strip().strip('"').strip("'")
    if len(value) <= 4:
        return "****"
    return f"{'*' * max(8, len(value) - 4)}{value[-4:]}"


def load_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def check_presence(env: dict[str, str], key: str) -> dict:
    value = env.get(key, "").strip()
    return {
        "key": key,
        "present": bool(value),
        "masked": mask(value),
        "length": len(value),
    }


def validate_meta(env: dict[str, str]) -> dict:
    app_id = env.get("META_APP_ID", "").strip()
    app_secret = env.get("META_APP_SECRET", "").strip()
    access_token = env.get("META_ACCESS_TOKEN", "").strip()
    graph_version = env.get("META_GRAPH_API_VERSION", "v21.0").strip() or "v21.0"
    ad_account_id = env.get("META_AD_ACCOUNT_ID", "").strip()

    report: dict = {
        "variables": [
            check_presence(env, "META_APP_ID"),
            check_presence(env, "META_APP_SECRET"),
            check_presence(env, "META_ACCESS_TOKEN"),
            check_presence(env, "META_GRAPH_API_VERSION"),
            check_presence(env, "META_AD_ACCOUNT_ID"),
        ],
        "format_checks": [],
        "api_checks": {},
    }

    if app_id and not app_id.isdigit():
        report["format_checks"].append({"check": "META_APP_ID numeric", "status": "invalid"})
    elif app_id:
        report["format_checks"].append({"check": "META_APP_ID numeric", "status": "valid"})

    if access_token and not re.match(r"^[A-Za-z0-9._-]+$", access_token):
        report["format_checks"].append({"check": "META_ACCESS_TOKEN charset", "status": "invalid"})
    elif access_token:
        report["format_checks"].append({"check": "META_ACCESS_TOKEN charset", "status": "valid"})

    if not (app_id and app_secret and access_token):
        report["api_checks"]["summary"] = "skipped_missing_credentials"
        return report

    base = f"https://graph.facebook.com/{graph_version}"
    app_access_token = f"{app_id}|{app_secret}"

    try:
        with httpx.Client(timeout=30.0) as client:
            app_token_response = client.get(
                f"{base}/oauth/access_token",
                params={
                    "client_id": app_id,
                    "client_secret": app_secret,
                    "grant_type": "client_credentials",
                },
            )
            app_token_body = app_token_response.json()
            report["api_checks"]["app_credentials"] = {
                "http_status": app_token_response.status_code,
                "error": app_token_body.get("error"),
                "token_type": app_token_body.get("token_type"),
                "has_access_token": bool(app_token_body.get("access_token")),
            }

            debug_response = client.get(
                f"{base}/debug_token",
                params={"input_token": access_token, "access_token": app_access_token},
            )
            debug_body = debug_response.json()
            report["api_checks"]["debug_token"] = {
                "http_status": debug_response.status_code,
                "error": debug_body.get("error"),
                "data": debug_body.get("data"),
            }

            me_response = client.get(
                f"{base}/me",
                params={"fields": "id,name", "access_token": access_token},
            )
            me_body = me_response.json()
            report["api_checks"]["me"] = {
                "http_status": me_response.status_code,
                "error": me_body.get("error"),
                "id": me_body.get("id"),
                "name": me_body.get("name"),
            }

            permissions_response = client.get(
                f"{base}/me/permissions",
                params={"access_token": access_token},
            )
            permissions_body = permissions_response.json()
            granted = [
                item.get("permission")
                for item in permissions_body.get("data", [])
                if item.get("status") == "granted"
            ]
            report["api_checks"]["permissions"] = {
                "http_status": permissions_response.status_code,
                "error": permissions_body.get("error"),
                "granted": granted,
            }

            if ad_account_id:
                account_response = client.get(
                    f"{base}/{ad_account_id}",
                    params={"fields": "id,name,account_status", "access_token": access_token},
                )
                account_body = account_response.json()
                report["api_checks"]["ad_account"] = {
                    "http_status": account_response.status_code,
                    "error": account_body.get("error"),
                    "id": account_body.get("id"),
                    "name": account_body.get("name"),
                    "account_status": account_body.get("account_status"),
                }
    except httpx.HTTPError as exc:
        report["api_checks"]["summary"] = "network_failure"
        report["api_checks"]["error"] = str(exc)

    return report


def validate_runway(env: dict[str, str]) -> dict:
    api_key = env.get("RUNWAYML_API_KEY", "").strip()
    base_url = env.get("RUNWAYML_BASE_URL", "https://api.dev.runwayml.com/v1").strip()
    api_version = env.get("RUNWAYML_API_VERSION", "2024-11-06").strip()
    image_model = env.get("RUNWAYML_MODEL_IMAGE", "").strip()
    video_model = env.get("RUNWAYML_MODEL_VIDEO", "").strip()

    report = {
        "variables": [
            check_presence(env, "RUNWAYML_API_KEY"),
            check_presence(env, "RUNWAYML_BASE_URL"),
            check_presence(env, "RUNWAYML_API_VERSION"),
            check_presence(env, "RUNWAYML_MODEL_IMAGE"),
            check_presence(env, "RUNWAYML_MODEL_VIDEO"),
        ],
        "checks": {},
    }

    if not api_key:
        report["checks"]["summary"] = "skipped_missing_api_key"
        return report

    headers = {
        "Authorization": f"Bearer {api_key}",
        "X-Runway-Version": api_version,
    }
    try:
        with httpx.Client(timeout=30.0) as client:
            # Lightweight probe: list tasks endpoint (401/403 vs 200 indicates key validity).
            tasks_response = client.get(f"{base_url.rstrip('/')}/tasks", headers=headers, params={"limit": 1})
            report["checks"]["tasks_list"] = {
                "http_status": tasks_response.status_code,
                "ok": tasks_response.status_code < 400,
                "body_preview": tasks_response.text[:200] if tasks_response.status_code >= 400 else None,
            }
            report["checks"]["configured_models"] = {
                "image": image_model or "(default gemini_image3.1_flash / Nano Banana 2)",
                "video": video_model or "(default veo3.1)",
            }
    except httpx.HTTPError as exc:
        report["checks"]["summary"] = "network_failure"
        report["checks"]["error"] = str(exc)

    return report


def validate_media(env: dict[str, str]) -> dict:
    return {
        "active": "runway",
        "note": "Image and video via Runway ML. Ad copy is generated from the brief.",
        "runway": validate_runway(env),
    }


def main() -> int:
    env = load_env(ENV_PATH)
    payload = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "env_path": str(ENV_PATH),
        "meta": validate_meta(env),
        "media": validate_media(env),
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
