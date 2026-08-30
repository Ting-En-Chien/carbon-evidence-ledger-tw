"""Stage 4.2F-C1 — exception-only confirmation UX."""

from __future__ import annotations

import re
from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.intake import parse_uploaded_table
from carbon_ledger.ui.i18n import STATE_LANGUAGE, t
from carbon_ledger.ui.state import (
    STATE_INTAKE_COMMITTED,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_SHOW_MAPPING_EDITOR,
    STATE_INTAKE_STEP,
    STATE_INTAKE_TABLE,
    STATE_INTAKE_VALIDATION_ERROR,
    initialize_ui_state,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
ZH = "zh-TW"
EN = "en"
INTAKE_PAGE = "app_pages/data_intake.py"
INTERNAL_TERMS = (
    "High",
    "Medium",
    "Low",
    "schema",
    "canonical",
    "parser",
    "confidence score",
    "activity_type",
    "activity_value",
    "site_id",
)
RAW_KEYS = (
    "intake.read_recognized",
    "intake.read_confirm_count",
    "intake.ex.queue_title",
    "intake.ex.apply",
    "intake.btn.continue_ready",
    "intake.draft_unapplied",
    "intake.status.ready",
    "intake.status.deferred",
)


def _run_customer() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    at.switch_page(INTAKE_PAGE)
    at.run()
    assert not at.exception
    return at


def _all_text(at: AppTest) -> str:
    chunks: list[str] = []
    for collection_name in (
        "title",
        "header",
        "subheader",
        "markdown",
        "text",
        "caption",
        "info",
        "warning",
        "success",
        "error",
    ):
        collection = getattr(at, collection_name, None)
        if collection is None:
            continue
        for item in collection:
            value = getattr(item, "value", None)
            if value is not None:
                chunks.append(str(value))
            body = getattr(item, "body", None)
            if body is not None:
                chunks.append(str(body))
    for button in at.button:
        if getattr(button, "label", None):
            chunks.append(str(button.label))
    for item in getattr(at, "selectbox", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
        for option in getattr(item, "options", None) or []:
            chunks.append(str(option))
    for item in getattr(at, "radio", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
        for option in getattr(item, "options", None) or []:
            chunks.append(str(option))
    return "\n".join(chunks)


_DATA_URI = re.compile(r"data:image/[^;]+;base64,[A-Za-z0-9+/=\s]+")


def _customer_copy(text: str) -> str:
    """Drop embedded screenshots so base64 cannot match copy tokens like Low."""
    return _DATA_URI.sub("", text)


def _csv_high_steel() -> bytes:
    return (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    ).encode("utf-8")


def _csv_medium() -> bytes:
    return (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    ).encode("utf-8")


def _csv_unmatched() -> bytes:
    return (
        "說明欄,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
    ).encode("utf-8")


def _seed_read(
    at: AppTest,
    data: bytes,
    *,
    editor: bool = False,
    name: str = "ops.csv",
) -> AppTest:
    table = parse_uploaded_table(file_name=name, data=data)
    at.session_state[STATE_INTAKE_TABLE] = table
    at.session_state[STATE_INTAKE_STEP] = 2
    at.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = editor
    at.switch_page(INTAKE_PAGE)
    at.run()
    assert not at.exception
    return at


def _state_get(at: AppTest, key: str, default: object = None) -> object:
    try:
        return at.session_state[key]
    except Exception:  # noqa: BLE001 - AppTest session_state has no .get()
        return default


def _click_label(at: AppTest, label: str) -> AppTest:
    button = next(b for b in at.button if str(b.label) == label)
    button.click()
    at.run()
    assert not at.exception
    continue_labels = {
        t("intake.btn.continue_ready", ZH),
        t("intake.btn.continue_ready", EN),
    }
    if label in continue_labels:
        for _ in range(4):
            try:
                step = int(at.session_state[STATE_INTAKE_STEP] or 0)
            except (KeyError, TypeError, ValueError, AttributeError):
                step = 0
            try:
                error = at.session_state[STATE_INTAKE_VALIDATION_ERROR]
            except (KeyError, AttributeError):
                error = None
            if step >= 3 or error:
                break
            at.run()
            assert not at.exception
    return at


def test_true_zero_count_is_shown_for_high_matches() -> None:
    at = _seed_read(_run_customer(), _csv_high_steel())
    text = _all_text(at)
    assert t("intake.status.ready", ZH) in text
    assert t("intake.ex.none", ZH) in text
    assert t("intake.read_rows", ZH, ready=1, held=0) in text
    assert t("intake.read_confirm_count", ZH, confirm=0) not in text
    labels = [str(button.label) for button in at.button]
    assert t("intake.btn.continue_ready", ZH) in labels
    assert t("intake.btn.accept", ZH) not in labels
    assert t("intake.ex.apply", ZH) not in labels


def test_high_auto_recognition_can_continue_without_field_by_field() -> None:
    at = _seed_read(_run_customer(), _csv_high_steel())
    committed = at.session_state[STATE_INTAKE_COMMITTED]
    assert committed["columns"]["activity_value"] == "使用量"
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    assert _state_get(at, STATE_INTAKE_RESULT) is not None
    assert at.session_state[STATE_INTAKE_STEP] == 3


def test_medium_proposal_is_not_committed_before_apply() -> None:
    at = _seed_read(_run_customer(), _csv_medium())
    committed = at.session_state[STATE_INTAKE_COMMITTED]
    assert "activity_value" not in (committed.get("columns") or {})
    text = _all_text(at)
    assert t("intake.ex.queue_title", ZH) in text
    assert t("intake.ex.column_q", ZH, column="用量") in text
    assert t("intake.ex.column_why_medium", ZH, label="用量") in text
    assert t("intake.ex.column_control", ZH) in text
    assert "看起來是用量" not in text
    assert t("intake.ex.apply", ZH) in [str(b.label) for b in at.button]
    assert t("intake.btn.continue_ready", ZH) not in [
        str(b.label) for b in at.button
    ]
    assert t("intake.btn.accept", ZH) not in text
    at = _click_label(at, t("intake.ex.apply", ZH))
    committed = at.session_state[STATE_INTAKE_COMMITTED]
    assert committed["columns"]["activity_value"] == "用量"
    after = _all_text(at)
    assert t("intake.status.ready", ZH) in after
    assert t("intake.read_rows", ZH, ready=1, held=0) in after


def test_unmatched_required_field_blocks_continue() -> None:
    at = _seed_read(_run_customer(), _csv_unmatched())
    committed = at.session_state[STATE_INTAKE_COMMITTED]
    assert "activity_type" not in (committed.get("columns") or {})
    text = _all_text(at)
    assert t("intake.ex.column_q", ZH, column="說明欄") in text
    assert t("intake.btn.continue_ready", ZH) not in [
        str(b.label) for b in at.button
    ]
    assert t("intake.editor.required", ZH) not in text


def test_full_mapping_editor_stays_secondary() -> None:
    at = _seed_read(_run_customer(), _csv_medium())
    text = _all_text(at)
    assert t("intake.editor.required", ZH) not in text
    assert t("intake.map_activity_type", ZH) not in text
    assert t("intake.btn.fix", ZH) in [str(b.label) for b in at.button]


def test_draft_editor_change_does_not_become_fact_on_continue_or_rerun() -> None:
    at = _seed_read(_run_customer(), _csv_medium(), editor=True)
    before = dict(at.session_state[STATE_INTAKE_COMMITTED]["columns"])
    assert "activity_value" not in before
    text = _all_text(at)
    assert t("intake.draft_unapplied", ZH) in text
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    assert _state_get(at, STATE_INTAKE_RESULT) is None
    assert at.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] is True
    assert t("intake.draft_unapplied", ZH) in _all_text(at)
    assert at.session_state[STATE_INTAKE_COMMITTED]["columns"] == before
    at.run()
    assert at.session_state[STATE_INTAKE_COMMITTED]["columns"] == before
    assert _state_get(at, STATE_INTAKE_RESULT) is None


def test_default_path_hides_internal_terminology() -> None:
    at = _seed_read(_run_customer(), _csv_medium())
    text = _customer_copy(_all_text(at))
    for token in INTERNAL_TERMS:
        assert token not in text
    for key in RAW_KEYS:
        assert key not in text


def test_english_read_path_has_no_raw_keys() -> None:
    at = _run_customer()
    at.session_state[STATE_LANGUAGE] = EN
    if len(at.segmented_control) >= 1:
        try:
            at.segmented_control[0].set_value("EN")
        except Exception:
            pass
    at.run()
    at.switch_page(INTAKE_PAGE)
    at.run()
    assert not at.exception
    at = _seed_read(at, _csv_high_steel())
    en = _all_text(at)
    assert t("intake.read_title", EN) in en
    assert t("intake.status.ready", EN) in en
    assert t("intake.btn.continue_ready", EN) in en
    assert "Nothing needs confirmation" not in en
    for key in RAW_KEYS:
        assert key not in en
    for token in INTERNAL_TERMS:
        assert token not in _customer_copy(en)


def _csv_high_steel_and_ng() -> bytes:
    return (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31,高雄廠\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    ).encode("utf-8")


def test_unknown_context_uses_deferred_status_not_waiting_copy() -> None:
    at = _seed_read(_run_customer(), _csv_high_steel_and_ng())
    committed = dict(at.session_state[STATE_INTAKE_COMMITTED])
    committed["natural_gas_subtype"] = "unknown"
    at.session_state[STATE_INTAKE_COMMITTED] = committed
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert t("intake.status.deferred", ZH, n=1) in text
    assert t("intake.status.ready", ZH) not in text
    assert t("intake.read_rows", ZH, ready=1, held=1) in text
    assert "等待回覆" not in text
    assert t("intake.read_confirm_count", ZH, confirm=1) not in text
    labels = [str(button.label) for button in at.button]
    assert t("intake.btn.continue_ready", ZH) in labels
