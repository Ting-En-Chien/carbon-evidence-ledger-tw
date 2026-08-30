"""Stage 3B.3 — commercial product flow cleanup (modes, demo, export hygiene)."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from carbon_ledger.export import export_run_bundle
from carbon_ledger.pipeline import run_demo_pipeline
from carbon_ledger.ui.app_mode import (
    ENV_APP_MODE,
    AppMode,
    is_admin_mode,
    is_customer_mode,
    resolve_boot_mode,
    set_app_mode,
)
from carbon_ledger.ui.i18n import t
from carbon_ledger.ui.state import (
    ANALYSIS_SOURCE_DEMO,
    ANALYSIS_SOURCE_NONE,
    ANALYSIS_SOURCE_UPLOADED,
    STATE_COMPANY_PROFILE,
    STATE_RESULT,
    activate_demo_mode,
    clear_analysis_result,
    get_analysis_source,
    get_company_profile_mapping,
    get_current_result,
    initialize_ui_state,
    is_synthetic_analysis,
)
from carbon_ledger.ui.view_models import (
    beginner_result_summary,
    calculated_emissions_summary,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
HERO_JS = REPO_ROOT / "src/carbon_ledger/ui/hero_emissions_countup.js"
MOTION_PY = REPO_ROOT / "src/carbon_ledger/ui/motion.py"
# Frozen hash for Stage 3B.3 — do not modify hero_emissions_countup.js.
HERO_JS_SHA256 = (
    "70cd43b7f1fa2bedf4485bc7846278b736e1c183961c6c7117d6cc8b5f5828c0"
)
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")
ZH = "zh-TW"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _demo_result():
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="stage3b3_demo",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=False,
        include_ifrs_s2=True,
    )


# ---------------------------------------------------------------------------
# 40 — product modes
# ---------------------------------------------------------------------------


def test_new_customer_session_does_not_auto_load_demo() -> None:
    state: dict = {}
    initialize_ui_state(state)
    assert get_current_result(state) is None
    assert state.get(STATE_RESULT) is None
    assert get_analysis_source(state) == ANALYSIS_SOURCE_NONE
    assert not is_synthetic_analysis(state)


def test_customer_mode_has_no_synthetic_company_by_default() -> None:
    state: dict = {}
    initialize_ui_state(state)
    assert is_customer_mode(state)
    profile = get_company_profile_mapping(state)
    assert profile == {} or not str(profile.get("company_name") or "").strip()
    assert state.get(STATE_COMPANY_PROFILE) in ({}, None) or not str(
        (state.get(STATE_COMPANY_PROFILE) or {}).get("company_name") or ""
    ).strip()


def test_demo_requires_explicit_activate_demo_mode() -> None:
    state: dict = {}
    initialize_ui_state(state)
    assert get_analysis_source(state) == ANALYSIS_SOURCE_NONE
    result = activate_demo_mode(state)
    assert result is not None
    assert get_analysis_source(state) == ANALYSIS_SOURCE_DEMO
    assert is_synthetic_analysis(state)
    assert get_current_result(state) is result


def test_demo_mode_remains_functional_after_activate() -> None:
    state: dict = {}
    initialize_ui_state(state)
    result = activate_demo_mode(state)
    calcs = result.calculation_results
    electricity = calcs[calcs["record_id"].astype(str) == "rec_electricity_001"]
    assert not electricity.empty
    assert electricity.iloc[0]["calculation_status"] == "calculated"
    assert float(electricity.iloc[0]["calculated_tco2e"]) == 23.7


def test_get_analysis_source_empty_when_none() -> None:
    state: dict = {}
    initialize_ui_state(state)
    assert get_analysis_source(state) == ANALYSIS_SOURCE_NONE
    assert get_analysis_source(state) == ""
    clear_analysis_result(state)
    assert get_analysis_source(state) == ANALYSIS_SOURCE_NONE


def test_admin_mode_gated_by_cel_app_mode_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_APP_MODE, raising=False)
    assert resolve_boot_mode() is AppMode.CUSTOMER
    state: dict = {}
    initialize_ui_state(state)
    assert not is_admin_mode(state)
    # UI cannot escalate to admin without boot env.
    set_app_mode(state, AppMode.ADMIN)
    assert not is_admin_mode(state)
    assert is_customer_mode(state)

    monkeypatch.setenv(ENV_APP_MODE, "admin")
    assert resolve_boot_mode() is AppMode.ADMIN
    admin_state: dict = {}
    initialize_ui_state(admin_state)
    assert is_admin_mode(admin_state)


def test_app_mode_module_documents_no_fake_authentication() -> None:
    source = (
        REPO_ROOT / "src/carbon_ledger/ui/app_mode.py"
    ).read_text(encoding="utf-8")
    assert "not a security boundary" in source.lower() or "RBAC" in source
    assert "Real authentication" in source or "authentication" in source.lower()


# ---------------------------------------------------------------------------
# 41 — synthetic / real data export flag
# ---------------------------------------------------------------------------


def test_demo_export_synthetic_demo_true(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_demo"
    manifest_path = export_run_bundle(
        _demo_result(), output_dir, synthetic_demo=True
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["synthetic_demo"] is True


def test_uploaded_export_synthetic_demo_false(tmp_path: Path) -> None:
    output_dir = tmp_path / "bundle_uploaded"
    manifest_path = export_run_bundle(
        _demo_result(), output_dir, synthetic_demo=False
    )
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["synthetic_demo"] is False


def test_synthetic_demo_fixture_regression_still_usable() -> None:
    result = _demo_result()
    assert len(result.activity_records_accepted) == 5
    assert (
        result.calculation_results["calculation_status"] == "calculated"
    ).sum() == 1


# ---------------------------------------------------------------------------
# 43 — analysis progress / motion hygiene
# ---------------------------------------------------------------------------


def test_motion_py_has_no_sleep_based_fake_progress() -> None:
    source = MOTION_PY.read_text(encoding="utf-8")
    assert "time.sleep(" not in source
    assert "st.progress" in source
    assert "progress_callback" in source or "No artificial" in source


def test_hero_emissions_countup_js_unchanged_sha256() -> None:
    assert HERO_JS.is_file()
    assert _sha256(HERO_JS) == HERO_JS_SHA256
    script = HERO_JS.read_text(encoding="utf-8")
    assert "5311" not in script


def test_countup_path_still_uses_calculated_tco2e() -> None:
    motion_source = MOTION_PY.read_text(encoding="utf-8")
    assert "calculated_tco2e" in motion_source or "emissions_value" in motion_source


# ---------------------------------------------------------------------------
# 44 — partial calculation labeling
# ---------------------------------------------------------------------------


def test_partial_result_wording_includes_currently_calculated() -> None:
    assert "目前已計算" in t("chart.emissions_contrib.help", ZH)
    assert "目前已計算" in t("dash.section_trend_help", ZH)
    assert "已計算排放量" in t("dash.kpi.emissions", ZH)
    assert t("common.partial_result", ZH)


def test_partial_summary_does_not_treat_blocked_as_zero() -> None:
    result = _demo_result()
    emissions = calculated_emissions_summary(result, ZH)
    summary = beginner_result_summary(result, ZH)
    assert emissions["partial"] is True
    assert emissions["label"] == t("common.partial_result", ZH)
    assert emissions["calculated_row_count"] == 1
    assert float(emissions["calculated_tco2e"]) == 23.7
    assert int(summary["calculated"]) == 1
    assert int(summary["activities"]) > int(summary["calculated"])
    blocked = result.calculation_results[
        result.calculation_results["calculation_status"].astype(str)
        != "calculated"
    ]
    assert blocked["calculated_tco2e"].isna().all()
    assert not (blocked["calculated_tco2e"] == 0).any()


def test_natural_gas_and_diesel_remain_blocked_in_demo() -> None:
    result = _demo_result()
    calcs = result.calculation_results.set_index("record_id")
    assert calcs.loc["rec_gas_001", "calculation_status"] == (
        "blocked_missing_conversion"
    )
    assert calcs.loc["rec_diesel_001", "calculation_status"] == (
        "blocked_missing_conversion"
    )


# ---------------------------------------------------------------------------
# 45 — customer information hygiene (unit-level)
# ---------------------------------------------------------------------------


def test_customer_mode_is_default_without_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_APP_MODE, raising=False)
    # Ensure nested resolve does not inherit a polluted process env from peers.
    assert os.environ.get(ENV_APP_MODE) in (None, "")
    assert resolve_boot_mode() is AppMode.CUSTOMER


def test_analysis_source_constants_include_none() -> None:
    assert ANALYSIS_SOURCE_NONE == ""
    assert ANALYSIS_SOURCE_DEMO == "demo"
    assert ANALYSIS_SOURCE_UPLOADED == "uploaded"


# ---------------------------------------------------------------------------
# Extra Stage 3B.3 hygiene
# ---------------------------------------------------------------------------


def test_pipeline_progress_callback_emits_real_stages() -> None:
    events: list[str] = []

    def _cb(stage: str, completed: int, total: int, message: str) -> None:
        events.append(stage)
        assert total >= completed >= 0
        assert isinstance(message, str)

    run_demo_pipeline(
        REPO_ROOT,
        run_id="stage3b3_progress",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_ifrs_s2=True,
        progress_callback=_cb,
    )
    assert "normalize" in events
    assert "factors" in events
    assert "calculate" in events
    assert "qa" in events


def test_intake_missing_site_defaults_to_unknown_not_site_main() -> None:
    from carbon_ledger.intake import (
        ColumnMapping,
        IntakeMetadata,
        build_and_validate_intake,
        parse_uploaded_table,
    )

    csv = (
        "activity,amount,unit,start,end\n"
        "grid_electricity,10,kWh,2025-01-01,2025-01-31\n"
    ).encode("utf-8")
    table = parse_uploaded_table(file_name="co.csv", data=csv)
    mapping = ColumnMapping(
        activity_type_column="activity",
        activity_value_column="amount",
        unit_column="unit",
        use_file_dates=True,
        start_date_column="start",
        end_date_column="end",
        activity_type_value_map={"grid_electricity": "grid_electricity"},
        unit_value_map={"kWh": "kWh"},
    )
    metadata = IntakeMetadata(
        source_name="co.csv",
        site_id="",
        document_date=__import__("datetime").date(2025, 1, 31),
        data_quality_tier="unknown",
        intake_run_id="t",
        ingested_at=pd.Timestamp("2025-02-01T00:00:00Z"),
    )
    result = build_and_validate_intake(table, mapping, metadata)
    assert result.accepted_count == 1
    site = str(result.accepted_activities.iloc[0]["site_id"])
    assert site == "UNKNOWN"
    assert site != "site_main"


def test_customer_dashboard_onboarding_without_demo() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file(str(REPO_ROOT / "streamlit_app.py"), default_timeout=120)
    at.run()
    assert get_current_result(at.session_state) is None
    text_chunks = []
    for collection_name in ("markdown", "caption", "button"):
        for item in getattr(at, collection_name, []) or []:
            for attr in ("value", "body", "label"):
                value = getattr(item, attr, None)
                if value is not None:
                    text_chunks.append(str(value))
    text = "\n".join(text_chunks)
    assert "歡迎使用" in text or "Welcome" in text
    assert "使用示範資料" in text or "Try demo data" in text
    assert "automated_sources_expected" not in text
