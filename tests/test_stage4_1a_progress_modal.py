"""Stage 4.1a — analysis progress modal and result-first dashboard."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

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
from carbon_ledger.pipeline import run_uploaded_pipeline
from carbon_ledger.ui.formatting import (
    RESULT_TCO2E_DECIMALS,
    format_result_tco2e_amount,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import (
    ANALYSIS_PHASE_ANALYZING,
    ANALYSIS_PHASE_COMPLETE,
    ANALYSIS_PHASE_FAILED,
    analysis_phase,
    analysis_stage_keys,
    begin_analysis_presentation_reset,
    consume_analysis_run_requests,
    post_analysis_dashboard_sections,
    progress_percent_for_stages,
    should_open_analysis_progress_dialog,
)
from carbon_ledger.ui.state import (
    STATE_ANALYSIS_FAILURE,
    STATE_ANALYSIS_PHASE,
    STATE_ANALYSIS_RUNNING,
    STATE_ANIMATION_RUN,
    STATE_HERO_EMISSIONS_PLAY,
    STATE_RESULT,
    STATE_RESULT_REVEAL_PENDING,
    STATE_RUN_UPLOADED_REQUEST,
    activate_demo_mode,
    initialize_ui_state,
)
from carbon_ledger.ui.view_models import (
    calculated_emissions_by_product_scope,
    calculated_emissions_summary,
    scope_kpi_states,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HERO_JS = REPO_ROOT / "src/carbon_ledger/ui/hero_emissions_countup.js"
HERO_SHA = "70cd43b7f1fa2bedf4485bc7846278b736e1c183961c6c7117d6cc8b5f5828c0"
APP_PATH = REPO_ROOT / "streamlit_app.py"
FIXED_INGESTED_AT = pd.Timestamp("2025-02-01T00:00:00Z")


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
    return "\n".join(chunks)


def _intake_and_run(csv: str) -> object:
    table = parse_uploaded_table(file_name="stage41a.csv", data=csv.encode("utf-8"))
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
        site_column=suggestions.get("site_id") or "",
        use_file_dates=True,
        start_date_column=suggestions["activity_start_date"],
        end_date_column=suggestions["activity_end_date"],
        activity_type_value_map=activity_map,
        unit_value_map=unit_map,
        natural_gas_subtype="NG1",
        diesel_context="company_vehicle",
        electricity_context="enterprise",
    )
    intake = build_and_validate_intake(
        table,
        mapping,
        IntakeMetadata(
            source_name="stage41a.csv",
            site_id="高雄廠",
            document_date=date(2025, 1, 31),
            data_quality_tier="unknown",
            intake_run_id="stage41a",
            ingested_at=FIXED_INGESTED_AT,
        ),
    )
    return run_uploaded_pipeline(
        REPO_ROOT,
        run_id="stage41a",
        ingested_at=FIXED_INGESTED_AT,
        source_documents=intake.source_documents,
        accepted_activities=intake.accepted_activities,
        include_ghg=True,
        include_ifrs_s2=True,
    )


def test_start_analysis_enters_analyzing_state() -> None:
    state: dict = {}
    initialize_ui_state(state)
    begin_analysis_presentation_reset(state)
    assert analysis_phase(state) == ANALYSIS_PHASE_ANALYZING
    assert state[STATE_ANALYSIS_RUNNING] is True
    assert state[STATE_RESULT] is None


def test_old_result_hidden_while_analyzing() -> None:
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_RESULT] = object()
    state[STATE_HERO_EMISSIONS_PLAY] = "old"
    state[STATE_RESULT_REVEAL_PENDING] = "old"
    begin_analysis_presentation_reset(state)
    assert state[STATE_RESULT] is None
    assert state[STATE_HERO_EMISSIONS_PLAY] is None
    assert state[STATE_RESULT_REVEAL_PENDING] is None


def test_progress_modal_markup_and_real_stages() -> None:
    source = (REPO_ROOT / "src/carbon_ledger/ui/motion.py").read_text(encoding="utf-8")
    assert "launch_analysis_progress_dialog" in source
    assert "@st.dialog" in source
    assert "data-cel-analysis-modal" in source
    assert "time.sleep(" not in source
    keys = [key for key, _ in analysis_stage_keys()]
    assert keys == [
        "reading",
        "normalize",
        "factors",
        "calculate",
        "quality",
        "issues",
    ]
    assert progress_percent_for_stages(0, 6) == 0
    assert progress_percent_for_stages(1, 6) == 17
    assert progress_percent_for_stages(2, 6) == 33
    assert progress_percent_for_stages(6, 6) == 100
    assert t("analysis.stage.factors", "zh-TW") == "配對排放係數與熱值"


def test_failure_keeps_dialog_state() -> None:
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_FAILED
    state[STATE_ANALYSIS_FAILURE] = t("error.analysis_failed_safe", "zh-TW")
    assert analysis_phase(state) == ANALYSIS_PHASE_FAILED
    failure_ui = (REPO_ROOT / "src/carbon_ledger/ui/motion.py").read_text(
        encoding="utf-8"
    )
    assert "analysis.return_to_data" in failure_ui
    assert "error.analysis_incomplete" in failure_ui


def test_emissions_summary_precedes_attention_in_dashboard_source() -> None:
    source = (REPO_ROOT / "app_pages/dashboard.py").read_text(encoding="utf-8")
    emissions_at = source.find('scroll_key="emissions-summary"')
    next_at = source.find('scroll_key="next-step"')
    assert emissions_at != -1
    assert next_at != -1
    assert emissions_at < next_at
    assert post_analysis_dashboard_sections()[0] == "emissions-summary"
    assert post_analysis_dashboard_sections()[3] == "next-step"


def test_demo_dashboard_emissions_summary_is_above_attention() -> None:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    activate_demo_mode(at.session_state)
    at.run()
    assert not at.exception
    text = _all_text(at)
    emissions_at = text.find("排放資料摘要")
    next_at = text.find("下一步")
    assert emissions_at != -1
    assert next_at != -1
    assert emissions_at < next_at


def test_hero_uses_two_decimal_result_precision() -> None:
    assert RESULT_TCO2E_DECIMALS == 2
    assert format_result_tco2e_amount(136.47) == "136.47"
    assert format_result_tco2e_amount(136) == "136.00"
    hero_source = (
        REPO_ROOT / "src/carbon_ledger/ui/motion.py"
    ).read_text(encoding="utf-8")
    assert "format_result_tco2e_amount" in hero_source
    digest = hashlib.sha256(HERO_JS.read_bytes()).hexdigest()
    assert digest == HERO_SHA


def test_scope_2_pending_when_electricity_not_calculated() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31\n"
        "柴油,1200,L,2025-01-01,2025-01-31\n"
    )
    result = _intake_and_run(csv)
    states = scope_kpi_states(result)
    assert states["scope_1"]["state"] == "calculated"
    assert states["scope_1"]["value"] > 0
    assert states["scope_2"]["state"] == "pending"
    assert states["scope_2"]["value"] is None


def test_scope_2_shows_calculated_value_when_backend_has_electricity() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "外購電力,50000,kWh,2025-01-01,2025-01-31\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31\n"
        "柴油,1200,L,2025-01-01,2025-01-31\n"
    )
    result = _intake_and_run(csv)
    states = scope_kpi_states(result)
    scopes = calculated_emissions_by_product_scope(result)
    summary = calculated_emissions_summary(result)
    assert states["scope_2"]["state"] == "calculated"
    assert states["scope_2"]["value"] == pytest.approx(float(scopes["scope_2"]))
    assert states["scope_1"]["value"] == pytest.approx(float(scopes["scope_1"]))
    assert summary["calculated_tco2e"] == pytest.approx(
        float(states["scope_1"]["value"]) + float(states["scope_2"]["value"])
    )


def test_counts_come_from_backend_not_hardcoded() -> None:
    csv = (
        "activity_type,activity_value,unit,activity_start_date,activity_end_date\n"
        "外購電力,50000,kWh,2025-01-01,2025-01-31\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31\n"
        "柴油,1200,L,2025-01-01,2025-01-31\n"
        "採購鋼材,10,t,2025-01-01,2025-01-31\n"
    )
    result = _intake_and_run(csv)
    summary = calculated_emissions_summary(result)
    assert summary["calculated_row_count"] == 3
    assert int(summary["calculated_tco2e"] or 0) != 5311
    motion = (REPO_ROOT / "src/carbon_ledger/ui/motion.py").read_text(encoding="utf-8")
    assert "136.47" not in motion
    assert "time.sleep(" not in motion


def test_request_flags_consumed_and_dialog_lifecycle() -> None:
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_RUN_UPLOADED_REQUEST] = True
    clicked, uploaded = consume_analysis_run_requests(state)
    assert clicked is True
    assert uploaded is True
    assert state[STATE_RUN_UPLOADED_REQUEST] is False
    assert should_open_analysis_progress_dialog(state, run_clicked=True)
    state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_COMPLETE
    assert should_open_analysis_progress_dialog(state, run_clicked=False)
    state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_ANALYZING
    assert should_open_analysis_progress_dialog(state, run_clicked=False)


def test_reanalysis_resets_animation_token() -> None:
    state: dict = {}
    initialize_ui_state(state)
    begin_analysis_presentation_reset(state)
    first = state[STATE_ANIMATION_RUN]
    begin_analysis_presentation_reset(state)
    assert state[STATE_ANIMATION_RUN]
    assert state[STATE_ANIMATION_RUN] != first
    assert state[STATE_RESULT] is None


def test_dashboard_hides_results_while_analyzing() -> None:
    source = (REPO_ROOT / "app_pages/dashboard.py").read_text(encoding="utf-8")
    running_at = source.find("STATE_ANALYSIS_RUNNING")
    stop_at = source.find("st.stop()")
    assert running_at != -1
    assert stop_at != -1
    assert running_at < stop_at
    assert "ANALYSIS_PHASE_COMPLETE" in source
    assert "ANALYSIS_PHASE_ANALYZING" in source
    app = APP_PATH.read_text(encoding="utf-8")
    assert "should_open_analysis_progress_dialog" in app
    motion = (REPO_ROOT / "src/carbon_ledger/ui/motion.py").read_text(encoding="utf-8")
    assert "ANALYSIS_PHASE_COMPLETE" in motion
    assert "st.rerun()" in motion
