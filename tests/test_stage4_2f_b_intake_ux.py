"""Stage 4.2F-B — customer-first data intake information architecture."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.intake import (
    parse_uploaded_table,
    suggest_column_mapping_with_confidence,
)
from carbon_ledger.intake_exceptions import initialize_committed, summary_counts
from carbon_ledger.ui.i18n import STATE_LANGUAGE, t
from carbon_ledger.ui.state import (
    STATE_INTAKE_SHOW_MAPPING_EDITOR,
    STATE_INTAKE_STEP,
    STATE_INTAKE_TABLE,
    initialize_ui_state,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
ZH = "zh-TW"
EN = "en"
INTAKE_PAGE = "app_pages/data_intake.py"
SCHEMA_TOKENS = (
    "activity_type",
    "activity_value",
    "activity_start_date",
    "activity_end_date",
)
OLD_COPY = (
    "我們看懂這份 Excel",
    "需要準備的資料",
    "不知道怎麼準備資料",
    "下載資料範本",
    "正確，繼續",
    "有地方不對",
)
RAW_KEYS = (
    "ev.landing.title",
    "intake.read_title",
    "intake.read_found",
    "intake.read_recognized",
    "intake.read_confirm_count",
    "intake.btn.continue_ready",
    "intake.ng_option_1",
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
    for item in getattr(at, "download_button", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
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
    for item in getattr(at, "file_uploader", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
    return "\n".join(chunks)


def _company_csv(*, include_gas: bool = False) -> bytes:
    rows = [
        "活動類型,用量,單位,開始日期,結束日期,廠場",
        "外購電力,100,kWh,2025-01-01,2025-01-31,高雄廠",
    ]
    if include_gas:
        rows.append("天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠")
    return ("\n".join(rows) + "\n").encode("utf-8")


def _seed_read_result(at: AppTest, data: bytes, *, editor: bool = False) -> AppTest:
    table = parse_uploaded_table(file_name="ops.csv", data=data)
    at.session_state[STATE_INTAKE_TABLE] = table
    at.session_state[STATE_INTAKE_STEP] = 2
    at.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] = editor
    at.switch_page(INTAKE_PAGE)
    at.run()
    assert not at.exception
    return at


def _expected_counts(table) -> tuple[int, int]:
    detailed = suggest_column_mapping_with_confidence(list(table.columns))
    committed = initialize_committed(table, detailed)
    counts = summary_counts(table, detailed, committed)
    return counts["recognized"], counts["confirm"]


def test_default_entry_emphasizes_existing_company_file() -> None:
    at = _run_customer()
    text = _all_text(at)
    assert t("ev.landing.title", ZH) in text
    assert t("ev.landing.body", ZH) in text
    assert t("ev.landing.primary", ZH) in text
    assert t("intake.upload_existing_title", ZH) in text
    assert t("intake.upload_label", ZH) in text
    assert len(at.file_uploader) >= 1


def test_template_download_is_secondary_fallback() -> None:
    at = _run_customer()
    labels = [str(item.label) for item in at.download_button]
    assert labels == [t("intake.template_fallback", ZH)]
    text = _all_text(at)
    assert "下載資料範本" not in text


def test_internal_schema_names_absent_from_default_path() -> None:
    at = _run_customer()
    text = _all_text(at)
    for token in SCHEMA_TOKENS:
        assert token not in text
    expander_labels = [
        str(getattr(item, "label", "") or "") for item in at.expander
    ]
    assert not any("系統欄位格式" in label for label in expander_labels)
    assert not any("進階" in label for label in expander_labels)


def test_old_understood_and_prepare_copy_absent() -> None:
    at = _run_customer()
    text = _all_text(at)
    for token in OLD_COPY:
        assert token not in text
    at = _seed_read_result(at, _company_csv())
    text = _all_text(at)
    for token in OLD_COPY:
        assert token not in text
    assert t("intake.read_title", ZH) in text


def test_recognition_result_uses_real_available_counts() -> None:
    at = _run_customer()
    data = _company_csv(include_gas=True)
    table = parse_uploaded_table(file_name="ops.csv", data=data)
    mapped, confirm = _expected_counts(table)
    at = _seed_read_result(at, data)
    text = _all_text(at)
    assert t("intake.read_found", ZH, n=len(table.frame)) in text
    assert t("intake.read_recognized", ZH, n=mapped) in text
    assert t("intake.read_confirm_count", ZH, confirm=confirm) in text
    assert confirm >= 1
    assert "可計算" not in text
    assert "ready to calculate" not in text.lower()


def test_explicit_confirmation_still_required() -> None:
    at = _seed_read_result(_run_customer(), _company_csv())
    labels = [str(button.label) for button in at.button]
    assert t("intake.btn.accept", ZH) not in labels
    assert t("intake.btn.continue_ready", ZH) not in labels
    assert t("intake.ex.apply", ZH) in labels
    assert "完成剩餘" in _all_text(at)
    assert at.session_state[STATE_INTAKE_STEP] == 2
    assert at.session_state[STATE_INTAKE_SHOW_MAPPING_EDITOR] is False


def test_full_mapping_editor_hidden_by_default() -> None:
    at = _seed_read_result(_run_customer(), _company_csv())
    text = _all_text(at)
    assert t("intake.editor.required", ZH) not in text
    assert t("intake.map_activity_type", ZH) not in text
    assert t("intake.btn.fix", ZH) in [str(button.label) for button in at.button]


def test_opened_editor_uses_customer_labels_and_grouped_controls() -> None:
    at = _seed_read_result(
        _run_customer(),
        _company_csv(include_gas=True),
        editor=True,
    )
    text = _all_text(at)
    assert t("intake.editor.required", ZH) in text
    assert t("intake.editor.optional", ZH) in text
    assert t("intake.editor.dates", ZH) in text
    assert t("intake.map_activity_type", ZH) in text
    for token in SCHEMA_TOKENS:
        assert token not in text
    ng_options: list[str] = []
    for item in getattr(at, "radio", []):
        ng_options.extend(str(option) for option in (item.options or []))
    assert t("intake.ng_option_1", ZH) in ng_options
    assert t("intake.ng_option_2", ZH) in ng_options
    assert t("intake.ng_type_unknown", ZH) in ng_options
    assert "NG1" not in ng_options
    assert "NG2" not in ng_options


def test_chinese_and_english_render_without_raw_keys() -> None:
    at = _run_customer()
    zh = _all_text(at)
    for key in RAW_KEYS:
        assert key not in zh
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
    en = _all_text(at)
    assert t("ev.landing.title", EN) in en
    assert t("intake.upload_existing_title", EN) in en
    assert t("intake.template_fallback", EN) in en
    for key in RAW_KEYS:
        assert key not in en
    for token in SCHEMA_TOKENS:
        assert token not in en
    at = _seed_read_result(at, _company_csv())
    en_read = _all_text(at)
    assert t("intake.read_title", EN) in en_read
    assert t("intake.ex.apply", EN) in en_read
    assert t("intake.btn.accept", EN) not in en_read
    for key in RAW_KEYS:
        assert key not in en_read
