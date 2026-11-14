from app.services.media.openai_image_catalog import (
    OPENAI_IMAGE_DEFAULT_API_MODEL,
    OPENAI_IMAGE_DEFAULT_CATALOG_ID,
    openai_image_catalog_options,
    resolve_openai_image_model,
)


def test_default_catalog_id_resolves_to_sunburst_api_model():
    assert OPENAI_IMAGE_DEFAULT_CATALOG_ID == "openai-gpt-image-2.6-sunburst"
    assert OPENAI_IMAGE_DEFAULT_API_MODEL == "gpt-image-2.6-sunburst"
    assert resolve_openai_image_model(None) == "gpt-image-2.6-sunburst"
    assert resolve_openai_image_model("") == "gpt-image-2.6-sunburst"
    assert resolve_openai_image_model(OPENAI_IMAGE_DEFAULT_CATALOG_ID) == "gpt-image-2.6-sunburst"
    assert resolve_openai_image_model("gpt-image-2.6-sunburst") == "gpt-image-2.6-sunburst"


def test_catalog_lists_sunburst_first_when_openai_configured(monkeypatch):
    import app.services.media.openai_image_catalog as catalog

    monkeypatch.setattr(catalog, "openai_configured", lambda: True)
    monkeypatch.setattr(catalog, "_fetch_live_image_model_ids", lambda: [])
    options = openai_image_catalog_options()
    ids = [o.id for o in options]
    assert OPENAI_IMAGE_DEFAULT_CATALOG_ID in ids
    assert ids[0] == OPENAI_IMAGE_DEFAULT_CATALOG_ID
