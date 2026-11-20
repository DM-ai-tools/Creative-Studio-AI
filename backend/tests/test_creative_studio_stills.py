import asyncio
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from app.core.config import settings
from app.core.security import get_current_user
from app.services import creative_studio_inserts as ins
from app.services import creative_studio_script_plan as sp
from app.services import creative_studio_still as still
from app.services.ffmpeg_util import ffmpeg_executable, probe_video_duration

TENANT = "11111111-1111-1111-1111-111111111111"
GPT = "openai-gpt-image-2.6-sunburst"


@pytest.fixture()
def uploads(tmp_path, monkeypatch):
    from app.services.file_service import file_service

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service, "upload_dir", tmp_path)
    return tmp_path


# ── drawing a still ─────────────────────────────────────────────────────────


class _FakeProvider:
    def __init__(self, result):
        self.result, self.calls = result, []

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        return self.result


def _patch_image_stack(monkeypatch, result):
    from app.services import usage_tracker
    from app.services.media import registry

    provider = _FakeProvider(result)
    recorded = []
    monkeypatch.setattr(registry, "get_image_provider", lambda model=None: provider)
    monkeypatch.setattr(usage_tracker, "record_media_generation", lambda **kw: recorded.append(kw))
    monkeypatch.setattr(usage_tracker, "estimate_media_cost", lambda **kw: (0.04, 1.0))
    return provider, recorded


def test_a_still_is_drawn_with_text_rules_recorded_for_billing_and_returned(uploads, monkeypatch):
    provider, recorded = _patch_image_stack(
        monkeypatch, {"status": "done", "url": "/files/t/generated/a.png", "provider": "openai", "model": GPT}
    )
    out = asyncio.run(still.generate_still(tenant_id=TENANT, prompt="A laptop screen with a table headed Clicks and Spend", model=GPT, aspect="9/16"))
    assert out["url"] == "/files/t/generated/a.png" and out["credits_estimate"] == 1.0
    sent = provider.calls[0]
    assert sent["prompt"].startswith(still.STILL_PREFIX) and "headed Clicks and Spend" in sent["prompt"]
    assert "gibberish" in sent["prompt"] and sent["format_type"] == "reel" and sent["model"] == GPT
    assert recorded[0]["operation"] == "creative_studio_script_still" and recorded[0]["success"] is True


def test_a_failed_image_is_recorded_as_failed_and_reported_clearly(uploads, monkeypatch):
    _, recorded = _patch_image_stack(monkeypatch, {"status": "failed", "url": None, "provider": "openai", "error": "content policy"})
    with pytest.raises(RuntimeError, match="content policy"):
        asyncio.run(still.generate_still(tenant_id=TENANT, prompt="x", model=GPT))
    assert recorded[0]["success"] is False and recorded[0]["error"] == "content policy"


def test_only_gpt_image_and_seedream_are_accepted_and_the_prompt_is_checked_before_any_charge(uploads, monkeypatch):
    provider, recorded = _patch_image_stack(monkeypatch, {"status": "done", "url": "/files/x.png"})
    for bad_model in ("gen4_image", "ark-seedance-2-5", "", "runway"):
        with pytest.raises(ValueError, match="GPT Image 2 or a Seedream"):
            asyncio.run(still.generate_still(tenant_id=TENANT, prompt="x", model=bad_model))
    with pytest.raises(ValueError, match="Describe the picture"):
        asyncio.run(still.generate_still(tenant_id=TENANT, prompt="   ", model=GPT))
    with pytest.raises(ValueError, match="too long"):
        asyncio.run(still.generate_still(tenant_id=TENANT, prompt="x" * 2600, model=GPT))
    assert provider.calls == [] and recorded == []  # nothing was sent to a paid provider
    assert still.is_still_model("seedream-5-0-lite") and still.is_still_model(GPT)


