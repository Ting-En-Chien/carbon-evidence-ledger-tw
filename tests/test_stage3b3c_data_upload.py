"""Stage 3B.3c — Data Upload page customer hygiene."""

from __future__ import annotations

from pathlib import Path

from streamlit.testing.v1 import AppTest

from carbon_ledger.intake import MAX_UPLOAD_BYTES, MAX_UPLOAD_MB
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    STATE_INTAKE_BYTES,
    STATE_INTAKE_TABLE,
    STATE_RESULT,
    activate_demo_mode,
    get_analysis_source,
    initialize_ui_state,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
CONFIG_PATH = REPO_ROOT / ".streamlit" / "config.toml"
ZH = "zh-TW"


def _run_customer() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    at.switch_page("app_pages/data_intake.py")
    at.run()
    assert not at.exception
    return at


def _ss(at: AppTest, key: str, default=None):
    try:
        return at.session_state[key]
    except KeyError:
        return default


def _surface_text(at: AppTest, *, include_captions: bool = False) -> str:
    """Visible-by-default copy. Schema names live only in expander bodies."""
    chunks: list[str] = []
    names = ["title", "header", "subheader", "markdown", "text"]
    if include_captions:
        names.append("caption")
    for name in names:
        collection = getattr(at, name, None)
        if collection is None:
            continue
        for item in collection:
            value = getattr(item, "value", None) or getattr(item, "body", None)
            if value:
                chunks.append(str(value))
    for button in at.button:
        if getattr(button, "label", None):
            chunks.append(str(button.label))
    for item in getattr(at, "download_button", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
    for item in getattr(at, "expander", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
    for item in getattr(at, "file_uploader", []):
        if getattr(item, "label", None):
            chunks.append(str(item.label))
    return "\n".join(chunks)


def _expander_labels(at: AppTest) -> list[str]:
    return [str(getattr(item, "label", "") or "") for item in at.expander]


def _streamlit_max_upload_mb() -> int:
    for line in CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("maxUploadSize"):
            return int(stripped.split("=", 1)[1].strip())
    raise AssertionError("maxUploadSize missing from .streamlit/config.toml")


def test_customer_default_hides_raw_schema_names() -> None:
    at = _run_customer()
    text = _surface_text(at)
    for token in (
        "activity_type",
        "activity_value",
        "activity_start_date",
        "activity_end_date",
        "系統內部欄位名稱",
    ):
        assert token not in text
    assert "需要準備的資料" not in text
    assert "上傳能源與營運資料" in text
    assert "選擇公司檔案" in text


def test_advanced_schema_section_is_collapsed() -> None:
    at = _run_customer()
    labels = _expander_labels(at)
    assert not any("系統欄位格式" in label for label in labels)
    assert not any("系統內部欄位名稱" in label for label in labels)


def test_example_table_hidden_until_expanded() -> None:
    at = _run_customer()
    labels = _expander_labels(at)
    assert not any("查看填寫範例" in label for label in labels)
    primary = _surface_text(at)
    assert "50000" not in primary
    assert "2024-01-01" not in primary


def test_example_and_template_do_not_enter_analysis_state() -> None:
    at = _run_customer()
    assert _ss(at, STATE_INTAKE_TABLE) is None
    assert _ss(at, STATE_INTAKE_BYTES) is None
    assert _ss(at, STATE_RESULT) is None
    assert get_analysis_source(at.session_state) == ""
    labels = [str(item.label) for item in at.download_button]
    assert labels
    assert _ss(at, STATE_INTAKE_TABLE) is None


def test_only_one_primary_template_download() -> None:
    at = _run_customer()
    labels = [str(item.label) for item in at.download_button]
    assert len(labels) == 1
    assert "還沒有資料檔？下載範例" in labels[0] or "example" in labels[0].lower()
    assert "範例檔" not in labels[0]


def test_upload_frontend_limit_matches_backend_10mb() -> None:
    assert MAX_UPLOAD_MB == 10
    assert MAX_UPLOAD_BYTES == 10 * 1024 * 1024
    assert _streamlit_max_upload_mb() == MAX_UPLOAD_MB


def test_customer_copy_does_not_say_200mb() -> None:
    at = _run_customer()
    text = _surface_text(at)
    assert "200 MB" not in text
    assert "200MB" not in text
    assert "10 MB" in text
    assert t("intake.upload_limit", ZH) in text or "10 MB" in text


def test_csv_xlsx_uploader_still_present() -> None:
    at = _run_customer()
    assert len(at.file_uploader) >= 1
    accepted = {str(item).lower() for item in at.file_uploader[0].allowed_type}
    assert ".csv" in accepted
    assert ".xlsx" in accepted


def test_evidence_wizard_steps_remain() -> None:
    at = _run_customer()
    text = _surface_text(at, include_captions=True)
    assert "上傳能源與營運資料" in text
    assert "上傳公司現有資料" in text
    assert "01 上傳檔案" not in text


def test_demo_mode_still_activates_explicitly() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    assert _ss(at, STATE_RESULT) is None
    activate_demo_mode(at.session_state)
    at.run()
    assert _ss(at, STATE_RESULT) is not None
    at.switch_page("app_pages/data_intake.py")
    at.run()
    assert _ss(at, STATE_RESULT) is not None
