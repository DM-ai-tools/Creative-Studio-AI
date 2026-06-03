"""Map CLI job_set_type -> platform.higgsfield.ai path."""
import asyncio
import os

import higgsfield_client

IMAGE_JOBS = [
    ("nano_banana_2", "Nano Banana Pro"),
    ("nano_banana_flash", "Nano Banana 2"),
    ("nano_banana", "Nano Banana"),
    ("flux_2", "FLUX.2"),
    ("flux_kontext", "Flux Kontext"),
    ("gpt_image_2", "GPT Image 2"),
    ("text2image_soul_v2", "Higgsfield Soul V2"),
    ("seedream_v4_5", "Seedream 4.5"),
    ("seedream_v5_lite", "Seedream V5 Lite"),
    ("grok_image", "Grok Image"),
    ("openai_hazel", "OpenAI Hazel"),
    ("image_auto", "Image Auto"),
    ("z_image", "Z Image"),
    ("kling_omni_image", "Kling O1 Image"),
    ("cinematic_studio_2_5", "Cinematic Studio 2.5"),
    ("soul_cinematic", "Soul Cinematic"),
    ("soul_location", "Soul Location"),
    ("marketing_studio_image", "Marketing Studio Image"),
]

VIDEO_JOBS = [
    ("veo3_1", "Google Veo 3.1"),
    ("veo3_1_lite", "Google Veo 3.1 Lite"),
    ("veo3", "Google Veo 3"),
    ("kling3_0", "Kling v3.0"),
    ("kling2_6", "Kling 2.6 Video"),
    ("seedance_2_0", "Seedance 2.0"),
    ("seedance1_5", "Seedance 1.5 Pro"),
    ("wan2_7", "Wan 2.7"),
    ("wan2_6", "Wan 2.6 Video"),
    ("minimax_hailuo", "Minimax Hailuo"),
    ("grok_video", "Grok Video"),
    ("cinematic_studio_3_0", "Cinematic Studio 3.0"),
    ("cinematic_studio_video", "Cinematic Studio Video"),
    ("cinematic_studio_video_v2", "Cinematic Studio Video V2"),
    ("soul_cast", "Soul Cast"),
    ("marketing_studio_video", "Marketing Studio Video"),
]

KNOWN = {
    "text2image_soul_v2": "higgsfield-ai/soul/v2/standard",
    "flux_2": "flux-2",
    "flux_kontext": "flux-kontext",
    "marketing_studio_video": "marketing-studio-video",
    "kling3_0": "kling-video/v3.0/pro/image-to-video",
    "kling2_6": "kling-video/v2.1/pro/image-to-video",
}


def _candidates(job: str) -> list[str]:
    hy = job.replace("_", "-")
    return [
        KNOWN.get(job, ""),
        hy,
        f"higgsfield-ai/{hy}",
        f"higgsfield-ai/{hy}/standard",
        f"higgsfield-ai/soul/standard" if job == "text2image_soul_v2" else "",
        "reve/text-to-image" if job == "image_auto" else "",
        "higgsfield-ai/dop/standard" if "video" in job or job.startswith("veo") or job.startswith("seedance") else "",
    ]


async def _probe(path: str, video: bool) -> bool:
    if not path:
        return False
    args: dict = {"prompt": "test", "aspect_ratio": "16:9"}
    if video:
        args = {
            "prompt": "pan",
            "image_url": "https://upload.wikimedia.org/wikipedia/commons/thumb/4/47/PNG_transparency_demonstration_1.png/280px-PNG_transparency_demonstration_1.png",
            "duration": 5,
            "aspect_ratio": "16:9",
        }
    try:
        await higgsfield_client.submit_async(path, args)
        return True
    except Exception as exc:
        msg = str(exc)
        return (
            "not_enough_credits" in msg
            or "literal_error" in msg
            or "required property" in msg
            or "enum" in msg
        )


async def main() -> None:
    if not os.getenv("HF_API_KEY"):
        print("Set HF_API_KEY / HF_API_SECRET")
        return
    print("IMAGE:")
    for job, label in IMAGE_JOBS:
        for path in _candidates(job):
            if await _probe(path, False):
                print(f"  {job:30} -> {path}")
                break
        else:
            print(f"  {job:30} -> ???")
    print("VIDEO:")
    for job, label in VIDEO_JOBS:
        for path in _candidates(job):
            if await _probe(path, True):
                print(f"  {job:30} -> {path}")
                break
        else:
            print(f"  {job:30} -> ???")


EXTRA = [
    "nano-banana-pro",
    "nano-banana-2",
    "nano-banana-flash",
    "nano-banana",
    "gpt-image-2",
    "seedream-v4-5",
    "seedream-v5-lite",
    "grok-image",
    "openai-hazel",
    "z-image",
    "kling-omni-image",
    "cinematic-studio-2-5",
    "soul-cinematic",
    "soul-location",
    "marketing-studio-image",
    "veo3-1",
    "veo3-1-lite",
    "veo3",
    "seedance-2-0",
    "seedance-1-5",
    "wan2-7",
    "wan2-6",
    "minimax-hailuo",
    "grok-video",
    "cinematic-studio-3-0",
    "cinematic-studio-video",
    "cinematic-studio-video-v2",
    "soul-cast",
    "google/nano-banana-2/text-to-image",
    "bytedance/seedream/v4.5/text-to-image",
    "openai/gpt-image-2/text-to-image",
    "wan-ai/wan-2.7/image-to-video",
    "minimax/hailuo-2.3/image-to-video",
    "google/veo-3.1/image-to-video",
    "bytedance/seedance-2.0/image-to-video",
]


async def probe_extra() -> None:
    print("EXTRA:")
    for path in EXTRA:
        video = any(
            x in path
            for x in ("video", "veo", "seedance", "wan", "hailuo", "dop", "kling-video")
        )
        if await _probe(path, video):
            print("  HIT", path)


if __name__ == "__main__":
    asyncio.run(main())
    asyncio.run(probe_extra())
