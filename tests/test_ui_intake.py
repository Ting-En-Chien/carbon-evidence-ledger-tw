"""AppTest coverage for Phase 9A Data Intake page."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.ui.i18n import STATE_LANGUAGE
from carbon_ledger.ui.state import STATE_RESULT

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"


def _run_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
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
        label = getattr(button, "label", None)
        if label is not None:
            chunks.append(str(label))
    for item in getattr(at, "download_button", []):
        label = getattr(item, "label", None)
        if label is not None:
            chunks.append(str(label))
    return "\n".join(chunks)


def _switch(at: AppTest, page: str) -> AppTest:
    at.switch_page(page)
    at.run()
    assert not at.exception
    return at


def _switch_language(at: AppTest, option: str) -> AppTest:
    code = "en" if option == "EN" else "zh-TW"
    at.session_state[STATE_LANGUAGE] = code
    if len(at.segmented_control) >= 1:
        try:
            at.segmented_control[0].set_value(option)
        except Exception:
            pass
    at.run()
    assert not at.exception
    return at


def test_data_intake_page_exists() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    text = _all_text(at)
    assert "匯入公司資料" in text
    assert "資料匯入" in text or "匯入" in text


def test_traditional_chinese_page_title_default() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    assert "匯入公司資料" in _all_text(at)


def test_english_page_title_after_language_switch() -> None:
    at = _switch_language(_run_app(), "EN")
    assert at.session_state[STATE_LANGUAGE] == "en"
    at = _switch(at, "app_pages/data_intake.py")
    assert "Import company data" in _all_text(at)
    assert at.session_state[STATE_LANGUAGE] == "en"


def test_uploader_and_template_download_exist() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    assert len(at.file_uploader) >= 1
    labels = [str(item.label) for item in at.download_button]
    assert any("範本" in label or "template" in label.lower() for label in labels)


def test_uploader_accepts_csv_xlsx_not_pdf() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    uploader = at.file_uploader[0]
    accepted = {str(item).lower() for item in uploader.allowed_type}
    assert ".csv" in accepted
    assert ".xlsx" in accepted
    assert ".pdf" not in accepted


def test_step_labels_exist() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    text = _all_text(at)
    assert "01 上傳檔案" in text
    assert "02 對應欄位" in text
    assert "03 確認資料" in text
    assert "04 檢查結果" in text


def test_example_and_demo_notice_exist() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    text = _all_text(at)
    assert "範例資料，不會自動匯入" in text
    assert "尚未取代示範分析結果" in text
    assert "不需要先修改原本 Excel 欄位名稱" in text
    assert "activity_type" in text
    assert "activity_value" in text
    labels = [str(item.label) for item in at.download_button]
    assert any("範例檔" in label or "example file" in label.lower() for label in labels)


def test_no_uncaught_exception_on_intake_page() -> None:
    at = _switch(_run_app(), "app_pages/data_intake.py")
    assert not at.exception


def test_dashboard_still_starts_and_demo_result_unchanged() -> None:
    at = _run_app()
    before = at.session_state[STATE_RESULT]
    at = _switch(at, "app_pages/data_intake.py")
    at = _switch(at, "app_pages/dashboard.py")
    assert at.session_state[STATE_RESULT] is before
    assert "碳資料總覽" in _all_text(at)


def test_language_switch_preserves_demo_pipeline_result() -> None:
    at = _run_app()
    before = at.session_state[STATE_RESULT]
    at.session_state[STATE_LANGUAGE] = "en"
    at.run()
    assert at.session_state[STATE_RESULT] is before