def test_aspect_ratios_map_to_the_providers_format_names():
    assert [still.format_for_aspect(a) for a in ("9/16", "9:16", "4/5", "16/9", "4/3", "1/1")] == ["reel", "reel", "reel", "video", "carousel", "static"]


# ── what the planner hands over ─────────────────────────────────────────────


def _scene(**over):
    base = {
        "title": "Explain the problem",
        "duration_seconds": 8,
        "duration_source": "script",
        "voiceover": "Your campaigns might get plenty of clicks.",
        "shots": [{"seconds": 4, "description": "A worried owner at a desk."}, {"seconds": 4, "description": "Parcels on a bench."}],
        "edit_inserts": [],
    }
    base.update(over)
    return base


def test_the_planner_turns_screen_inserts_into_stills_and_leaves_everything_else_alone():
    report = "Photoreal laptop screen with a search-term report dashboard: columns Search Term, Clicks, Spend; green and red rows."
    plan = sp.normalize_plan(
        {
            "scenes": [
                _scene(
                    edit_inserts=[
                        {"starts_at_seconds": 1, "duration_seconds": 4, "kind": "screen", "note": "report", "image_prompt": report},
                        {"starts_at_seconds": 5, "duration_seconds": 3, "kind": "text card", "note": "headline", "image_prompt": "must be ignored"},
                    ]
                )
            ]
        },
        clip_cap=30,
        script_text="(8s)",
    )
    [one] = plan["stills"]
    assert one["id"] == "still-1" and one["image_prompt"] == report  # kept word for word, never "sanitised"
    assert (one["start"], one["end"], one["duration"]) == (1.0, 5.0, 4.0)
    assert one["label"] == "Explain the problem - screen"
    kinds = {e["kind"]: e["image_prompt"] for e in plan["edit_list"]}
    assert kinds["screen"] == report and kinds["text card"] == ""  # only screens/graphics become pictures


def test_stills_are_2_to_6_seconds_never_overlap_and_inserts_without_a_prompt_are_not_stills():
    inserts = [
        {"starts_at_seconds": 0, "duration_seconds": 1, "kind": "graphic", "note": "a", "image_prompt": "A bar of coloured shapes"},
        {"starts_at_seconds": 1, "duration_seconds": 12, "kind": "screen", "note": "b", "image_prompt": "A phone held at an angle"},
        {"starts_at_seconds": 3, "duration_seconds": 3, "kind": "screen", "note": "no prompt written", "image_prompt": ""},
    ]
    plan = sp.normalize_plan({"scenes": [_scene(duration_seconds=14, shots=[{"seconds": 14, "description": "x"}], edit_inserts=inserts)]}, clip_cap=30, script_text="14s")
    spans = [(s["start"], s["end"]) for s in plan["stills"]]
    assert all(2.0 <= b - a <= 6.0 for a, b in spans), spans
    assert all(second[0] >= first[1] for first, second in zip(spans, spans[1:])), spans  # no overlaps
    assert len(plan["stills"]) == 2 and [s["id"] for s in plan["stills"]] == ["still-1", "still-2"]


# ── laying stills over a video ──────────────────────────────────────────────


