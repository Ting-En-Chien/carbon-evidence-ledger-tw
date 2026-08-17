"""RC QA — Streamlit session isolation, reanalysis, and double-click guards."""

from __future__ import annotations

import json
from pathlib import Path

from rc_qa_support import (
    REPO_ROOT,
    dataset_a_csv,
    dataset_b_csv,
    intake_and_run,
)
from streamlit.testing.v1 import AppTest

from carbon_ledger.export import export_run_bundle
from carbon_ledger.potential_duplicates import (
    DECISION_KEEP_ALL,
    decide_potential_duplicate_group,
    decision_to_map_payload,
    groups_from_intake,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.motion import (
    ANALYSIS_PHASE_ANALYZING,
    begin_analysis_presentation_reset,
    customer_safe_analysis_error,
)
from carbon_ledger.ui.state import (
    ANALYSIS_SOURCE_DEMO,
    ANALYSIS_SOURCE_UPLOADED,
    STATE_ANALYSIS_PHASE,
    STATE_ANALYSIS_RUNNING,
    STATE_ANALYSIS_SOURCE,
    STATE_INTAKE_DUPLICATE_REVIEW,
    STATE_INTAKE_FILE_NAME,
    STATE_INTAKE_RESULT,
    STATE_RESULT,
    activate_demo_mode,
    clear_analysis_result,
    get_analysis_source,
    initialize_ui_state,
    is_synthetic_analysis,
    run_uploaded_analysis,
)
from carbon_ledger.ui.view_models import calculated_emissions_summary

APP_PATH = REPO_ROOT / "streamlit_app.py"
ZH = "zh-TW"
ENGINEERING_TOKENS = (
    "grid_electricity",
    "stationary_combustion",
    "mobile_combustion",
    "factor_id",
    "source_id",
    "rule_id",
    "record_id",
    "evaluation_id",
    "MONITORING_PARTIAL",
    "BASELINE_CAPTURED",
    "NOT_ACTIVATED",
    "calculation_trace",
    "schema_version",
)


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
            for attr in ("value", "body", "label"):
                value = getattr(item, attr, None)
                if value is not None:
                    chunks.append(str(value))
    return "\n".join(chunks)


def _run_app() -> AppTest:
    at = AppTest.from_file(str(APP_PATH), default_timeout=120)
    at.run()
    assert not at.exception
    return at


def _keep_all_lookalikes(intake) -> dict:
    """RC fixtures may contain legitimate repeated activities; keep them all."""
    payload = {}
    for group in groups_from_intake(intake):
        decided = decide_potential_duplicate_group(
            group,
            DECISION_KEEP_ALL,
            reviewed_at="2026-08-15T00:00:00Z",
            review_session="rc_qa_state",
        )
        payload[group.group_id] = decision_to_map_payload(decided)
    return payload


def test_replacing_dataset_clears_previous_result() -> None:
    result_a, intake_a = intake_and_run(
        dataset_a_csv(rows=120), run_id="state_a", file_name="A.csv"
    )
    result_b, intake_b = intake_and_run(
        dataset_b_csv(rows=200), run_id="state_b", file_name="B.csv"
    )
    total_a = calculated_emissions_summary(result_a)["calculated_tco2e"]
    total_b = calculated_emissions_summary(result_b)["calculated_tco2e"]
    assert total_a != total_b

    state: dict = {}
    initialize_ui_state(state)
    state[STATE_INTAKE_RESULT] = intake_a
    state[STATE_INTAKE_FILE_NAME] = "A.csv"
    state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_UPLOADED
    state[STATE_INTAKE_DUPLICATE_REVIEW] = _keep_all_lookalikes(intake_a)
    run_uploaded_analysis(state, run_id="state_a_run")
    assert (
        calculated_emissions_summary(state[STATE_RESULT])["calculated_tco2e"] == total_a
    )

    begin_analysis_presentation_reset(state)
    assert state[STATE_RESULT] is None
    state[STATE_INTAKE_RESULT] = intake_b
    state[STATE_INTAKE_FILE_NAME] = "B.csv"
    state[STATE_INTAKE_DUPLICATE_REVIEW] = _keep_all_lookalikes(intake_b)
    run_uploaded_analysis(state, run_id="state_b_run")
    latest = calculated_emissions_summary(state[STATE_RESULT])["calculated_tco2e"]
    assert latest == total_b
    assert latest != total_a


def test_ng1_then_ng2_reanalysis_does_not_keep_ng1_total() -> None:
    csv = (
        "活動類型,用量,單位,開始日期,結束日期,廠場\n"
        "天然氣,8000,m3,2025-01-01,2025-01-31,高雄廠\n"
    )
    ng1, _ = intake_and_run(csv, run_id="ng1", natural_gas_subtype="NG1")
    ng2, _ = intake_and_run(csv, run_id="ng2", natural_gas_subtype="NG2")
    t1 = calculated_emissions_summary(ng1)["calculated_tco2e"]
    t2 = calculated_emissions_summary(ng2)["calculated_tco2e"]
    assert t1 != t2
    state: dict = {}
    initialize_ui_state(state)
    state[STATE_RESULT] = ng1
    begin_analysis_presentation_reset(state)
    assert state[STATE_RESULT] is None
    state[STATE_RESULT] = ng2
    assert calculated_emissions_summary(state[STATE_RESULT])["calculated_tco2e"] == t2


def test_navigation_keeps_latest_valid_result() -> None:
    result, intake = intake_and_run(
        dataset_a_csv(rows=120), run_id="nav", file_name="A.csv"
    )
    at = _run_app()
    at.session_state[STATE_RESULT] = result
    at.session_state[STATE_INTAKE_RESULT] = intake
    at.session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_UPLOADED
    at.session_state[STATE_INTAKE_FILE_NAME] = "A.csv"
    for page in (
        "app_pages/dashboard.py",
        "app_pages/activity_explorer.py",
        "app_pages/evidence_data.py",
        "app_pages/frameworks.py",
        "app_pages/dashboard.py",
    ):
        at.switch_page(page)
        at.run()
        assert not at.exception
        assert at.session_state[STATE_RESULT] is result


def test_fresh_customer_has_no_demo_contamination() -> None:
    at = _run_app()
    text = _all_text(at)
    assert "Demo Fasteners" not in text
    assert "23.7" not in text
    assert "ui_demo" not in text
    for token in ENGINEERING_TOKENS:
        assert token not in text, token
    stored = None
    if STATE_RESULT in at.session_state:
        stored = at.session_state[STATE_RESULT]
    assert stored is None


def test_customer_upload_export_is_not_synthetic(tmp_path: Path) -> None:
    result, _ = intake_and_run(dataset_a_csv(rows=120), run_id="syn_false")
    manifest_path = export_run_bundle(result, tmp_path / "out", synthetic_demo=False)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["synthetic_demo"] is False


def test_demo_export_is_synthetic(tmp_path: Path) -> None:
    state: dict = {}
    initialize_ui_state(state)
    result = activate_demo_mode(state, force=True)
    manifest_path = export_run_bundle(result, tmp_path / "demo", synthetic_demo=True)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["synthetic_demo"] is True
    assert get_analysis_source(state) == ANALYSIS_SOURCE_DEMO
    assert is_synthetic_analysis(state) is True


def test_start_analysis_disabled_while_analyzing() -> None:
    source = (REPO_ROOT / "streamlit_app.py").read_text(encoding="utf-8")
    assert "disabled=_analysis_busy" in source
    _result, intake = intake_and_run(
        dataset_a_csv(rows=120), run_id="busy", file_name="A.csv"
    )
    at = _run_app()
    at.session_state[STATE_INTAKE_RESULT] = intake
    at.session_state[STATE_INTAKE_FILE_NAME] = "A.csv"
    at.session_state[STATE_ANALYSIS_SOURCE] = ANALYSIS_SOURCE_UPLOADED
    at.session_state[STATE_ANALYSIS_RUNNING] = True
    at.session_state[STATE_ANALYSIS_PHASE] = ANALYSIS_PHASE_ANALYZING
    at.run()
    assert not at.exception


def test_empty_customer_pages_render() -> None:
    at = _run_app()
    pages = (
        "app_pages/dashboard.py",
        "app_pages/applicability.py",
        "app_pages/frameworks.py",
        "app_pages/taiwan_ghg.py",
        "app_pages/data_intake.py",
        "app_pages/audit_export.py",
    )
    for page in pages:
        at.switch_page(page)
        at.run()
        assert not at.exception
        text = _all_text(at)
        assert "Traceback" not in text
        assert "Exception" not in text
        for token in ENGINEERING_TOKENS:
            assert token not in text, f"{page}: {token}"


def test_english_smoke_has_no_raw_i18n_keys() -> None:
    at = _run_app()
    at.session_state["ui_language"] = "en"
    at.run()
    text = _all_text(at)
    assert "nav.dashboard" not in text
    assert "dash.kpi" not in text
    assert t("error.analysis_failed_safe", "en")


def test_new_file_reset_clears_analysis_result() -> None:
    state: dict = {}
    initialize_ui_state(state)
    result, _ = intake_and_run(dataset_a_csv(rows=120), run_id="reset")
    state[STATE_RESULT] = result
    clear_analysis_result(state)
    assert state[STATE_RESULT] is None


def test_customer_safe_error_hides_traceback() -> None:
    raw = customer_safe_analysis_error(
        RuntimeError("ValueError: NoneType traceback"), ZH
    )
    assert "NoneType" not in raw
    assert "traceback" not in raw.lower()
    assert "分析未完成" in raw
