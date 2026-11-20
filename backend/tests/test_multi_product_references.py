import inspect

from app.services import generation_job as gj
from app.services.ai_service import ai_service


def _slot(*urls):
    return {"reference_images": [{"file_url": u} for u in urls]}


def test_every_product_photo_of_a_variant_is_sent_to_the_model_in_order():
    urls = gj._variant_reference_image_urls({}, _slot("/files/a.png", "/files/b.png", "/files/a.png", "/files/c.png"))
    assert urls == ["/files/a.png", "/files/b.png", "/files/c.png"]


def test_without_variant_photos_nothing_is_sent_unless_the_brief_has_an_exact_product_photo():
    assert gj._variant_reference_image_urls({}, {}) == []
    kb = {"exact_product_reference": True, "reference_images": [{"is_product_reference": True, "file_url": "/files/p.png"}]}
    assert gj._variant_reference_image_urls(kb, {}) == ["/files/p.png"]


def test_the_image_service_and_openai_provider_accept_a_list_of_references():
    assert "reference_image_urls" in inspect.signature(ai_service.generate_image_asset).parameters
    from app.services.media.openai_image_provider import OpenAIImageProvider

    assert "reference_image_urls" in inspect.signature(OpenAIImageProvider.generate).parameters


def test_the_variant_list_keeps_the_logo_details_the_tile_needs():
    from app.schemas.variant import slim_generation_params_for_list

    image = {"status": "done", "url": "/files/a.png", "prompt": "x" * 900, "url_without_logo": "/files/b.png",
             "logo_applied": True, "logo_corner": "top_right", "logo_backing": "plate"}
    slim = slim_generation_params_for_list({"pipeline": {"image": image}})["pipeline"]["image"]
    assert slim["url_without_logo"] == "/files/b.png" and slim["logo_corner"] == "top_right" and slim["logo_applied"] is True
    assert "prompt" not in slim