def test_insert_windows_are_checked_before_any_video_work():
    ok = ins.clean_inserts(
        [{"image_url": "/files/b.png", "start_seconds": 4, "duration_seconds": 2}, {"image_url": "/files/a.png", "start_seconds": 1, "duration_seconds": 2}], 10
    )
    assert [(i["image_url"], i["start"], i["end"]) for i in ok] == [("/files/a.png", 1.0, 3.0), ("/files/b.png", 4.0, 6.0)]  # sorted
    assert ins.clean_inserts([{"image_url": "/files/a.png", "start_seconds": 8, "duration_seconds": 5}], 10)[0]["end"] == 10.0  # clamped to the video
    with pytest.raises(ValueError, match="overlap"):
        ins.clean_inserts([{"image_url": "a", "start_seconds": 1, "duration_seconds": 3}, {"image_url": "b", "start_seconds": 3, "duration_seconds": 2}], 10)
    with pytest.raises(ValueError, match="after the video ends"):
        ins.clean_inserts([{"image_url": "a", "start_seconds": 9.8, "duration_seconds": 2}], 10)
    with pytest.raises(ValueError, match="no image"):
        ins.clean_inserts([{"image_url": " ", "start_seconds": 1, "duration_seconds": 2}], 10)
    with pytest.raises(ValueError, match="start time"):
        ins.clean_inserts([{"image_url": "a", "start_seconds": "soon", "duration_seconds": 2}], 10)
    with pytest.raises(ValueError, match="at least one"):
        ins.clean_inserts([], 10)
    with pytest.raises(ValueError, match="at most 8"):
        ins.clean_inserts([{"image_url": "a", "start_seconds": i, "duration_seconds": 1} for i in range(9)], 30)


needs_ffmpeg = pytest.mark.skipif(not ffmpeg_executable(), reason="ffmpeg is not installed")


def _make_video(path: Path, seconds=8, size="320x568"):
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [ffmpeg_executable(), "-y", "-f", "lavfi", "-i", f"color=c=0x303840:s={size}:d={seconds}:r=24", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
         "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(path)],
        check=True, capture_output=True,
    )


def _frame(video: Path, at: float, out: Path) -> Image.Image:
    subprocess.run([ffmpeg_executable(), "-y", "-ss", f"{at}", "-i", str(video), "-frames:v", "1", str(out)], check=True, capture_output=True)
    return Image.open(out).convert("RGB")


def _share(img: Image.Image, rgb) -> float:
    data = list(img.resize((60, 100)).getdata())
    close = sum(1 for p in data if all(abs(p[i] - rgb[i]) < 40 for i in range(3)))
    return close / len(data)


@needs_ffmpeg
def test_each_still_shows_only_in_its_window_audio_and_length_are_kept(uploads, tmp_path):
    _make_video(uploads / TENANT / "generated" / "in.mp4", seconds=8)
    # two stills in a different aspect from the video: they must fill the frame, not stretch
    Image.new("RGB", (640, 640), (220, 30, 30)).save(uploads / TENANT / "generated" / "red.png")
    Image.new("RGB", (900, 500), (30, 200, 60)).save(uploads / TENANT / "generated" / "green.png")
    result = ins.add_image_inserts_to_video(
        video_url=f"/files/{TENANT}/generated/in.mp4",
        tenant_id=TENANT,
        inserts=[
            {"image_url": f"/files/{TENANT}/generated/green.png", "start_seconds": 5, "duration_seconds": 2.5},
            {"image_url": f"/files/{TENANT}/generated/red.png", "start_seconds": 1, "duration_seconds": 3},
        ],
    )
    out = uploads / result["url"].removeprefix("/files/")
    src = uploads / TENANT / "generated" / "in.mp4"
    assert out.is_file() and probe_video_duration(out) == pytest.approx(probe_video_duration(src), abs=0.3)
    assert b"Audio" in subprocess.run([ffmpeg_executable(), "-i", str(out)], capture_output=True).stderr
    grey = (0x30, 0x38, 0x40)
    assert _share(_frame(out, 0.3, tmp_path / "f0.png"), grey) > 0.9  # before the first still: the original video
    assert _share(_frame(out, 2.5, tmp_path / "f1.png"), (220, 30, 30)) > 0.85  # red still fills the frame
    assert _share(_frame(out, 4.6, tmp_path / "f2.png"), grey) > 0.9  # between the two: the original again
    assert _share(_frame(out, 6.0, tmp_path / "f3.png"), (30, 200, 60)) > 0.85  # green still
    assert _share(_frame(out, 7.7, tmp_path / "f4.png"), grey) > 0.9  # after: the original again
    assert [(i["start_seconds"], i["end_seconds"]) for i in result["inserts"]] == [(1.0, 4.0), (5.0, 7.5)]


