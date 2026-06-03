"""Probe Runway veo3.1 image_to_video validation."""
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
    key = env["RUNWAYML_API_KEY"]
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Runway-Version": env.get("RUNWAYML_API_VERSION", "2024-11-06"),
    }
    base = env["RUNWAYML_BASE_URL"].rstrip("/")
    img = (
        "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/"
        "PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png"
    )
    payloads = [
        {
            "name": "valid_https",
            "body": {
                "model": "veo3.1",
                "promptImage": img,
                "ratio": "1080:1920",
                "duration": 8,
                "promptText": "Gentle camera push in, cinematic ad.",
            },
        },
        {
            "name": "bad_duration_10",
            "body": {
                "model": "veo3.1",
                "promptImage": img,
                "ratio": "1080:1920",
                "duration": 10,
                "promptText": "test",
            },
        },
        {
            "name": "missing_image",
            "body": {
                "model": "veo3.1",
                "ratio": "1080:1920",
                "duration": 8,
                "promptText": "test",
            },
        },
    ]
    with httpx.Client(timeout=60.0) as client:
        for item in payloads:
            r = client.post(f"{base}/image_to_video", headers=headers, json=item["body"])
            print(f"--- {item['name']} HTTP {r.status_code}")
            try:
                print(json.dumps(r.json(), indent=2)[:800])
            except Exception:
                print(r.text[:800])


if __name__ == "__main__":
    main()
