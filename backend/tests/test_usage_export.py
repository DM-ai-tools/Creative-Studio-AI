import io
from datetime import date, datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from openpyxl import load_workbook

from app.services.public_urls import absolute_media_url, media_urls_from_extra
from app.services.usage_export_service import (
    DETAIL_HEADERS,
    _assign_pending_media_spend,
    _detail_row,
    _infer_brand_from_text,
    _manager_brand_from_context,
    _usage_delivery_kind,
    _usage_media_cost_dedup_key,
    _is_automation_service_email,
    _usage_has_successful_media_output,
    _resolve_usage_actor,
    _manager_media_cost_usd,
    _usage_media_cost_usd,
    _variant_delivery_flags,
    build_summary_workbook,
    build_usage_workbook,
    parse_usage_date_range,
)


def test_parse_usage_date_range_days():
    since, until, label = parse_usage_date_range(days=30)
    assert until >= since
    assert label == "last_30_days"


def test_parse_usage_date_range_custom():
    since, until, label = parse_usage_date_range(
        date_from=date(2025, 1, 1),
        date_to=date(2025, 1, 31),
    )
    assert since.year == 2025
    assert until.day == 31
    assert "2025-01-01" in label


def test_parse_usage_date_range_rejects_inverted():
    with pytest.raises(ValueError):
        parse_usage_date_range(
            date_from=date(2025, 2, 1),
            date_to=date(2025, 1, 1),
        )


def test_extract_output_urls_dedupes():
    urls = media_urls_from_extra(
        {
            "image_url": "/files/a.png",
            "output_urls": ["/files/a.png", "https://x.test/b.mp4"],
        }
    )
    assert len(urls) == 2


def test_absolute_media_url():
    u = absolute_media_url("/files/test.png")
    assert u.endswith("/files/test.png")


