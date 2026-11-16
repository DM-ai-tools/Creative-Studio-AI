import io
from types import SimpleNamespace

from openpyxl import load_workbook

from app.services.usage_export_app_figures import _work_mode
from app.services.usage_export_service import (
    DETAIL_HEADERS,
    build_summary_workbook,
    build_usage_workbook,
)

SHEETS = [
    ("App figures", [["Metric (as shown on Usage & costs)", "Value"], ["Total spend (USD)", 12.5]]),
    ("Work by user", [["User", "Images generated"], ["Alex", 4]]),
    ("API calls (as in app)", [["When (UTC)", "Open file"], ["2026-01-01", "https://x/a.png"]]),
]


def _row(operation="", provider="", model="", extra=None):
    return SimpleNamespace(operation=operation, provider=provider, model=model, extra=extra or {})


def test_work_mode_classification():
    assert _work_mode(_row("creative_studio_tts", "openai")) == "voice"
    assert _work_mode(_row("generate_video", "heygen")) == "heygen"
    assert _work_mode(_row("video_generation", "byteplus", "dreamina-seedance-2-0")) == "video"
    assert _work_mode(_row("generate_image", "openai")) == "image"
    assert _work_mode(_row("analyze-reference-image", "openrouter")) == "text"
    assert _work_mode(_row("fetch_brand_from_url", "firecrawl")) == "scrape"
    assert _work_mode(_row("/api/v1/generation/creative-studio/chat", "openrouter")) == "text"


def test_full_report_puts_app_figures_after_readme_and_drops_duplicate_rollups():
    content = build_usage_workbook([[""] * len(DETAIL_HEADERS)], app_sheets=SHEETS)
    wb = load_workbook(io.BytesIO(content))
    assert wb.sheetnames[:3] == ["Read me", "App figures", "Work by user"]
    assert "API calls (as in app)" not in wb.sheetnames  # Usage detail already has every call
    assert "By user" not in wb.sheetnames and "By model" not in wb.sheetnames
    assert "By brand" in wb.sheetnames
    assert wb["App figures"].cell(row=2, column=2).value == 12.5


def test_summary_report_includes_app_figures_and_keeps_manager_sheets():
    content = build_summary_workbook(
        period_label="last 7 days",
        overview=[["x", 1]],
        by_user=[["Alex", 1, 2, 3, "B", 1.0, 2.0, 3]],
        by_brand=[["B", 1, 2, 3, "Alex", "", 1.0]],
        app_sheets=SHEETS,
    )
    wb = load_workbook(io.BytesIO(content))
    assert wb.sheetnames[:2] == ["Read me", "App figures"]
    for name in ("Work by user", "API calls (as in app)", "Overview", "By user", "By brand"):
        assert name in wb.sheetnames
    # links in the API calls sheet become clickable
    assert wb["API calls (as in app)"].cell(row=2, column=2).hyperlink is not None
