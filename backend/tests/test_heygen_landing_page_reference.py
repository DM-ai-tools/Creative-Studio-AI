from app.services.heygen_prompt import resolve_visual_style
from app.services.media.heygen_provider import _rank_landing_page_reference_urls


def test_landing_page_pdf_context_is_reference_not_spoken_copy():
    prompt = resolve_visual_style(
        {
            "brand_name": "Traffic Radius",
            "key_benefits": {
                "landing_page_reference_text": "Free Google Ads audit and a 90-day action plan.",
            },
        },
        {},
        for_video_agent=True,
        format_type="reel",
    )

    assert "Optional landing-page PDF reference" in prompt
    assert "do not read this reference aloud" in prompt
    assert "Free Google Ads audit" in prompt


def test_relevant_pdf_pages_are_selected_for_heygen_broll():
    pages = [
        {
            "pageNumber": index,
            "imageUrl": f"/files/page-{index}.jpg",
            "text": (
                "Google Ads audit conversion tracking and ninety day action plan"
                if index in {12, 19}
                else f"General company information page {index}"
            ),
        }
        for index in range(1, 21)
    ]
    urls, page_numbers = _rank_landing_page_reference_urls(
        {"key_benefits": {"landing_page_reference_pages": pages}},
        query="Show the Google Ads audit, conversion tracking and 90-day action plan",
        limit=8,
    )

    assert len(urls) == 8
    assert 12 in page_numbers
    assert 19 in page_numbers