def _usage_row(**overrides):
    values = {
        "id": uuid4(),
        "created_at": datetime(2026, 10, 29, 8, 30, tzinfo=timezone.utc),
        "user_id": None,
        "tenant_id": uuid4(),
        "extra": {},
        "provider": "byteplus",
        "model": "seedance-2.5",
        "operation": "video_generation",
        "prompt_tokens": 0,
        "completion_tokens": 100,
        "total_tokens": 100,
        "cost_usd": 1.25,
        "success": True,
        "error": None,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_detail_row_recovers_job_user_brand_and_final_video_link():
    user_id = uuid4()
    brand_id = uuid4()
    tenant_id = uuid4()
    row = _usage_row(tenant_id=tenant_id, extra={"job_id": "job-1"})
    detail = _detail_row(
        row,
        users={user_id: SimpleNamespace(email="creator@example.com", full_name="Creator")},
        tenants={tenant_id: "Client workspace"},
        brands={brand_id: "Traffic Radius"},
        job_metadata={
            "job-1": {
                "url": "/files/final-production.mp4",
                "user_id": str(user_id),
                "brand_id": str(brand_id),
                "brand_name": "Traffic Radius",
                "brief_id": "",
                "media_mode": "video",
            }
        },
    )

    assert detail[DETAIL_HEADERS.index("User email")] == "creator@example.com"
    assert detail[DETAIL_HEADERS.index("Brand name")] == "Traffic Radius"
    assert detail[DETAIL_HEADERS.index("Video link (for manager — click to open)")].endswith(
        "/files/final-production.mp4"
    )


def test_detail_row_recovers_brand_from_asset_path():
    brand_id = uuid4()
    row = _usage_row(
        provider="openai",
        model="gpt-image-2",
        operation="generate_image",
        extra={"image_url": "/files/legacy-image.png"},
    )
    detail = _detail_row(
        row,
        users={},
        tenants={},
        brands={brand_id: "Recovered brand"},
        file_url_to_brand={"/files/legacy-image.png": brand_id},
    )
    assert detail[DETAIL_HEADERS.index("Brand name")] == "Recovered brand"


def test_summary_workbook_has_user_and_brand_sheets():
    content = build_summary_workbook(
        period_label="last 7 days",
        overview=[["Total videos delivered", 3]],
        by_user=[["Alex", 1, 2, 2, "Brand X", 1.2, 4.5, 10]],
        by_brand=[["Brand X", 1, 2, 2, "Alex", "Hook line", 4.5]],
        unassigned_by_hook=[["Alex", "Summer campaign", "Juice", "Summer sale hook", "static", "Image", "https://x", "brief-1"]],
        no_brand_by_person=[["Alex", 10, 2, 12, "Summer campaign", "Hook one", "https://x"]],
    )
    workbook = load_workbook(io.BytesIO(content))
    assert "By user" in workbook.sheetnames
    assert "By brand" in workbook.sheetnames
    assert "No brand detail" not in workbook.sheetnames
    assert "No brand by person" not in workbook.sheetnames
    assert "API only (no library)" not in workbook.sheetnames
    assert workbook["By user"].cell(row=1, column=1).value == "User"
    assert workbook["By user"].cell(row=2, column=3).value == 2


def test_automation_service_email_detection():
    assert _is_automation_service_email("seedance_2.5@creativestudio.tools")
    assert not _is_automation_service_email("varshankumar.ch@dotmappers.in")


def test_usage_output_required_for_delivery_count():
    assert not _usage_has_successful_media_output(
        _usage_row(operation="video_generation", provider="byteplus", model="dreamina-seedance-2-5-260628")
    )
    assert _usage_has_successful_media_output(
        _usage_row(
            operation="video_generation",
            provider="byteplus",
            model="dreamina-seedance-2-5-260628",
            extra={"output_urls": ["/files/clip.mp4"]},
        )
    )
    assert _usage_has_successful_media_output(
        _usage_row(
            operation="video_generation",
            provider="byteplus",
            model="dreamina-seedance-2-0-260128",
            completion_tokens=245_000,
            extra={"task_id": "cgt-test-123"},
        )
    )


def test_seedance_actor_from_brief_owner():
    brief_id = uuid4()
    owner_id = uuid4()
    service_id = uuid4()
    ev = _usage_row(
        operation="video_generation",
        provider="byteplus",
        model="dreamina-seedance-2-0-260128",
        user_id=service_id,
        completion_tokens=245_000,
        extra={"brief_id": str(brief_id), "task_id": "cgt-test-456"},
    )
    email, name = _resolve_usage_actor(
        ev,
        users={
            owner_id: SimpleNamespace(email="pratiti@example.com", full_name="Pratiti"),
        },
        job_metadata={},
        task_job_metadata={},
        brief_owners={brief_id: owner_id},
    )
    assert email == "pratiti@example.com"
    assert name == "Pratiti"


def test_pending_image_spend_splits_to_library_brands():
    brand_acc = {
        "(no brand)": {"cost": 0.0, "images": 0, "videos": 0, "creatives": 0, "users": set(), "hooks": set()},
        "Spar Club": {"cost": 0.0, "images": 24, "videos": 0, "creatives": 24, "users": set(), "hooks": set()},
        "Pickle Juice Australia": {"cost": 0.0, "images": 14, "videos": 0, "creatives": 14, "users": set(), "hooks": set()},
    }
    _assign_pending_media_spend(
        brand_acc,
        pending_by_user={"pratiti@x.com": {"image": 1.0, "video": 0.0}},
        user_brand_images={"pratiti@x.com": {"Spar Club": 24, "Pickle Juice Australia": 14}},
        user_brand_videos={},
    )
    assert round(brand_acc["Spar Club"]["cost"], 4) == round(1.0 * 24 / 38, 4)
    assert brand_acc["(no brand)"]["cost"] == 0.0


def test_image_cost_dedup_keys_differ_per_output():
    a = _usage_row(
        operation="generate_image",
        provider="openai",
        model="gpt-image-2",
        extra={"job_id": "shared-job", "output_urls": ["/files/a.png"]},
    )
    b = _usage_row(
        operation="generate_image",
        provider="openai",
        model="gpt-image-2",
        extra={"job_id": "shared-job", "output_urls": ["/files/b.png"]},
    )
    assert _usage_media_cost_dedup_key(a) != _usage_media_cost_dedup_key(b)


def test_manager_media_cost_seedance_matches_dashboard_tokens():
    row = _usage_row(
        operation="video_generation",
        provider="byteplus",
        model="dreamina-seedance-2-0-260128",
        completion_tokens=245_000,
        total_tokens=245_000,
        cost_usd=0,
        extra={"output_urls": ["/files/a.mp4"], "task_id": "cgt-1"},
    )
    cost = _manager_media_cost_usd(row)
    assert 1.0 < cost < 3.0


def test_manager_media_cost_seedance_prefers_stored_cost():
    row = _usage_row(
        operation="video_generation",
        provider="byteplus",
        model="dreamina-seedance-2-5-260628",
        completion_tokens=2_500_000,
        cost_usd=12.5,
        extra={"output_urls": ["/files/a.mp4"]},
    )
    assert _manager_media_cost_usd(row) == 12.5


def test_usage_media_cost_excludes_llm():
    llm = _usage_row(operation="llm_chat", provider="openrouter", cost_usd=5.0)
    img = _usage_row(operation="generate_image", provider="openai", cost_usd=0.12)
    assert _usage_media_cost_usd(llm) == 0.0
    assert _usage_media_cost_usd(img) == 0.12


def test_usage_delivery_kind_counts_image_and_video():
    assert _usage_delivery_kind(_usage_row(operation="generate_image", provider="openai")) == "image"
    assert _usage_delivery_kind(_usage_row(operation="generate_video", provider="heygen")) == "video"
    assert (
        _usage_delivery_kind(
            _usage_row(
                operation="video_generation",
                provider="google",
                model="gemini-omni-1.1-flash",
            )
        )
        == "video"
    )
    assert (
        _usage_delivery_kind(
            _usage_row(
                operation="video_generation",
                provider="byteplus",
                model="dreamina-seedance-2-5-260628",
            )
        )
        == "video"
    )
    assert _usage_delivery_kind(_usage_row(operation="llm_chat", provider="openrouter")) is None
    assert _usage_delivery_kind(_usage_row(operation="analyze-reference-image", success=True)) is None


def test_infer_brand_from_hook_text():
    brands = ["Pickle Juice Australia", "Traffic Radius", "Spar Club"]
    assert _infer_brand_from_text("Stop scrolling — Pickle Juice Australia hydration", brands) == "Pickle Juice Australia"
    label, inferred = _manager_brand_from_context(
        brand_name="No brand",
        hook="New reel for Traffic Radius local ads",
        known_brands=brands,
    )
    assert inferred is True
    assert label == "Traffic Radius"


def test_variant_delivery_flags_without_public_url():
    variant = SimpleNamespace(
        format="reel",
        status="READY",
        generation_params={"pipeline": {"video": {"status": "done"}}},
    )
    has_img, has_vid = _variant_delivery_flags(variant, "", "")
    assert not has_img
    assert has_vid


def test_variant_delivery_flags_ready_static_without_pipeline():
    variant = SimpleNamespace(
        format="static",
        status="READY",
        generation_params={},
    )
    has_img, has_vid = _variant_delivery_flags(variant, "", "")
    assert has_img
    assert not has_vid


def test_workbook_media_urls_are_clickable():
    row = [""] * len(DETAIL_HEADERS)
    video_url = "https://creativestudio.tools/files/report-video.mp4"
    row[DETAIL_HEADERS.index("Video link (for manager — click to open)")] = video_url
    content = build_usage_workbook([row])
    workbook = load_workbook(io.BytesIO(content))
    sheet = workbook["Usage detail"]
    col = DETAIL_HEADERS.index("Video link (for manager — click to open)") + 1
    assert sheet.cell(row=2, column=col).hyperlink.target == video_url
