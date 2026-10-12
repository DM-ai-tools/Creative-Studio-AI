from app.services.creative_studio_clone import (
    clone_scene_groups,
    clone_scenes,
    compile_clone_prompt,
)
from app.services.media.openai_image_provider import OpenAIImageProvider
from app.services.creative_studio_chat_service import run_creative_studio_chat_turn

import pytest


def test_clone_catalog_exposes_all_fifty_scenes():
    scenes = clone_scenes()
    catalog = clone_scene_groups()

    assert len(scenes) == 50
    assert len(catalog["categories"]) == 5
    assert len(catalog["scenes"]) == 50
    assert len({scene["id"] for scene in scenes}) == 50


def test_clone_prompt_locks_identity_count_and_text_free_output():
    prompt = compile_clone_prompt(
        user_prompt="Use a premium cinematic office lighting setup.",
        scene_id=clone_scenes()[0]["id"],
        clone_count=5,
    )

    assert "exactly 5 separate copies" in prompt
    assert "exact same facial identity" in prompt
    assert "no extra people" in prompt
    assert "No captions, logos, watermarks or readable text" in prompt


def test_clone_count_is_safely_clamped():
    prompt = compile_clone_prompt(user_prompt="Boardroom", scene_id="", clone_count=99)
    assert "exactly 6 separate copies" in prompt


@pytest.mark.asyncio
async def test_openai_clone_sends_every_character_reference(monkeypatch):
    from app.services.media import openai_image_provider as module

    captured: dict = {}

    class Response:
        status_code = 200
        text = ""

    class Client:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            captured["files"] = kwargs.get("files")
            captured["data"] = kwargs.get("data")
            return Response()

    async def save_result(self, *args, **kwargs):
        return {"status": "done", "url": "/files/tenant/generated/clone.png"}

    monkeypatch.setattr(module, "openai_configured", lambda: True)
    monkeypatch.setattr(module.httpx, "AsyncClient", Client)
    monkeypatch.setattr(OpenAIImageProvider, "_save_response_image", save_result)

    one_pixel = "data:image/png;base64,iVBORw0KGgo="
    result = await OpenAIImageProvider().generate(
        prompt="Boardroom scene",
        tenant_id="tenant",
        model="openai-gpt-image-2",
        format_type="static",
        reference_image_urls=[one_pixel, one_pixel.replace("go=", "go==")],
        reference_purpose="character",
    )

    assert result["status"] == "done"
    assert len(captured["files"]) == 2
    assert all(field == "image[]" for field, _ in captured["files"])
    assert captured["data"]["input_fidelity"] == "high"


@pytest.mark.asyncio
async def test_clone_without_photo_queues_identity_first(monkeypatch):
    from app.services import creative_studio_chat_service as chat_module
    from app.services.media import openai_image_catalog

    captured: dict = {}

    async def start_job(**kwargs):
        captured.update(kwargs)
        return "clone-job"

    monkeypatch.setattr(openai_image_catalog, "openai_configured", lambda: True)
    monkeypatch.setattr(chat_module, "_start_job", start_job)

    result = await run_creative_studio_chat_turn(
        tenant_id="tenant",
        messages=[
            {
                "role": "user",
                "content": "Create a white Australian woman aged 28 to 32 in a modern office",
            }
        ],
        action="generate_image",
        image_prompt="Create a white Australian woman aged 28 to 32 in a modern office",
        clone_mode=True,
        clone_count=2,
        prompt_only_video=False,
        reference_assets=[],
    )

    assert result["status"] == "queued"
    assert captured["clone_mode"] is True
    assert captured["clone_count"] == 2
    assert "Australian woman" in captured["clone_identity_prompt"]
    assert "exactly 2 separate copies" in captured["prompt"]
