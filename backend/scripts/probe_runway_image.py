"""Probe Runway text_to_image validation for gemini_image3.1_flash."""
from __future__ import annotations

import json
from pathlib import Path

import httpx

ENV = Path(__file__).resolve().parents[1] / ".env"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> None:
    env = load_env()
    headers = {
        "Authorization": f"Bearer {env['RUNWAYML_API_KEY']}",
        "Content-Type": "application/json",
        "X-Runway-Version": env.get("RUNWAYML_API_VERSION", "2024-11-06"),
    }
    base = env["RUNWAYML_BASE_URL"].rstrip("/")
    prompt = "Professional dental clinic ad, bright smile, navy and white brand colors."
    cases = [
        {
            "name": "aspect_9_16_1k",
            "body": {
                "model": "gemini_image3.1_flash",
                "promptText": prompt,
                "ratio": "9:16",
                "imageSize": "1K",
            },
        },
        {
            "name": "pixel_768_1344",
            "body": {
                "model": "gemini_image3.1_flash",
                "promptText": prompt,
                "ratio": "768:1344",
            },
        },
        {
            "name": "bad_1080_1920",
            "body": {
                "model": "gemini_image3.1_flash",
                "promptText": prompt,
                "ratio": "1080:1920",
            },
        },
    ]
    with httpx.Client(timeout=60.0) as client:
        for item in cases:
            r = client.post(f"{base}/text_to_image", headers=headers, json=item["body"])
            print(f"--- {item['name']} HTTP {r.status_code}")
            try:
                print(json.dumps(r.json(), indent=2)[:600])
            except Exception:
                print(r.text[:600])


if __name__ == "__main__":
    main()
