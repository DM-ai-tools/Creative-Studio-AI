"""Auto must say so when it plans a shorter film than the script the user pasted."""

from app.services.creative_studio_chat_service import (
    _estimate_script_duration,
    auto_duration_cap_notice,
)

LONG_UNTIMED = "\n".join(
    f"Scene {i}: Presenter explains point {i} to camera in the office." for i in range(1, 17)
)
TIMED_TWO_MINUTES = "\n".join(
    f"SCENE {i + 1} — {i * 15 // 60}:{i * 15 % 60:02d}–{(i + 1) * 15 // 60}:{(i + 1) * 15 % 60:02d}\n"
    f"VISUAL: Shot {i + 1}."
    for i in range(8)
)


def _user(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def test_long_untimed_script_is_capped_and_explained():
    assert _estimate_script_duration(LONG_UNTIMED) == 60
    notice = auto_duration_cap_notice(_user(LONG_UNTIMED), None)
    assert notice and "limited to 60s" in notice and "120s" in notice


def test_no_notice_when_a_duration_is_chosen():
    assert auto_duration_cap_notice(_user(LONG_UNTIMED), 120) is None


def test_no_notice_for_a_complete_timed_timeline():
    assert _estimate_script_duration(TIMED_TWO_MINUTES) == 120
    assert auto_duration_cap_notice(_user(TIMED_TWO_MINUTES), None) is None


def test_no_notice_when_the_script_fits_auto():
    short = "Scene 1: Product on desk.\nScene 2: Hand picks it up."
    assert auto_duration_cap_notice(_user(short), None) is None


def test_no_notice_when_the_script_states_a_runtime():
    stated = "Make a 2 minute brand film.\n" + LONG_UNTIMED
    assert _estimate_script_duration(stated) == 120
    assert auto_duration_cap_notice(_user(stated), None) is None


def test_notice_is_shown_only_once_per_chat():
    first = auto_duration_cap_notice(_user(LONG_UNTIMED), None)
    history = [*_user(LONG_UNTIMED), {"role": "assistant", "content": f"Plan ready.\n\n{first}"}]
    assert auto_duration_cap_notice(history, None) is None
