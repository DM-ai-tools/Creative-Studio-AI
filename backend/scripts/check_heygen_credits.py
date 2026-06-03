"""Print HeyGen API wallet balance."""
import json
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402


def main() -> None:
    if not settings.HEYGEN_API_KEY:
        print("HEYGEN_API_KEY not set")
        return
    base = settings.HEYGEN_BASE_URL.rstrip("/")
    headers = {"X-Api-Key": settings.HEYGEN_API_KEY}
    for path in ("/v1/user/remaining_quota", "/v2/user/remaining_quota"):
        r = httpx.get(f"{base}{path}", headers=headers, timeout=30)
        print(f"{path} -> {r.status_code}")
        try:
            print(json.dumps(r.json(), indent=2)[:800])
        except Exception:
            print(r.text[:400])


if __name__ == "__main__":
    main()
