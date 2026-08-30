"""Pure tests for Phase 8 / 8B UI view-model helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from carbon_ledger.pipeline import run_demo_pipeline
from carbon_ledger.ui import view_models as vm
from carbon_ledger.ui.glossary import glossary_contains
from carbon_ledger.ui.tutorial import onboarding_step_titles

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXED_INGESTED_AT = pd.Timestamp("2024-02-01T00:00:00Z")
EN = "en"
ZH = "zh-TW"


def _full_result():
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="ui_view_model_test",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=True,
        include_cbam=True,
        include_ifrs_s2=True,
    )


def _core_only_result():
    return run_demo_pipeline(
        REPO_ROOT,
        run_id="ui_view_model_core",
        ingested_at=FIXED_INGESTED_AT,
        include_ghg=False,
        include_cbam=False,
        include_ifrs_s2=False,
    )


def _row(overview: pd.DataFrame, activity_type: str) -> pd.Series:
    matched = overview[overview["activity_type"] == activity_type]
    assert len(matched) == 1
    return matched.iloc[0]


def test_activity_overview_returns_five_baseline_rows() -> None:
    overview = vm.build_activity_overview(_full_result(), EN)
    assert len(overview) == 5


def test_activity_names_are_human_readable() -> None:
    overview = vm.build_activity_overview(_full_result(), EN)
    names = set(overview["activity_name"])
    assert "Purchased electricity" in names
    assert "Natural gas" in names
    assert "Diesel" in names
    assert "Purchased steel wire rod" in names
    assert "Finished-goods output" in names


def test_electricity_displays_calculated() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "grid_electricity")
    assert row["calculation_label"] == "Calculated"


def test_natural_gas_displays_blocked_missing_conversion() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "natural_gas")
    assert row["calculation_label"] == "Blocked — missing conversion"


def test_diesel_displays_blocked_missing_conversion() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "diesel")
    assert row["calculation_label"] == "Blocked — missing conversion"


def test_purchased_steel_displays_emission_factor_needed() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "purchased_steel")
    assert row["calculation_label"] == "Emission factor needed"


def test_finished_output_displays_supporting_data() -> None:
    row = _row(
        vm.build_activity_overview(_full_result(), EN),
        "finished_goods_output",
    )
    assert row["calculation_label"] == "Supporting data"


def test_electricity_ghg_label_is_scope_2() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "grid_electricity")
    assert row["ghg_label"] == "Scope 2"


def test_natural_gas_ghg_label_is_scope_1() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "natural_gas")
    assert row["ghg_label"] == "Scope 1"


def test_diesel_ghg_label_is_scope_1() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "diesel")
    assert row["ghg_label"] == "Scope 1"


def test_purchased_steel_ghg_label_scope_3_category_1() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "purchased_steel")
    assert row["ghg_label"] == "Scope 3 Category 1"


def test_finished_output_ghg_label_not_applicable() -> None:
    row = _row(
        vm.build_activity_overview(_full_result(), EN),
        "finished_goods_output",
    )
    assert row["ghg_label"] == "Not applicable"


def test_cbam_labels_separated_from_ghg_labels() -> None:
    overview = vm.build_activity_overview(_full_result(), EN)
    for _, row in overview.iterrows():
        assert row["cbam_label"] != row["ghg_label"]


def test_ifrs_labels_separated_from_ghg_labels() -> None:
    overview = vm.build_activity_overview(_full_result(), EN)
    for _, row in overview.iterrows():
        assert row["ifrs_s2_label"] != row["ghg_label"]


def test_disabled_adapter_displays_not_run() -> None:
    overview = vm.build_activity_overview(_core_only_result(), EN)
    assert (overview["ghg_label"] == "Not run").all()
    assert (overview["cbam_label"] == "Not run").all()
    assert (overview["ifrs_s2_label"] == "Not run").all()


def test_calculated_emissions_summary_includes_calculated_rows_only() -> None:
    summary = vm.calculated_emissions_summary(_full_result(), EN)
    assert summary["calculated_row_count"] == 1
    assert summary["calculated_tco2e"] is not None
    assert summary["calculated_tco2e"] > 0
    assert summary["partial"] is True
    assert summary["label"] == "Partial result"


def test_blocked_records_are_not_treated_as_zero() -> None:
    result = _full_result()
    overview = vm.build_activity_overview(result, EN)
    blocked = overview[
        overview["calculation_label"].isin(
            ["Blocked — missing conversion", "Emission factor needed"]
        )
    ]
    assert not blocked.empty
    assert blocked["calculated_tco2e"].isna().all()
    summary = vm.calculated_emissions_summary(result, EN)
    assert summary["calculated_row_count"] == 1


def test_qa_count_equals_current_core_qa_rows() -> None:
    result = _full_result()
    kpis = vm.dashboard_kpi_counts(result, EN)
    assert kpis["open_qa_issues"] == len(result.core_qa_issues)


def test_attention_flag_true_for_baseline_gas() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "natural_gas")
    assert bool(row["attention_required"]) is True


def test_attention_flag_true_for_baseline_diesel() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "diesel")
    assert bool(row["attention_required"]) is True


def test_attention_flag_true_for_baseline_steel() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "purchased_steel")
    assert bool(row["attention_required"]) is True


def test_attention_flag_false_for_electricity() -> None:
    row = _row(vm.build_activity_overview(_full_result(), EN), "grid_electricity")
    assert bool(row["attention_required"]) is False


def test_attention_flag_false_for_finished_output() -> None:
    row = _row(
        vm.build_activity_overview(_full_result(), EN),
        "finished_goods_output",
    )
    assert bool(row["attention_required"]) is False


def test_original_pipeline_result_dataframes_are_not_mutated() -> None:
    result = _full_result()
    before = {
        "activities": result.activity_records_accepted.copy(deep=True),
        "calculations": result.calculation_results.copy(deep=True),
        "ghg": result.ghg_evaluations.copy(deep=True),
        "cbam": result.cbam_evaluations.copy(deep=True),
        "ifrs": result.ifrs_s2_evaluations.copy(deep=True),
        "qa": result.core_qa_issues.copy(deep=True),
    }
    _ = vm.build_activity_overview(result, ZH)
    _ = vm.calculated_emissions_summary(result, ZH)
    _ = vm.attention_issue_cards(result, ZH)
    _ = vm.issues_table(result, ZH)
    _ = vm.ghg_framework_table(result, ZH)
    _ = vm.cbam_framework_table(result, ZH)
    _ = vm.ifrs_framework_table(result, ZH)
    assert result.activity_records_accepted.equals(before["activities"])
    assert result.calculation_results.equals(before["calculations"])
    assert result.ghg_evaluations.equals(before["ghg"])
    assert result.cbam_evaluations.equals(before["cbam"])
    assert result.ifrs_s2_evaluations.equals(before["ifrs"])
    assert result.core_qa_issues.equals(before["qa"])


def test_zh_default_status_labels() -> None:
    row = _row(vm.build_activity_overview(_full_result(), ZH), "natural_gas")
    assert "缺少轉換" in row["calculation_label"]


def test_glossary_core_terms() -> None:
    for term in (
        "Activity",
        "Emission factor",
        "tCO2e",
        "Scope 1",
        "Scope 2",
        "Scope 3",
        "IFRS S2",
    ):
        assert glossary_contains(term)
    assert not glossary_contains("CBAM")


def test_onboarding_has_five_action_steps() -> None:
    steps = onboarding_step_titles(ZH)
    assert steps == [
        "完成公司設定",
        "上傳活動資料",
        "確認資料內容",
        "開始計算",
        "查看計算結果",
    ]
    joined = "\n".join(steps)
    assert "GHG Protocol" not in joined
    assert "IFRS" not in joined
