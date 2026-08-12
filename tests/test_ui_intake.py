"""AppTest coverage for Phase 9A Data Intake page."""

from __future__ import annotations

from pathlib import Path

import pytest
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
    assert "示範分析" in text
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
    assert "分析結果" in _all_text(at)


def test_language_switch_preserves_demo_pipeline_result() -> None:
    at = _run_app()
    before = at.session_state[STATE_RESULT]
    at.session_state[STATE_LANGUAGE] = "en"
    at.run()
    assert at.session_state[STATE_RESULT] is before


def _build_2025_upload_intake():
    from datetime import date

    import pandas as pd

    from carbon_ledger.intake import (
        ColumnMapping,
        IntakeMetadata,
        build_and_validate_intake,
        default_value_maps,
        parse_uploaded_table,
        suggest_activity_type,
        suggest_column_mapping,
        suggest_unit,
    )

    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "grid_electricity,120000,kWh,2025-01-01,2025-01-31\n"
        "natural_gas,8000,m3,2025-01-01,2025-01-31\n"
        "diesel,1200,L,2025-01-01,2025-01-31\n"
    )
    table = parse_uploaded_table(
        file_name="company_upload.csv",
        data=csv.encode("utf-8"),
    )
    suggestions = suggest_column_mapping(list(table.columns))
    activity_map, unit_map = default_value_maps(
        table,
        ColumnMapping(
            activity_type_column=suggestions["activity_type"],
            activity_value_column=suggestions["activity_value"],
            unit_column=suggestions["unit"],
        ),
    )
    activity_map = {
        key: value or suggest_activity_type(key) for key, value in activity_map.items()
    }
    unit_map = {key: value or suggest_unit(key) for key, value in unit_map.items()}
    mapping = ColumnMapping(
        activity_type_column=suggestions["activity_type"],
        activity_value_column=suggestions["activity_value"],
        unit_column=suggestions["unit"],
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
    )
    metadata = IntakeMetadata(
        source_name="碳排放練習工作簿.xlsx",
        site_id="site_main",
        document_date=date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="ui_intake_test",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
    )
    validated = build_and_validate_intake(table, mapping, metadata)
    # Present as the beginner workbook name used in UX copy / result labels.
    validated.file_name = "碳排放練習工作簿.xlsx"
    return validated, table


def _seed_validated_intake(at: AppTest) -> AppTest:
    from carbon_ledger.ui.state import (
        STATE_INTAKE_FILE_NAME,
        STATE_INTAKE_RESULT,
        STATE_INTAKE_STEP,
        STATE_INTAKE_TABLE,
    )

    intake, table = _build_2025_upload_intake()
    at.session_state[STATE_INTAKE_RESULT] = intake
    at.session_state[STATE_INTAKE_TABLE] = table
    at.session_state[STATE_INTAKE_FILE_NAME] = intake.file_name
    at.session_state[STATE_INTAKE_STEP] = 4
    at = _switch(at, "app_pages/data_intake.py")
    return at


def test_step04_success_shows_start_analysis_cta() -> None:
    at = _seed_validated_intake(_run_app())
    text = _all_text(at)
    assert "資料已準備完成" in text
    assert "使用這批資料開始分析" in text
    assert "返回修改資料" in text
    labels = [str(button.label) for button in at.button]
    assert "使用這批資料開始分析" in labels


def test_start_analysis_runs_uploaded_not_demo() -> None:
    from carbon_ledger.ui.state import (
        ANALYSIS_SOURCE_UPLOADED,
        STATE_ANALYSIS_SOURCE,
        STATE_RESULT,
    )

    at = _seed_validated_intake(_run_app())
    demo_before = at.session_state[STATE_RESULT]
    demo_ids = set(
        demo_before.activity_records_accepted["record_id"].astype(str).tolist()
    )
    button = next(
        b
        for b in at.button
        if str(b.label) == "使用這批資料開始分析"
    )
    button.click()
    at.run()
    assert not at.exception
    result = at.session_state[STATE_RESULT]
    assert result is not demo_before
    uploaded_ids = set(result.activity_records_accepted["record_id"].astype(str))
    assert uploaded_ids.isdisjoint(demo_ids)
    assert at.session_state[STATE_ANALYSIS_SOURCE] == ANALYSIS_SOURCE_UPLOADED
    assert len(result.activity_records_accepted) == 3


def test_uploaded_analysis_result_in_session_and_result_page_labels() -> None:
    from carbon_ledger.ui.state import (
        ANALYSIS_SOURCE_UPLOADED,
        STATE_ANALYSIS_SOURCE,
        run_uploaded_analysis,
    )

    at = _seed_validated_intake(_run_app())
    run_uploaded_analysis(at.session_state)
    at = _switch(at, "app_pages/dashboard.py")
    text = _all_text(at)
    assert at.session_state[STATE_ANALYSIS_SOURCE] == ANALYSIS_SOURCE_UPLOADED
    assert "碳排放練習工作簿.xlsx" in text
    assert "2025-01" in text
    assert "你上傳的公司資料" in text
    assert "虛構台灣扣件公司" not in text
    assert "2024 示範資料" not in text


