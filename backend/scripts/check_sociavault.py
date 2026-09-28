"""Quick SociaVault credit / connectivity check."""
import asyncio
import sys

from app.services.competitor_discovery_service import discover_competitor_candidates
from app.services.sociavault_client import fetch_facebook_profile, fetch_instagram_profile


async def main() -> None:
    for label, coro in [
        ("instagram", fetch_instagram_profile("nike")),
        ("facebook", fetch_facebook_profile("nike")),
    ]:
        try:
            profile = await coro
            name = ""
            if isinstance(profile, dict):
                name = str(
                    profile.get("full_name")
                    or profile.get("username")
                    or profile.get("name")
                    or ""
                ).strip()
            print(f"{label}: OK" + (f" ({name})" if name else ""))
        except Exception as exc:
            print(f"{label}: FAIL - {exc}")
            sys.exit(1)

    if "--discover" in sys.argv:
        try:
            candidates = await discover_competitor_candidates(
                brand_name="Melbourne Mortgage Co",
                industry="Mortgage broker",
                niche="Home loans",
                geography="Melbourne VIC",
                client_handle_or_url="https://www.instagram.com/nike/",
                client_platform="instagram",
            )
            print(f"discover: OK ({len(candidates)} candidates)")
            if candidates:
                first = candidates[0]
                print(f"  first: {first.get('name')} @{first.get('handle')}")
        except Exception as exc:
            print(f"discover: FAIL - {exc}")
            sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
