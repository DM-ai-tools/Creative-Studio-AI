"""Check Runway API credits / whether generation can run."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import httpx

BACKEND = Path(__file__).resolve().parents[1]
ENV = BACKEND / ".env"


def load_env() -> dict[str, str]:
    values: dict[str, str] = {}
    for line in ENV.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def main() -> int:
    env = load_env()
    key = env.get("RUNWAYML_API_KEY", "")
    version = env.get("RUNWAYML_API_VERSION", "2024-11-06")
    base = env.get("RUNWAYML_BASE_URL", "https://api.dev.runwayml.com/v1").rstrip("/")

    if not key:
        print(json.dumps({"ok": False, "error": "RUNWAYML_API_KEY missing in backend/.env"}, indent=2))
        return 1

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-Runway-Version": version,
    }

    report: dict = {
        "api_key_present": True,
        "api_key_suffix": key[-4:] if len(key) >= 4 else "****",
    }

    with httpx.Client(timeout=30.0) as client:
        for path in ["/organization", "/credits", "/account", "/tasks?limit=1"]:
            try:
                r = client.get(f"{base}{path}", headers=headers)
                report[f"GET {path}"] = {"status": r.status_code, "body": r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text[:500]}
            except Exception as exc:
                report[f"GET {path}"] = {"error": str(exc)}

        probe = client.post(
            f"{base}/text_to_image",
            headers=headers,
            json={
                "model": env.get("RUNWAYML_MODEL_IMAGE", "gemini_image3.1_flash"),
                "promptText": "Credit check probe — simple gray square product photo",
                "ratio": "1024:1024",
            },
        )
        probe_body = probe.json() if probe.headers.get("content-type", "").startswith("application/json") else {"raw": probe.text[:500]}
        report["generation_probe"] = {
            "status": probe.status_code,
            "body": probe_body,
        }

        if probe.status_code == 200 or probe.status_code == 201:
            task_id = probe_body.get("id") if isinstance(probe_body, dict) else None
            report["credits_ok"] = True
            report["message"] = "Credits available — test image task accepted by Runway."
            if task_id:
                report["test_task_id"] = task_id
                report["note"] = "A small test task was submitted; cancel in Runway dashboard if you want to avoid using credits."
        elif isinstance(probe_body, dict) and "not enough credits" in str(probe_body.get("error", "")).lower():
            report["credits_ok"] = False
            report["message"] = "No Runway API credits. Add credits at https://dev.runwayml.com/"
        elif probe.status_code == 400 and "validation" in str(probe_body).lower():
            report["credits_ok"] = None
            report["message"] = "Payload validation failed — fix config before credits can be tested."
        else:
            report["credits_ok"] = None
            report["message"] = f"Unexpected response (HTTP {probe.status_code}). See generation_probe."

    print(json.dumps(report, indent=2, default=str))
    return 0 if report.get("credits_ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
