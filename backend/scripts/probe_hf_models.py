"""One-off probe for Higgsfield platform model paths. Run: HF_API_KEY=... HF_API_SECRET=... python scripts/probe_hf_models.py"""
import asyncio
import os

import httpx
import higgsfield_client

# Curated from docs + probes (HIT = valid path, credits or validation error)
IMAGE_PATHS = [
    "flux-pro/kontext/max/text-to-image",
    "flux-pro/kontext/pro/text-to-image",
    "flux-pro/2/pro/text-to-image",
    "google/nano-banana-pro/text-to-image",
    "google/nano-banana-2/text-to-image",
    "nano-banana-pro/text-to-image",
    "nano-banana-2/text-to-image",
    "bytedance/seedream/v4.5/text-to-image",
    "bytedance/seedream/v5-lite/text-to-image",
    "openai/gpt-image-2/text-to-image",
    "/v1/text2image/soul",
    "higgsfield-ai/soul/standard",
    "higgsfield-ai/soul/v2/standard",
    "reve/text-to-image",
    "bytedance/seedream/v4/text-to-image",
    "black-forest-labs/flux-2-pro/text-to-image",
    "black-forest-labs/flux-kontext-pro/text-to-image",
    "openai/gpt-image-1.5/text-to-image",
    "google/imagen3/text-to-image",
    "google/gemini-flash/text-to-image",
    "xai/grok-2-image/text-to-image",
    "kling-image/v1/text-to-image",
    "higgsfield-ai/z-image/standard",
    "higgsfield-ai/image-auto/standard",
]

VIDEO_PATHS = [
    "/v1/image2video/dop",
    "higgsfield-ai/dop/standard",
    "higgsfield-ai/dop/turbo",
    "higgsfield-ai/dop/preview",
    "kling-video/v2.1/pro/image-to-video",
    "kling-video/v3.0/pro/image-to-video",
    "bytedance/seedance/v1/pro/image-to-video",
    "bytedance/seedance/v2/pro/image-to-video",
    "google/veo3/image-to-video",
    "google/veo3.1/image-to-video",
    "google/veo3.1-fast/image-to-video",
    "minimax/video-01/image-to-video",
    "wanx/v2.6/image-to-video",
    "wanx/v2.7/image-to-video",
    "xai/grok-video/image-to-video",
]


async def probe(path: str, video: bool) -> str:
    args: dict = {"prompt": "product hero shot", "aspect_ratio": "16:9"}
    if video:
        args = {
            "prompt": "slow cinematic pan",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png",
            "duration": 5,
            "aspect_ratio": "16:9",
        }
    try:
        await higgsfield_client.submit_async(path, args)
        return "HIT"
    except Exception as exc:
        msg = str(exc)
        if "Model not found" in msg or "not found" in msg.lower():
            return "miss"
        if "not_enough_credits" in msg or "literal_error" in msg or "required property" in msg:
            return "HIT"
        return f"err:{msg[:80]}"


async def main() -> None:
    if not os.getenv("HF_API_KEY"):
        print("Set HF_API_KEY and HF_API_SECRET")
        return
    print("=== IMAGE ===")
    for p in IMAGE_PATHS:
        print(await probe(p, False), p)
    print("=== VIDEO ===")
    for p in VIDEO_PATHS:
        print(await probe(p, True), p)


JOB_SET_TYPES = [
    "nano_banana_2",
    "nano_banana_flash",
    "nano_banana",
    "flux_2",
    "flux_kontext",
    "gpt_image_2",
    "text2image_soul_v2",
    "seedream_v4_5",
    "seedream_v5_lite",
    "grok_image",
    "openai_hazel",
    "image_auto",
    "z_image",
    "kling_omni_image",
    "cinematic_studio_2_5",
    "soul_cinematic",
    "soul_location",
    "marketing_studio_image",
    "veo3_1",
    "veo3_1_lite",
    "veo3",
    "kling3_0",
    "kling2_6",
    "seedance_2_0",
    "seedance1_5",
    "wan2_7",
    "wan2_6",
    "minimax_hailuo",
    "grok_video",
    "cinematic_studio_3_0",
    "cinematic_studio_video",
    "cinematic_studio_video_v2",
    "soul_cast",
    "marketing_studio_video",
]


async def probe_job_types() -> None:
    print("=== JOB SET TYPE PATHS ===")
    for job in JOB_SET_TYPES:
        video = job in {
            "veo3_1",
            "veo3_1_lite",
            "veo3",
            "kling3_0",
            "kling2_6",
            "seedance_2_0",
            "seedance1_5",
            "wan2_7",
            "wan2_6",
            "minimax_hailuo",
            "grok_video",
            "cinematic_studio_3_0",
            "cinematic_studio_video",
            "cinematic_studio_video_v2",
            "soul_cast",
            "marketing_studio_video",
        }
        candidates = [
            job,
            job.replace("_", "-"),
            f"higgsfield-ai/{job}",
            f"higgsfield-ai/{job.replace('_', '-')}",
            f"higgsfield-ai/{job}/standard",
            f"higgsfield-ai/{job.replace('_', '-')}/standard",
        ]
        for path in candidates:
            status = await probe(path, video)
            if status == "HIT":
                print("HIT", job, "->", path)
                break


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(probe_job_types())
