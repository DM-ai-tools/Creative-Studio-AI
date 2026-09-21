"""Probe why Seedance is unavailable on this Higgsfield account."""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.config import settings

os.environ["HF_API_KEY"] = (settings.HIGGSFIELD_API_KEY or "").strip()
os.environ["HF_API_SECRET"] = (settings.HIGGSFIELD_API_SECRET or "").strip()

import higgsfield_client  # noqa: E402
import httpx  # noqa: E402

IMG = (
    "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/"
    "PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"
)

SEEDANCE_PATHS = [
    "bytedance/seedance/v1/pro/image-to-video",
    "bytedance/seedance/v1/pro/text-to-video",
    "bytedance/seedance/v1.5/pro/image-to-video",
    "bytedance/seedance/v2/pro/image-to-video",
    "bytedance/seedance-1.5/image-to-video",
    "bytedance/seedance-2.0/image-to-video",
    "bytedance/seedance-2.0/text-to-video",
    "seedance-2-0",
    "seedance-1-5",
]

COMPARE = [
    "higgsfield-ai/dop/standard",
    "bytedance/seedance-2.0/image-to-video",
]


def classify(exc: BaseException) -> str:
    msg = str(exc).lower()
    if "model_not_found" in msg or "model not found" in msg:
        return "NOT_FOUND"
    if "model_disabled" in msg:
        return "DISABLED"
    if "not_enough_credits" in msg:
        return "EXISTS_NO_CREDITS"
    if "invalid_image" in msg:
        return "EXISTS_BAD_IMAGE"
    if "literal_error" in msg or "validation" in msg or "required" in msg:
        return "EXISTS_VALIDATION"
    return f"OTHER:{str(exc)[:100]}"


async def probe_submit(path: str) -> str:
    args = {
        "prompt": "slow pan of product",
        "image_url": IMG,
        "duration": 5,
        "aspect_ratio": "9:16",
    }
    try:
        await higgsfield_client.submit_async(path, args)
        return "SUBMIT_ACCEPTED"
    except Exception as exc:  # noqa: BLE001
        return classify(exc)


async def probe_http_lists() -> None:
    key = os.environ["HF_API_KEY"]
    secret = os.environ["HF_API_SECRET"]
    bases = [
        "https://platform.higgsfield.ai",
        "https://api.higgsfield.ai",
        "https://fnf.higgsfield.ai",
    ]
    headers = {
        "hf-api-key": key,
        "hf-secret": secret,
        "Content-Type": "application/json",
    }
    paths = ["/v1/models", "/v1/me", "/v1/credits", "/v1/applications"]
    async with httpx.AsyncClient(timeout=20.0) as client:
        for base in bases:
            for path in paths:
                url = base + path
                try:
                    r = await client.get(url, headers=headers)
                    body = r.text[:180].replace("\n", " ")
                    print(f"HTTP {r.status_code} {url} :: {body}")
                except Exception as exc:  # noqa: BLE001
                    print(f"HTTP ERR {url} :: {exc}")


async def main() -> None:
    print("=== credentials ===")
    print("key_len", len(os.environ.get("HF_API_KEY") or ""))
    print("secret_len", len(os.environ.get("HF_API_SECRET") or ""))
    print()
    print("=== Seedance paths ===")
    for path in SEEDANCE_PATHS:
        status = await probe_submit(path)
        print(f"{status:22} {path}")
    print()
    print("=== working controls ===")
    for path in COMPARE:
        status = await probe_submit(path)
        print(f"{status:22} {path}")
    print()
    print("=== list endpoints ===")
    await probe_http_lists()


if __name__ == "__main__":
    asyncio.run(main())
