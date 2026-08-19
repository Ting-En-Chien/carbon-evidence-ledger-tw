"""Stage 4.2F-C2 — mapping memory and compact reuse UX."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.intake import parse_uploaded_table
from carbon_ledger.intake_mapping_memory import (
    EVENT_CUSTOMER_CONFIRMED,
    append_provenance_event,
    lookup_remembered_mapping,
    snapshot_rememberable_committed,
    structural_fingerprint,
)
from carbon_ledger.ui.i18n import STATE_LANGUAGE, t
from carbon_ledger.ui.state import (
    STATE_COMPANY_MASTER,
    STATE_INTAKE_COMMITTED,
    STATE_INTAKE_MAPPING_MEMORY,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_SHOW_MAPPING_EDITOR,
    STATE_INTAKE_STEP,
    STATE_INTAKE_TABLE,
    clear_intake_state,
    initialize_ui_state,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
ZH = "zh-TW"
EN = "en"
INTAKE_PAGE = "app_pages/data_intake.py"
CONFIRMED_UBN = "12345675"
OTHER_UBN = "24681358"
INTERNAL_TERMS = (
    "High",
    "Medium",
    "Low",
    "schema",
    "canonical",
    "parser",
    "fingerprint",
    "activity_type",
    "activity_value",
    "site_id",
    "system_suggested",
    "customer_confirmed",
    "remembered_mapping_applied",
)


def _run_customer() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    at.switch_page(INTAKE_PAGE)
    at.run()
    assert not at.exception
    return at


def _confirm_company(at: AppTest, ubn: str = CONFIRMED_UBN) -> None:
    at.session_state[STATE_COMPANY_MASTER] = {
        "company_name": (
            "長興材料工業股份有限公司"
            if ubn == CONFIRMED_UBN
            else "未公開財務示範股份有限公司"
        ),
        "customer_confirmed_at": "2026-08-18T00:00:00+00:00",
        "unified_business_number": ubn,
    }


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
    for item in getattr(at, "expander", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
    return "\n".join(chunks)


def _csv_medium(value: str = "10") -> bytes:
    return (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        f"採購鋼材,{value},t,2025-01-01,2025-01-31,高雄廠\n"
    ).encode("utf-8")


def _csv_unmatched() -> bytes:
    return (
        "說明欄,數字甲,數字乙,單位,開始日期,結束日期,廠場\n"
        "採購鋼材,10,20,t,2025-01-01,2025-01-31,高雄廠\n"
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
    return at


def _remembered_for(at: AppTest, data: bytes, ubn: str = CONFIRMED_UBN):
    table = parse_uploaded_table(file_name="ops.csv", data=data)
    return lookup_remembered_mapping(
        at.session_state,
        ubn=ubn,
        fingerprint=structural_fingerprint(
            columns=list(table.columns),
            header_row_index=table.header_row_index,
        ),
    )


def test_first_upload_resolves_medium_and_remembers_after_commit() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium())
    text = _all_text(at)
    assert t("intake.memory.found", ZH) not in text
    assert t("intake.ex.queue_title", ZH) in text
    assert t("intake.ex.apply", ZH) in [str(b.label) for b in at.button]
    at = _click_label(at, t("intake.ex.apply", ZH))
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    assert _state_get(at, STATE_INTAKE_RESULT) is not None
    found = _remembered_for(at, _csv_medium())
    assert found is not None
    assert found["columns"]["activity_value"] == "用量"


def test_second_upload_offers_memory_and_does_not_apply_silently() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("10"))
    at = _click_label(at, t("intake.ex.apply", ZH))
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    clear_intake_state(at.session_state)
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("99"), name="ops-feb.csv")
    text = _all_text(at)
    assert t("intake.memory.found", ZH) in text
    assert t("intake.memory.explain", ZH) in text
    labels = [str(button.label) for button in at.button]
    assert t("intake.memory.use", ZH) in labels
    assert t("intake.memory.recheck", ZH) in labels
    assert t("intake.ex.apply", ZH) not in labels
    assert t("intake.ex.column_q", ZH, column="用量") not in text
    committed = at.session_state[STATE_INTAKE_COMMITTED]
    assert "activity_value" not in (committed.get("columns") or {})
    for token in INTERNAL_TERMS:
        assert token not in text
    opening_fragments = [
        str(item.value)
        for item in at.markdown
        if str(getattr(item, "value", "")).strip().startswith(
            '<div class="cel-memory-offer">'
        )
    ]
    assert opening_fragments == []


def test_use_previous_settings_reduces_mapping_questions() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("10"))
    at = _click_label(at, t("intake.ex.apply", ZH))
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    clear_intake_state(at.session_state)
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("99"), name="ops-feb.csv")
    at = _click_label(at, t("intake.memory.use", ZH))
    text = _all_text(at)
    assert t("intake.status.ready", ZH) in text
    assert t("intake.read_confirm_count", ZH, confirm=1) not in text
    assert t("intake.ex.column_q", ZH, column="用量") not in text
    assert t("intake.btn.continue_ready", ZH) in [
        str(b.label) for b in at.button
    ]
    columns = at.session_state[STATE_INTAKE_COMMITTED]["columns"]
    assert columns["activity_value"] == "用量"


def test_recheck_keeps_normal_inference() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("10"))
    at = _click_label(at, t("intake.ex.apply", ZH))
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    clear_intake_state(at.session_state)
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("99"), name="ops-feb.csv")
    at = _click_label(at, t("intake.memory.recheck", ZH))
    text = _all_text(at)
    assert t("intake.ex.queue_title", ZH) in text
    assert t("intake.ex.column_q", ZH, column="用量") in text
    assert "activity_value" not in (
        at.session_state[STATE_INTAKE_COMMITTED].get("columns") or {}
    )


def test_different_company_does_not_see_remembered_setting() -> None:
    at = _run_customer()
    _confirm_company(at, CONFIRMED_UBN)
    at = _seed_read(at, _csv_medium())
    at = _click_label(at, t("intake.ex.apply", ZH))
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    clear_intake_state(at.session_state)
    _confirm_company(at, OTHER_UBN)
    at = _seed_read(at, _csv_medium("99"), name="ops-other.csv")
    text = _all_text(at)
    assert t("intake.memory.found", ZH) not in text
    assert t("intake.ex.column_q", ZH, column="用量") in text


def test_changed_structure_falls_back_to_exceptions() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium())
    at = _click_label(at, t("intake.ex.apply", ZH))
    at = _click_label(at, t("intake.btn.continue_ready", ZH))
    clear_intake_state(at.session_state)
    _confirm_company(at)
    at = _seed_read(at, _csv_unmatched(), name="ops-changed.csv")
    text = _all_text(at)
    assert t("intake.memory.found", ZH) not in text
    assert t("intake.ex.column_q", ZH, column="說明欄") in text
    assert t("intake.ex.usage_q_blank", ZH) not in text


def test_draft_editor_is_not_remembered() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium(), editor=True)
    assert _remembered_for(at, _csv_medium()) is None
    assert _state_get(at, STATE_INTAKE_MAPPING_MEMORY) in ({}, None)


def test_history_uses_customer_language() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium())
    at = _click_label(at, t("intake.ex.apply", ZH))
    text = _all_text(at)
    assert t("intake.memory.history", ZH) in text
    for token in INTERNAL_TERMS:
        assert token not in text


def test_only_one_question_is_visible_and_next_appears_after_apply() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_unmatched())
    text = _all_text(at)
    assert t("intake.ex.column_q", ZH, column="說明欄") in text
    assert t("intake.ex.usage_q_blank", ZH) not in text
    assert t("intake.ex.progress", ZH, current=1, total=2) in text
    assert len(
        [button for button in at.button if button.label == t("intake.ex.apply", ZH)]
    ) == 1
    at = _click_label(at, t("intake.ex.apply", ZH))
    second = _all_text(at)
    assert t("intake.ex.column_q", ZH, column="說明欄") not in second
    assert t("intake.ex.usage_q_blank", ZH) in second
    assert t("intake.ex.progress", ZH, current=2, total=2) in second
    assert "activity_value" not in text


def test_company_b_cannot_render_company_a_history() -> None:
    at = _run_customer()
    append_provenance_event(
        at.session_state,
        event=EVENT_CUSTOMER_CONFIRMED,
        company_ubn=CONFIRMED_UBN,
        field="activity_value",
        committed="甲公司私有欄位",
    )
    _confirm_company(at, OTHER_UBN)
    at = _seed_read(at, _csv_medium())
    text = _all_text(at)
    assert "甲公司私有欄位" not in text


def test_confirmed_company_name_and_ubn_replace_unset_header() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium())
    text = _all_text(at)
    assert "長興材料工業股份有限公司" in text
    assert CONFIRMED_UBN in text
    assert t("sidebar.company_unset", ZH) not in text


def test_english_memory_copy_is_aligned() -> None:
    at = _run_customer()
    at.session_state[STATE_LANGUAGE] = EN
    if len(at.segmented_control) >= 1:
        try:
            at.segmented_control[0].set_value("EN")
        except Exception:
            pass
    at.run()
    assert not at.exception
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("10"))
    at = _click_label(at, t("intake.ex.apply", EN))
    at = _click_label(at, t("intake.btn.continue_ready", EN))
    clear_intake_state(at.session_state)
    at.session_state[STATE_LANGUAGE] = EN
    _confirm_company(at)
    at = _seed_read(at, _csv_medium("99"), name="ops-feb.csv")
    text = _all_text(at)
    assert t("intake.memory.found", EN) in text
    assert t("intake.memory.use", EN) in text
    assert t("intake.memory.recheck", EN) in text
    assert "intake.memory.found" not in text
    for token in INTERNAL_TERMS:
        assert token not in text


def test_unknown_answer_is_not_stored_in_memory_snapshot() -> None:
    at = _run_customer()
    _confirm_company(at)
    at = _seed_read(at, _csv_medium())
    at = _click_label(at, t("intake.ex.apply", ZH))
    committed = dict(at.session_state[STATE_INTAKE_COMMITTED])
    committed["natural_gas_subtype"] = "unknown"
    snapshot = snapshot_rememberable_committed(committed)
    assert "natural_gas_subtype" not in snapshot
    assert snapshot["columns"]["activity_value"] == "用量"
