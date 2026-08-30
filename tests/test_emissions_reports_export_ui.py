"""AppTest coverage for emissions reports page and hidden IFRS/Taiwan nav."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest
from test_emissions_report_closure import (
    bind_confirmed_company,
    seed_confirmed_report_workspace,
)

from carbon_ledger.intake import (
    IntakeMetadata,
    build_and_validate_intake,
    parse_uploaded_table,
    suggest_column_mapping_with_confidence,
)
from carbon_ledger.intake_exceptions import (
    initialize_committed,
    mapping_from_committed,
)
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    ANALYSIS_SOURCE_UPLOADED,
    STATE_ANALYSIS_SOURCE,
    STATE_INTAKE_FILE_NAME,
    STATE_INTAKE_RESULT,
    STATE_INTAKE_TABLE,
    STATE_RESULT,
    STATE_UPLOADED_ANALYSIS_COMPLETED,
    initialize_ui_state,
)
from carbon_ledger.ui.view_models import calculated_emissions_summary

REPO_ROOT = Path(__file__).resolve().parents[1]
APP_PATH = REPO_ROOT / "streamlit_app.py"
ZH = "zh-TW"


def _all_text(at: AppTest) -> str:
    chunks: list[str] = []
    for collection_name in (
        "markdown",
        "caption",
        "text",
        "info",
        "success",
        "warning",
        "error",
        "title",
        "header",
        "subheader",
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
    for button in list(at.button) + list(getattr(at, "download_button", [])):
        label = getattr(button, "label", None)
        if label is not None:
            chunks.append(str(label))
    return "\n".join(chunks)


def _fresh() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    initialize_ui_state(at.session_state)
    assert not at.exception
    return at


def _complete_result():
    csv = (
        "活動類型,使用量,單位,開始日期,結束日期,廠場\n"
        "外購電力,50000,kWh,2025-01-01,2025-01-31,高雄廠\n"
        "外購電力,1000,kWh,2025-02-01,2025-02-28,高雄廠\n"
    )
    table = parse_uploaded_table(file_name="ops.csv", data=csv.encode("utf-8"))
    detailed = suggest_column_mapping_with_confidence(
        list(table.columns), frame=table.frame
    )
    committed = initialize_committed(table, detailed)
    mapping = mapping_from_committed(table, committed)
    mapping.electricity_context = "enterprise"
    metadata = IntakeMetadata(
        source_name="ops.csv",
        site_id="高雄廠",
        document_date=date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="report_ui",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
    )
    intake = build_and_validate_intake(table, mapping, metadata)
    result = run_uploaded_pipeline(
        REPO_ROOT,
        run_id="report_ui",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
        include_ifrs_s2=True,
    )
    return result, intake, table


def test_customer_nav_titles_hide_ifrs_and_taiwan() -> None:
    assert t("nav.audit", ZH) == "碳排報表與匯出"
    assert t("nav.audit", "en") == "Emissions Reports & Exports"
    assert t("nav.ifrs", ZH) == "IFRS S1/S2"
    assert t("nav.taiwan", ZH) == "台灣溫室氣體與碳費"
    source = (REPO_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert 'visibility=_admin_nav' in source
    assert "app_pages/frameworks.py" in source
    assert "app_pages/taiwan_ghg.py" in source


def test_hidden_ifrs_and_taiwan_redirect_without_exception() -> None:
    at = _fresh()
    at.switch_page("app_pages/frameworks.py")
    at.run()
    assert not at.exception
    at.switch_page("app_pages/taiwan_ghg.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "合規總覽" in text or "尚未" in text


def test_no_company_shows_setup_cta() -> None:
    at = _fresh()
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "完成公司與報導期間設定" in text
    labels = [str(button.label) for button in at.button]
    assert any("完成公司與報導期間設定" in label for label in labels)


def test_company_without_analysis_goes_to_intake(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path)
    at = _fresh()
    bind_confirmed_company(at.session_state, company="報表測試公司")
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "尚無可匯出的碳排結果" in text
    labels = [str(button.label) for button in at.button]
    assert not any("完成公司與報導期間設定" in label for label in labels)
    assert any("前往排放資料與計算" in label for label in labels)


def test_complete_result_pdf_download_and_technical_files(
    monkeypatch, tmp_path
) -> None:
    monkeypatch.setenv("CEL_COMPANY_WORKSPACE_DIR", str(tmp_path))
    seed_confirmed_report_workspace(tmp_path, company="報表測試公司")
    result, intake, table = _complete_result()
    at = _fresh()
    bind_confirmed_company(at.session_state, company="報表測試公司")
    at.session_state[STATE_RESULT] = result
    at.session_state[STATE_INTAKE_RESULT] = intake
    at.session_state[STATE_INTAKE_TABLE] = table
    at.session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_UPLOADED
    at.session_state[STATE_INTAKE_FILE_NAME] = "ops.csv"
    at.session_state[STATE_UPLOADED_ANALYSIS_COMPLETED] = True
    at.switch_page("app_pages/audit_export.py")
    at.run()
    assert not at.exception
    text = _all_text(at)
    assert "碳排計算完成" in text
    assert t("report.pdf_button", ZH) in text
    labels = [str(item.label) for item in at.download_button]
    assert any("PDF" in label or "碳排摘要" in label for label in labels)
    assert any("zip" in label.lower() or "稽核包" in label for label in labels)
    data = None
    if "cel_emissions_pdf_cache" in at.session_state:
        data = at.session_state["cel_emissions_pdf_cache"].get("bytes")
    if isinstance(data, (bytes, bytearray)):
        assert bytes(data[:4]) == b"%PDF"
        assert len(data) > 1000
    total = calculated_emissions_summary(result, ZH)["calculated_tco2e"]
    assert f"{float(total):.2f}" in text
    expanders = [
        str(getattr(item, "label", "") or "") for item in getattr(at, "expander", [])
    ]
    assert any("專業覆核附件" in label for label in expanders)
