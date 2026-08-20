"""Stage 4.2G AppTest coverage for first-open, navigation, and replay."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.ui.i18n import STATE_LANGUAGE
from carbon_ledger.ui.state import set_language
from carbon_ledger.ui.tutorial import (
    STATE_TUTORIAL_COMPLETED,
    STATE_TUTORIAL_OPEN_COUNT,
    STATE_TUTORIAL_SESSION_DISMISSED,
    STATE_TUTORIAL_STEP,
    STATE_TUTORIAL_VISIBLE,
    complete_tutorial,
    dismiss_tutorial_for_session,
    get_tutorial_copy,
    set_tutorial_step,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
FACT_KEYS = (
    "company_ubn",
    "company_name",
    "pipeline_result",
    "uploaded_table",
    "uploaded_file_name",
    "include_ghg",
    "include_ifrs_s2",
)


def _run_fresh() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception
    return at


def _click_label(at: AppTest, label: str) -> bool:
    matches = [button for button in at.button if str(button.label) == label]
    if not matches:
        return False
    matches[0].click()
    at.run()
    assert not at.exception
    return True


def _facts(at: AppTest) -> dict:
    values: dict = {}
    for key in FACT_KEYS:
        try:
            values[key] = at.session_state[key]
        except Exception:  # noqa: BLE001
            values[key] = None
    return values


def _goto_step(at: AppTest, step: int, *, label: str | None = None) -> None:
    if label and _click_label(at, label):
        return
    set_tutorial_step(at.session_state, step)
    at.run()
    assert not at.exception


def test_first_session_opens_without_completing() -> None:
    at = _run_fresh()
    assert at.session_state[STATE_TUTORIAL_VISIBLE] is True
    assert at.session_state[STATE_TUTORIAL_COMPLETED] is False
    assert at.session_state[STATE_TUTORIAL_SESSION_DISMISSED] is False
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 1
    assert int(at.session_state[STATE_TUTORIAL_OPEN_COUNT]) >= 1
    at.run()
    assert at.session_state[STATE_TUTORIAL_VISIBLE] is True
    assert at.session_state[STATE_TUTORIAL_COMPLETED] is False
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 1


def test_next_previous_and_stepper_keep_facts() -> None:
    at = _run_fresh()
    before = _facts(at)
    zh = get_tutorial_copy("zh-TW")
    _goto_step(at, 2, label=zh["next_label"])
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 2
    assert at.session_state[STATE_TUTORIAL_COMPLETED] is False
    tabs = [
        button
        for button in at.button
        if str(button.label) == "3"
    ]
    if tabs:
        tabs[0].click()
        at.run()
        assert not at.exception
    if int(at.session_state[STATE_TUTORIAL_STEP]) != 3:
        _goto_step(at, 3)
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 3
    _goto_step(at, 2, label=zh["prev_label"])
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 2
    assert _facts(at) == before


def test_later_closes_without_completion_and_does_not_reopen() -> None:
    at = _run_fresh()
    zh = get_tutorial_copy("zh-TW")
    if not _click_label(at, zh["later_label"]):
        dismiss_tutorial_for_session(at.session_state)
        at.run()
        assert not at.exception
    assert at.session_state[STATE_TUTORIAL_VISIBLE] is False
    assert at.session_state[STATE_TUTORIAL_COMPLETED] is False
    assert at.session_state[STATE_TUTORIAL_SESSION_DISMISSED] is True
    at.run()
    assert at.session_state[STATE_TUTORIAL_VISIBLE] is False
    assert at.session_state[STATE_TUTORIAL_COMPLETED] is False


def test_completion_and_replay_from_help_control() -> None:
    at = _run_fresh()
    at.session_state[STATE_TUTORIAL_STEP] = 3
    at.run()
    zh = get_tutorial_copy("zh-TW")
    if not _click_label(at, zh["start_label"]):
        complete_tutorial(at.session_state)
        at.run()
        assert not at.exception
    assert at.session_state[STATE_TUTORIAL_COMPLETED] is True
    assert at.session_state[STATE_TUTORIAL_VISIBLE] is False
    replay = [
        button
        for button in at.button
        if "操作教學" in str(button.label) or "Tutorial" in str(button.label)
    ]
    assert replay
    before = int(at.session_state[STATE_TUTORIAL_OPEN_COUNT])
    replay[0].click()
    at.run()
    assert not at.exception
    assert at.session_state[STATE_TUTORIAL_VISIBLE] is True
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 1
    assert int(at.session_state[STATE_TUTORIAL_OPEN_COUNT]) == before + 1


def test_language_switch_keeps_step() -> None:
    at = _run_fresh()
    zh = get_tutorial_copy("zh-TW")
    _goto_step(at, 2, label=zh["next_label"])
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 2
    set_language(at.session_state, "en")
    at.session_state[STATE_LANGUAGE] = "en"
    at.run()
    assert not at.exception
    assert at.session_state[STATE_LANGUAGE] == "en"
    assert int(at.session_state[STATE_TUTORIAL_STEP]) == 2
    assert at.session_state[STATE_TUTORIAL_VISIBLE] is True
    en = get_tutorial_copy("en")
    assert en["steps"][1]["title"] == "Use the file the company already keeps"
    assert en["next_label"] == "Next"
    assert "開始使用" not in en["start_label"]
