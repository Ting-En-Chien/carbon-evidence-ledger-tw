"""Pure tests for Phase 8E chart data preparation."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from carbon_ledger.pipeline import run_demo_pipeline
from carbon_ledger.ui import charts
from carbon_ledger.ui.i18n import t

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")
EN = "en"
ZH = "zh-TW"


def _full_result():
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="ui_chart_test",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )


def test_calculation_status_counts_equal_activity_count() -> None:
    result = _full_result()
    before = result.calculation_results.copy()
    frame = charts.calculation_status_distribution(result, ZH)
    assert int(frame["count"].sum()) == len(result.activity_records_accepted)
    assert "blocked_missing_conversion" not in set(frame["label"])
    assert t("status.calculated", ZH) in set(frame["label"])
    pd.testing.assert_frame_equal(before, result.calculation_results)


def test_blocked_activities_not_in_emissions_contributions() -> None:
    result = _full_result()
    contrib = charts.calculated_emissions_contributions(result, ZH)
    assert len(contrib) == 1
    assert float(contrib["tco2e"].sum()) > 0
    overview_statuses = set(
        result.calculation_results["calculation_status"].astype(str)
    )
    assert "blocked_missing_conversion" in overview_statuses
    # Contributions include only calculated rows.
    assert all(contrib["tco2e"] > 0)


def test_ghg_scope_counts_equal_evaluations() -> None:
    result = _full_result()
    before = result.ghg_evaluations.copy()
    frame = charts.ghg_scope_classification_counts(result, ZH)
    assert int(frame["count"].sum()) == len(result.ghg_evaluations)
    assert t("chart.ghg_scope.title", ZH) == "活動分類筆數"
    help_text = t("chart.ghg_scope.help", ZH)
    assert "排放量占比" in help_text
    pd.testing.assert_frame_equal(before, result.ghg_evaluations)


def test_issue_gap_counts_equal_qa_rows() -> None:
    result = _full_result()
    before = result.core_qa_issues.copy()
    frame = charts.issue_gap_type_counts(result, ZH)
    assert int(frame["count"].sum()) == len(result.core_qa_issues)
    pd.testing.assert_frame_equal(before, result.core_qa_issues)


def test_language_switch_changes_labels_not_counts() -> None:
    result = _full_result()
    zh = charts.calculation_status_distribution(result, ZH)
    en = charts.calculation_status_distribution(result, EN)
    assert list(zh["count"]) == list(en["count"])
    assert list(zh["label"]) != list(en["label"])
    assert t("status.calculated", ZH) in set(zh["label"])
    assert t("status.calculated", EN) in set(en["label"])


def test_no_arbitrary_readiness_percentage_in_chart_copy() -> None:
    blob = " ".join(
        [
            t("chart.calc_status.help", ZH, n=5),
            t("chart.ghg_scope.help", ZH),
            t("chart.ifrs_ready.help", ZH),
            t("chart.issue_gaps.help", ZH),
        ]
    ).lower()
    assert "readiness score" not in blob
    assert "readiness percentage" not in blob
    assert "% ready" not in blob


def test_chart_height_constants_are_bounded() -> None:
    assert charts.CHART_HEIGHT_OVERVIEW <= 340
    assert charts.CHART_HEIGHT_SMALL <= 260
    assert charts.CHART_HEIGHT_COMPACT <= 160


def test_monthly_emissions_series_only_uses_calculated_rows() -> None:
    result = _full_result()
    frame = charts.monthly_emissions_series(result, ZH)
    assert not frame.empty
    assert set(frame.columns) == {"month", "tco2e"}
    assert float(frame["tco2e"].sum()) > 0


def test_emissions_source_excludes_blocked_as_zero() -> None:
    result = _full_result()
    contrib, blocked = charts.emissions_source_rows(result, ZH)
    assert not contrib.empty
    assert all(float(v) > 0 for v in contrib["tco2e"])
    assert not blocked.empty
