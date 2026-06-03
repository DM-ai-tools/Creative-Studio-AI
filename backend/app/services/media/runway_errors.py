"""Parse Runway API errors into short user-facing messages."""

from __future__ import annotations

import json
import re


def format_runway_error(exc: Exception) -> str:
    raw = str(exc)
    if "not enough credits" in raw.lower():
        return "Runway credits exhausted. Add credits at https://dev.runwayml.com/"
    if "high load" in raw.lower() or '"code":8' in raw.lower():
        return (
            "Runway Veo is temporarily overloaded. Wait a few minutes and regenerate — "
            "the app will auto-retry up to 3 times on the next run."
        )
    if "aspect ratio" in raw.lower() and "promptimage" in raw.lower():
        return "Video source image aspect ratio rejected by Runway. Regenerate after the latest fix, or try again."
    if "validation of body failed" in raw.lower() and "duration" in raw.lower():
        return (
            "Runway rejected the video request (often duration). "
            "Veo 3.1 only allows 4, 6, or 8 seconds — pick one of those in Video duration, then regenerate."
        )

    json_match = re.search(r"\{.*\}", raw, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
        except json.JSONDecodeError:
            return raw[:240]

        if isinstance(data, dict):
            if data.get("error"):
                return str(data["error"])[:240]
            issues = data.get("issues")
            if isinstance(issues, list) and issues:
                parts = []
                for issue in issues[:2]:
                    if not isinstance(issue, dict):
                        continue
                    path = ".".join(str(p) for p in (issue.get("path") or []))
                    message = issue.get("message") or issue.get("code")
                    if path and message:
                        parts.append(f"{path}: {message}")
                    elif message:
                        parts.append(str(message))
                if parts:
                    msg = "; ".join(parts)[:240]
                    if "too_big" in msg.lower() or "too big" in msg.lower():
                        return "Image prompt too long for Runway (max 1000 characters). Try a shorter brand voice in Brand Kit."
                    return msg

    if "too_big" in raw.lower() and "prompttext" in raw.lower():
        return "Image prompt too long for Runway (max 1000 characters)."

    return raw[:240]