@needs_ffmpeg
def test_inserts_work_without_zoom_and_report_missing_files_clearly(uploads):
    _make_video(uploads / TENANT / "generated" / "in.mp4", seconds=6)
    Image.new("RGB", (300, 300), (10, 10, 200)).save(uploads / TENANT / "generated" / "blue.png")
    ok = ins.add_image_inserts_to_video(
        video_url=f"/files/{TENANT}/generated/in.mp4", tenant_id=TENANT, zoom=False,
        inserts=[{"image_url": f"/files/{TENANT}/generated/blue.png", "start_seconds": 2, "duration_seconds": 2}],
    )
    assert (uploads / ok["url"].removeprefix("/files/")).is_file()
    with pytest.raises(ValueError, match="picture could not be found"):
        ins.add_image_inserts_to_video(video_url=f"/files/{TENANT}/generated/in.mp4", tenant_id=TENANT, inserts=[{"image_url": "/files/nope.png", "start_seconds": 1, "duration_seconds": 2}])
    with pytest.raises(ValueError, match="could not be found"):
        ins.add_image_inserts_to_video(video_url="/files/nope.mp4", tenant_id=TENANT, inserts=[{"image_url": "/files/x.png", "start_seconds": 1, "duration_seconds": 2}])
    with pytest.raises(ValueError, match="picture could not be found"):  # only pictures made in this app, never an outside address
        ins.add_image_inserts_to_video(video_url=f"/files/{TENANT}/generated/in.mp4", tenant_id=TENANT, inserts=[{"image_url": "https://evil.example/x.png", "start_seconds": 1, "duration_seconds": 2}])


# ── the API ─────────────────────────────────────────────────────────────────


def _client(monkeypatch):
    from app.api.v1 import generation
    from app.services.usage_allowance import require_usage_allowance

    app = FastAPI()
    app.include_router(generation.router, prefix="/api/v1")
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id="u1", tenant_id=TENANT)
    app.dependency_overrides[require_usage_allowance] = lambda: None
    return TestClient(app)


def test_still_endpoint_returns_the_picture_and_turns_bad_requests_into_clear_errors(monkeypatch):
    async def fake(**kw):
        if kw["model"] == "bad":
            raise ValueError("Choose GPT Image 2 or a Seedream model to draw the still.")
        return {"url": "/files/t/a.png", "model": kw["model"], "provider": "openai", "credits_estimate": 1.0, "note": None}

    monkeypatch.setattr(still, "generate_still", fake)
    client = _client(monkeypatch)
    good = client.post("/api/v1/generation/creative-studio/still", json={"prompt": "a screen", "model": GPT, "aspect": "9/16"})
    assert good.status_code == 200 and good.json()["url"] == "/files/t/a.png"
    bad = client.post("/api/v1/generation/creative-studio/still", json={"prompt": "a screen", "model": "bad"})
    assert bad.status_code == 422 and "Seedream" in bad.json()["detail"]
    assert client.post("/api/v1/generation/creative-studio/still", json={"prompt": "", "model": GPT}).status_code == 422


def test_inserts_endpoint_validates_the_request_and_maps_errors(monkeypatch):
    client = _client(monkeypatch)
    url = "/api/v1/generation/creative-studio/inserts"
    assert client.post(url, json={"video_url": "/files/x.mp4", "inserts": []}).status_code == 422  # needs at least one
    too_long = {"image_url": "/files/a.png", "start_seconds": 1, "duration_seconds": 99}
    assert client.post(url, json={"video_url": "/files/x.mp4", "inserts": [too_long]}).status_code == 422
    missing = client.post(url, json={"video_url": "/files/nope.mp4", "inserts": [{"image_url": "/files/a.png", "start_seconds": 1, "duration_seconds": 2}]})
    assert missing.status_code == 422 and "could not be found" in missing.json()["detail"]