def test_navigation_preserves_uploaded_analysis_state() -> None:
    from carbon_ledger.ui.state import (
        ANALYSIS_SOURCE_UPLOADED,
        STATE_ANALYSIS_SOURCE,
        STATE_RESULT,
        run_uploaded_analysis,
    )

    at = _seed_validated_intake(_run_app())
    run_uploaded_analysis(at.session_state)
    stored = at.session_state[STATE_RESULT]
    at = _switch(at, "app_pages/activity_explorer.py")
    at = _switch(at, "app_pages/issues_actions.py")
    at = _switch(at, "app_pages/dashboard.py")
    assert at.session_state[STATE_RESULT] is stored
    assert at.session_state[STATE_ANALYSIS_SOURCE] == ANALYSIS_SOURCE_UPLOADED
    assert "碳排放練習工作簿.xlsx" in _all_text(at)


def test_demo_mode_still_works_separately() -> None:
    from carbon_ledger.ui.state import (
        ANALYSIS_SOURCE_DEMO,
        STATE_ANALYSIS_SOURCE,
        run_analysis,
    )

    at = _run_app()
    assert at.session_state[STATE_ANALYSIS_SOURCE] == ANALYSIS_SOURCE_DEMO
    run_analysis(
        at.session_state,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )
    at.run()
    text = _all_text(at)
    assert "重新分析" in text
    assert "示範資料" in text
    assert at.session_state[STATE_ANALYSIS_SOURCE] == ANALYSIS_SOURCE_DEMO


def test_2025_electricity_uses_active_2025_factor_and_trace() -> None:
    from carbon_ledger.ui.state import run_uploaded_analysis
    from carbon_ledger.ui.view_models import (
        calculation_trace_fields,
        first_calculated_electricity_record_id,
        uncalculable_activity_cards,
    )

    at = _seed_validated_intake(_run_app())
    result = run_uploaded_analysis(at.session_state)
    record_id = first_calculated_electricity_record_id(result)
    assert record_id is not None
    calc = result.calculation_results
    row = calc[calc["record_id"].astype(str) == record_id].iloc[0]
    assert str(row["calculation_status"]) == "calculated"
    assert float(row["factor_value"]) == pytest.approx(0.466)
    assert "2025" in str(row["factor_id"])
    assert "2024" not in str(row["factor_id"])
    assert float(row["calculated_kgco2e"]) == pytest.approx(120000 * 0.466)

    trace = calculation_trace_fields(
        result, record_id, "zh-TW", official_source=True
    )
    assert trace["factor_year"] == "2025"
    assert float(trace["factor_value"]) == pytest.approx(0.466)
    assert trace["is_calculated"] is True

    blocked = uncalculable_activity_cards(result, "zh-TW")
    assert blocked
    for card in blocked:
        assert card["title"] == "目前無法計算"
        assert "0" != card["missing"]

    at = _switch(at, "app_pages/dashboard.py")
    text = _all_text(at)
    assert "目前無法計算" in text
    assert "0.466" in text
    assert "2025" in text
    assert "進階技術資料" in text or "查看完整證據鏈" in text


def test_technical_framework_not_required_on_first_screen() -> None:
    from carbon_ledger.ui.state import run_uploaded_analysis

    at = _seed_validated_intake(_run_app())
    run_uploaded_analysis(at.session_state)
    at = _switch(at, "app_pages/dashboard.py")
    text = _all_text(at)
    # Beginner sections present
    assert "已計算排放量" in text
    assert "優先處理" in text
    assert "排放趨勢" in text
    # Technical IDs are under progressive disclosure, not forced on first screen body
    # as the primary answer set.
    assert "candidate_id" not in text.lower()
    assert "snapshot_id" not in text.lower()


def test_result_meta_does_not_truncate_filename_in_kpi() -> None:
    from carbon_ledger.ui.state import run_uploaded_analysis

    at = _seed_validated_intake(_run_app())
    run_uploaded_analysis(at.session_state)
    at = _switch(at, "app_pages/dashboard.py")
    text = _all_text(at)
    assert "碳排放練習工作簿.xlsx" in text
    assert "2025-01" in text
    assert "你上傳的公司資料" in text
    # Filename must appear as full meta text, not a truncated KPI metric value.
    assert "碳排放練..." not in text


def test_sidebar_shows_rerun_not_start_after_uploaded_analysis() -> None:
    from carbon_ledger.ui.state import run_uploaded_analysis

    at = _seed_validated_intake(_run_app())
    run_uploaded_analysis(at.session_state)
    at = _switch(at, "app_pages/dashboard.py")
    labels = [str(button.label) for button in at.button]
    assert "重新分析" in labels
    assert "使用這批資料開始分析" not in labels
    expander_labels = [
        str(getattr(item, "label", "") or getattr(item, "header", "") or "")
        for item in getattr(at, "expander", [])
    ]
    assert any("分析設定" in label for label in expander_labels) or any(
        "分析設定" in str(getattr(item, "label", "")) for item in at.button
    )


def test_chart_heights_are_bounded() -> None:
    from carbon_ledger.ui import charts

    assert charts.CHART_HEIGHT_OVERVIEW <= 340
    assert charts.CHART_HEIGHT_SMALL <= 260
    assert charts.CHART_HEIGHT_COMPACT <= 160
    result_fn = charts._contribution_bar_spec
    single = result_fn(height=charts.CHART_HEIGHT_COMPACT)
    assert int(single["height"]) <= 160
